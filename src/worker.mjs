// Orca ADE Antigravity Auto-Switcher Plugin Worker
// Handles background quota monitoring, status bar updates, auto-rotation, and panel RPC.

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const POLL_INTERVAL_MS = 15000;
const SETTLE_DELAY_MS = 2000;
const DEFAULT_COOLDOWN_MS = 30000;

let lastSwitchTime = 0;
let isSwitching = false;

function formatEmailShort(email) {
  if (!email) return 'None';
  const prefix = email.split('@')[0];
  return prefix.length > 12 ? prefix.slice(0, 10) + '..' : prefix;
}

function formatMinutesLeft(tsMs) {
  if (!tsMs) return 'Unknown';
  const diffMinutes = Math.max(0, Math.floor((tsMs - Date.now()) / 60000));
  return `${diffMinutes}m`;
}

async function runOrcaCommand(args) {
  try {
    const { stdout } = await execFileAsync('orca', args, { encoding: 'utf8' });
    return JSON.parse(stdout);
  } catch (err) {
    return null;
  }
}

export default function activate(orca) {
  orca.log('Antigravity Auto-Switcher: Plugin activated.');

  async function fetchAccountsData() {
    const data = await runOrcaCommand(['account', 'list', '--agent', 'antigravity', '--json']);
    if (!data || !data.result) return null;

    const result = data.result;
    const activeId = result.activeAccountId;
    const rawAccounts = result.accounts || [];

    const accounts = rawAccounts.map((acc) => {
      const usage = acc.usage || {};
      const session = usage.session || {};
      const weekly = usage.weekly || {};
      const buckets = usage.buckets || [];

      return {
        id: acc.id,
        email: acc.email,
        isActive: acc.id === activeId,
        sessionUsed: Number(session.usedPercent || 0),
        weeklyUsed: Number(weekly.usedPercent || 0),
        sessionResetsAt: session.resetsAt,
        weeklyResetsAt: weekly.resetsAt,
        isExhausted: (session.usedPercent >= 1.0 || weekly.usedPercent >= 1.0),
        earliestReset: session.resetsAt || weekly.resetsAt || (buckets[0] && buckets[0].resetsAt),
      };
    });

    const activeAccount = accounts.find((a) => a.isActive) || null;
    return { accounts, activeId, activeAccount };
  }

  async function updateStatusBar(activeAccount) {
    if (!activeAccount) {
      await orca.host.call('statusBar.update', {
        id: 'agy-status',
        text: 'Agy: No Account',
        icon: 'refresh',
        tone: 'neutral',
        tooltip: 'Antigravity: No active account found.',
      });
      return;
    }

    const shortEmail = formatEmailShort(activeAccount.email);
    const usedPct = Math.round(activeAccount.sessionUsed * 100);
    const tone = activeAccount.isExhausted ? 'danger' : (usedPct >= 80 ? 'warning' : 'success');

    const resetStr = activeAccount.earliestReset ? ` · Reset in ${formatMinutesLeft(activeAccount.earliestReset)}` : '';
    const tooltip = `Antigravity: ${activeAccount.email} (${usedPct}% used)${resetStr}`;

    await orca.host.call('statusBar.update', {
      id: 'agy-status',
      text: `Agy: ${shortEmail} (${usedPct}%)`,
      icon: 'refresh',
      tone,
      tooltip,
    });
  }

  async function rotateToBestAccount(reason = 'Rate limit terdeteksi') {
    const now = Date.now();
    if (isSwitching) return { success: false, reason: 'Switch in progress' };
    if (now - lastSwitchTime < DEFAULT_COOLDOWN_MS) {
      const remainingSec = Math.ceil((DEFAULT_COOLDOWN_MS - (now - lastSwitchTime)) / 1000);
      return { success: false, reason: `In cooldown (${remainingSec}s left)` };
    }

    isSwitching = true;
    try {
      const state = await fetchAccountsData();
      if (!state || !state.accounts.length) {
        return { success: false, reason: 'No accounts' };
      }

      const activeEmail = state.activeAccount ? state.activeAccount.email : 'Unknown';
      const available = state.accounts.filter((a) => !a.isActive && !a.isExhausted);

      if (!available.length) {
        await orca.host.call('notifications.show', {
          title: 'Antigravity: Semua Akun Limit!',
          body: 'Seluruh akun telah mencapai batas kuota 100%. Rotasi dijeda.',
        });
        return { success: false, reason: 'All accounts exhausted' };
      }

      // Sort lowest usage first
      available.sort((a, b) => (a.sessionUsed + a.weeklyUsed) - (b.sessionUsed + b.weeklyUsed));
      const target = available[0];

      orca.log(`Rotating account: ${activeEmail} -> ${target.email} (Reason: ${reason})`);
      const switchRes = await runOrcaCommand([
        'account', 'select', '--agent', 'antigravity', '--account', target.email, '--json'
      ]);

      lastSwitchTime = Date.now();

      await orca.host.call('notifications.show', {
        title: 'Rotasi Akun Antigravity',
        body: `Limit pada ${activeEmail}. Berhasil beralih ke ${target.email}`,
      });

      // Settle delay before resuming terminal
      await new Promise((resolve) => setTimeout(resolve, SETTLE_DELAY_MS));

      // Auto-resume active terminal
      const termsData = await runOrcaCommand(['terminal', 'list', '--json']);
      const terms = (termsData && termsData.result && termsData.result.terminals) || [];
      const activeTerm = terms.find((t) => t.connected && t.writable);

      if (activeTerm) {
        await orca.host.call('terminal.sendText', {
          terminalId: activeTerm.handle,
          text: 'lanjutkan pengerjaan tadi',
          enter: true,
        });
        orca.log(`Auto-resume sent to terminal ${activeTerm.handle}`);
      }

      const newState = await fetchAccountsData();
      if (newState && newState.activeAccount) {
        await updateStatusBar(newState.activeAccount);
      }

      return { success: true, newEmail: target.email };
    } finally {
      isSwitching = false;
    }
  }

  // Periodic quota & status bar check
  async function checkQuotaAndRefresh() {
    try {
      const state = await fetchAccountsData();
      if (!state) return;

      await updateStatusBar(state.activeAccount);

      // Auto rotate if active account is exhausted
      if (state.activeAccount && state.activeAccount.isExhausted) {
        await rotateToBestAccount(`Kuota akun aktif habis (${Math.round(state.activeAccount.sessionUsed * 100)}%)`);
      }
    } catch (e) {
      orca.log(`Error in checkQuotaAndRefresh: ${e.message}`);
    }
  }

  // Hook into agent status changes
  if (orca.events && orca.events.on) {
    orca.events.on('agent.status.changed', async (event) => {
      if (event && event.state === 'blocked') {
        orca.log(`Agent status changed to blocked: ${event.title || 'agent'}. Checking quota...`);
        const state = await fetchAccountsData();
        if (state && state.activeAccount && state.activeAccount.isExhausted) {
          await rotateToBestAccount('Agen terhenti karena limit kuota');
        }
      }
    });
  }

  // Register command for command palette / status bar click
  if (orca.commands && orca.commands.register) {
    orca.commands.register('rotate-now', async () => {
      return rotateToBestAccount('Manual command trigger');
    });
  }

  // Register panel RPC handlers
  if (orca.panels && orca.panels.handle) {
    orca.panels.handle('accounts.read', async () => {
      const state = await fetchAccountsData();
      return state || { accounts: [], activeId: null };
    });

    orca.panels.handle('accounts.rotateNow', async () => {
      return rotateToBestAccount('Triggered from UI panel');
    });

    orca.panels.handle('accounts.selectTarget', async (input) => {
      const target = (input && input.target) || input;
      if (!target) return { success: false, reason: 'Target missing' };
      const res = await runOrcaCommand(['account', 'select', '--agent', 'antigravity', '--account', target, '--json']);
      lastSwitchTime = Date.now();
      const state = await fetchAccountsData();
      if (state && state.activeAccount) await updateStatusBar(state.activeAccount);
      return { success: true, result: res };
    });
  }

  // Start initial check and background interval
  checkQuotaAndRefresh();
  const timer = setInterval(checkQuotaAndRefresh, POLL_INTERVAL_MS);

  return {
    dispose() {
      clearInterval(timer);
      orca.log('Antigravity Auto-Switcher: Plugin deactivated.');
    },
  };
}

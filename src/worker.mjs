// Orca ADE Antigravity Auto-Switcher Plugin Worker
// Handles real-time quota monitoring, model detection, status bar updates, and panel RPC.

import { execFile } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const POLL_INTERVAL_MS = 3500;
const SETTLE_DELAY_MS = 2000;
const DEFAULT_COOLDOWN_MS = 30000;

let lastSwitchTime = 0;
let isSwitching = false;

function resolveOrcaBinary() {
  const home = homedir();
  const candidates = [
    process.env.ORCA_CLI_COMMAND,
    join(home, '.config', 'orca', 'linux-orca-cli-shim', 'orca'),
    '/opt/homebrew/bin/orca',
    '/usr/local/bin/orca',
    join(home, 'AppData', 'Local', 'Programs', 'Orca', 'resources', 'bin', 'orca.cmd'),
    'orca',
  ].filter(Boolean);

  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return 'orca';
}

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

async function runOrcaCommand(args, logFn = null) {
  const bin = resolveOrcaBinary();
  const env = {
    ...process.env,
    PATH: `${join(homedir(), '.config', 'orca', 'linux-orca-cli-shim')}:${process.env.PATH || ''}`,
  };

  try {
    const { stdout } = await execFileAsync(bin, args, { encoding: 'utf8', env });
    return JSON.parse(stdout);
  } catch (err) {
    if (logFn) logFn(`runOrcaCommand error [${bin} ${args.join(' ')}]: ${err.message}`);
    return null;
  }
}

export default function activate(orca) {
  orca.log('Antigravity Auto-Switcher: Plugin worker activated (Real-time mode).');

  async function detectActiveSession() {
    try {
      const termsData = await runOrcaCommand(['terminal', 'list', '--json']);
      const terms = (termsData && termsData.result && termsData.result.terminals) || [];

      // Find terminal that is active/connected
      for (const t of terms) {
        if (!t.connected) continue;
        const preview = t.preview || '';
        const title = t.title || '';
        const combined = `${title} ${preview}`;

        // Look for model name (including paid/internal models like Argon, Carbon, Claude, GPT, Gemini)
        const match = combined.match(/(?:Argon(?:\s+[a-z0-9\.-]+)?|Carbon(?:\s+[a-z0-9\.-]+)?|Gemini\s+[0-9\.]+(?:\s+[a-z]+)?|GPT-[0-9\.]+(?:\s+[a-z]+)?|Claude\s+[0-9\.]+(?:\s+[a-z]+)?|o[13](?:-mini|-preview)?|DeepSeek-[a-z0-9\.-]+)/i);
        const modelName = match ? match[0].trim() : null;

        if (modelName || combined.toLowerCase().includes('antigravity') || combined.toLowerCase().includes('gemini') || combined.toLowerCase().includes('argon') || combined.toLowerCase().includes('carbon')) {
          return {
            terminalId: t.handle,
            title: t.title || 'Terminal Session',
            model: modelName || 'Gemini / Paid Models (Antigravity)',
            agent: t.agentIdentity || 'antigravity',
            lastOutputAt: t.lastOutputAt,
          };
        }
      }

      // Fallback: check most recently writable terminal
      const writable = terms.find((t) => t.connected && t.writable);
      if (writable) {
        return {
          terminalId: writable.handle,
          title: writable.title || 'Terminal Session',
          model: 'Gemini Models (Antigravity)',
          agent: writable.agentIdentity || 'antigravity',
          lastOutputAt: writable.lastOutputAt,
        };
      }
    } catch (e) {
      // ignore
    }

    return {
      terminalId: null,
      title: 'Active Session',
      model: 'Gemini Models (Antigravity)',
      agent: 'antigravity',
    };
  }

  function computeTokenTelemetry() {
    const brainDir = join(homedir(), '.config', 'orca', 'antigravity-chat', 'antigravity-acp', 'brain');
    if (!existsSync(brainDir)) return null;

    try {
      const convDirs = readdirSync(brainDir);
      const now = Date.now();
      const ONE_DAY = 24 * 60 * 60 * 1000;
      const cutoffs = {
        today: now - ONE_DAY,
        '7d': now - 7 * ONE_DAY,
        '30d': now - 30 * ONE_DAY,
        all: 0,
      };

      const stats = {
        today: { total: 0, input: 0, output: 0, cache: 0, turns: 0 },
        '7d': { total: 0, input: 0, output: 0, cache: 0, turns: 0 },
        '30d': { total: 0, input: 0, output: 0, cache: 0, turns: 0 },
        all: { total: 0, input: 0, output: 0, cache: 0, turns: 0 },
      };

      const dailyMap = {};
      const hourlyTodayMap = {};

      for (const c of convDirs) {
        const tFile = join(brainDir, c, '.system_generated', 'logs', 'transcript.jsonl');
        if (!existsSync(tFile)) continue;
        try {
          const content = readFileSync(tFile, 'utf8');
          const lines = content.split('\n');
          for (const line of lines) {
            if (!line.includes('input_tokens')) continue;
            try {
              const d = JSON.parse(line);
              const inp = d.input_tokens || 0;
              const out = d.output_tokens || 0;
              const cch = d.cache_read_tokens || 0;
              const tot = inp + out + cch;
              if (!tot && !d.created_at) continue;

              const ts = d.created_at ? new Date(d.created_at).getTime() : now;
              const dateStr = d.created_at ? d.created_at.slice(0, 10) : 'Today';

              if (!dailyMap[dateStr]) dailyMap[dateStr] = { date: dateStr, total: 0, input: 0, output: 0, cache: 0, turns: 0 };
              dailyMap[dateStr].total += tot;
              dailyMap[dateStr].input += inp;
              dailyMap[dateStr].output += out;
              dailyMap[dateStr].cache += cch;
              dailyMap[dateStr].turns += 1;

              if (ts >= cutoffs.today) {
                const hourStr = (d.created_at ? d.created_at.slice(11, 13) : '12') + ':00';
                if (!hourlyTodayMap[hourStr]) hourlyTodayMap[hourStr] = { label: hourStr, total: 0, input: 0, output: 0, cache: 0, turns: 0 };
                hourlyTodayMap[hourStr].total += tot;
                hourlyTodayMap[hourStr].input += inp;
                hourlyTodayMap[hourStr].output += out;
                hourlyTodayMap[hourStr].cache += cch;
                hourlyTodayMap[hourStr].turns += 1;
              }

              for (const [key, cutoff] of Object.entries(cutoffs)) {
                if (ts >= cutoff) {
                  stats[key].total += tot;
                  stats[key].input += inp;
                  stats[key].output += out;
                  stats[key].cache += cch;
                  stats[key].turns += 1;
                }
              }
            } catch (e) {}
          }
        } catch (e) {}
      }

      for (const s of Object.values(stats)) {
        s.hitRate = s.total > 0 ? (s.cache / s.total) * 100 : 0;
        s.cost = (s.input * 1.25 + s.output * 5.00 + s.cache * 0.30) / 1_000_000;
        s.savings = (s.cache * (1.25 - 0.30)) / 1_000_000;
      }

      return {
        periods: stats,
        daily: Object.values(dailyMap).sort((a, b) => a.date.localeCompare(b.date)),
        hourlyToday: Object.values(hourlyTodayMap).sort((a, b) => a.label.localeCompare(b.label)),
      };
    } catch (err) {
      return null;
    }
  }

  async function fetchAccountsData() {
    const data = await runOrcaCommand(['account', 'list', '--agent', 'antigravity', '--json'], (msg) => orca.log(msg));
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
        isExhausted: (Number(session.usedPercent || 0) >= 100 || Number(weekly.usedPercent || 0) >= 100),
        earliestReset: session.resetsAt || weekly.resetsAt || (buckets[0] && buckets[0].resetsAt),
        buckets: buckets.map((b) => ({
          name: b.name || b.windowName || 'Bucket',
          group: b.group || 'Model',
          usedPercent: Number(b.usedPercent || 0),
          resetsAt: b.resetsAt,
        })),
      };
    });

    const activeAccount = accounts.find((a) => a.isActive) || null;
    const totalAccounts = accounts.length;
    const availableAccounts = accounts.filter((a) => !a.isExhausted).length;
    const exhaustedAccounts = accounts.filter((a) => a.isExhausted).length;
    const healthPercent = totalAccounts > 0 ? Math.round((availableAccounts / totalAccounts) * 100) : 0;

    const activeSession = await detectActiveSession();
    const telemetry = computeTokenTelemetry();

    return {
      accounts,
      activeId,
      activeAccount,
      globalStats: {
        totalAccounts,
        availableAccounts,
        exhaustedAccounts,
        healthPercent,
      },
      activeSession,
      telemetry,
      timestamp: Date.now(),
    };
  }

  async function updateStatusBar(activeAccount, modelName = 'Gemini') {
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
    const usedPct = Math.round(activeAccount.sessionUsed);
    const tone = activeAccount.isExhausted ? 'danger' : (usedPct >= 80 ? 'warning' : 'success');

    const resetStr = activeAccount.earliestReset ? ` · Reset in ${formatMinutesLeft(activeAccount.earliestReset)}` : '';
    const tooltip = `Antigravity: ${activeAccount.email} (${usedPct}% used) · Model: ${modelName}${resetStr}`;

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
    if (isSwitching) return { success: false, reason: 'Pergantian akun sedang berlangsung' };
    if (now - lastSwitchTime < DEFAULT_COOLDOWN_MS) {
      const remainingSec = Math.ceil((DEFAULT_COOLDOWN_MS - (now - lastSwitchTime)) / 1000);
      return { success: false, reason: `Dalam masa cooldown (${remainingSec}s tersisa)` };
    }

    isSwitching = true;
    try {
      const state = await fetchAccountsData();
      if (!state || !state.accounts.length) {
        return { success: false, reason: 'Tidak ada akun Antigravity' };
      }

      const activeEmail = state.activeAccount ? state.activeAccount.email : 'Unknown';
      const available = state.accounts.filter((a) => !a.isActive && !a.isExhausted);

      if (!available.length) {
        await orca.host.call('notifications.show', {
          title: 'Semua Akun Limit',
          body: 'Seluruh kuota akun habis. Menunggu waktu reset.',
        });
        return { success: false, reason: 'Semua akun limit' };
      }

      // Sort lowest usage first
      available.sort((a, b) => (a.sessionUsed + a.weeklyUsed) - (b.sessionUsed + b.weeklyUsed));
      const target = available[0];

      orca.log(`Rotating account: ${activeEmail} -> ${target.email} (Reason: ${reason})`);
      await runOrcaCommand([
        'account', 'select', '--agent', 'antigravity', '--account', target.email, '--json'
      ]);

      lastSwitchTime = Date.now();

      await orca.host.call('notifications.show', {
        title: 'Akun Dirotasi',
        body: `Beralih ke ${target.email}. Melanjutkan pengerjaan...`,
      });

      // Settle delay before resuming terminal
      await new Promise((resolve) => setTimeout(resolve, SETTLE_DELAY_MS));

      // Auto-resume active terminal (prioritizing Antigravity agent sessions)
      const termsData = await runOrcaCommand(['terminal', 'list', '--json']);
      const terms = (termsData && termsData.result && termsData.result.terminals) || [];
      const writableTerms = terms.filter((t) => t.connected && t.writable);

      function isAgentTerminal(t) {
        const text = `${t.title || ''} ${t.preview || ''} ${t.agentIdentity || ''}`.toLowerCase();
        return text.includes('antigravity') || text.includes('gemini') || text.includes('agy') || text.includes('argon') || text.includes('carbon');
      }

      writableTerms.sort((a, b) => {
        const aAgent = isAgentTerminal(a) ? 1 : 0;
        const bAgent = isAgentTerminal(b) ? 1 : 0;
        if (aAgent !== bAgent) return bAgent - aAgent;
        return (b.lastOutputAt || 0) - (a.lastOutputAt || 0);
      });

      const activeTerm = writableTerms[0];

      if (activeTerm) {
        await orca.host.call('terminal.sendText', {
          terminalId: activeTerm.handle,
          text: 'lanjutkan pengerjaan tadi',
          enter: true,
        });
        orca.log(`Auto-resume sent to terminal ${activeTerm.handle}`);
      }

      const newState = await fetchAccountsData();
      if (newState) {
        await updateStatusBar(newState.activeAccount, newState.activeSession?.model);
        if (orca.panels && orca.panels.post) {
          orca.panels.post('accounts.changed', newState);
        }
      }

      return { success: true, newEmail: target.email };
    } finally {
      isSwitching = false;
    }
  }

  // Periodic quota & status bar check with panel broadcast
  async function checkQuotaAndRefresh() {
    try {
      const state = await fetchAccountsData();
      if (!state) return;

      await updateStatusBar(state.activeAccount, state.activeSession?.model);

      // Broadcast real-time state to any open panel
      if (orca.panels && orca.panels.post) {
        orca.panels.post('accounts.changed', state);
      }

      // Auto rotate if active account is exhausted
      if (state.activeAccount && state.activeAccount.isExhausted) {
        await rotateToBestAccount(`Kuota akun aktif habis (${Math.round(state.activeAccount.sessionUsed)}%)`);
      }
    } catch (e) {
      orca.log(`Error in checkQuotaAndRefresh: ${e.message}`);
    }
  }

  // Hook into agent status changes
  if (orca.events && orca.events.on) {
    orca.events.on('agent.status.changed', async (event) => {
      if (event && event.state === 'blocked') {
        orca.log(`Agent status blocked: ${event.title || 'agent'}. Checking quota...`);
        const state = await fetchAccountsData();
        if (state && state.activeAccount && state.activeAccount.isExhausted) {
          await rotateToBestAccount('Agen terhenti karena limit kuota');
        }
      }
    });

    orca.events.on('workspace.changed', () => {
      checkQuotaAndRefresh();
    });
  }

  // Register command for command palette
  if (orca.commands && orca.commands.register) {
    orca.commands.register('rotate-now', async () => {
      return rotateToBestAccount('Triggered from command palette');
    });
  }

  // Register panel RPC handlers
  if (orca.panels && orca.panels.handle) {
    orca.panels.handle('accounts.read', async () => {
      const state = await fetchAccountsData();
      return state || { accounts: [], activeId: null };
    });

    orca.panels.handle('telemetry.read', async () => {
      return computeTokenTelemetry();
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
      if (state) {
        await updateStatusBar(state.activeAccount, state.activeSession?.model);
        if (orca.panels && orca.panels.post) {
          orca.panels.post('accounts.changed', state);
        }
      }
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

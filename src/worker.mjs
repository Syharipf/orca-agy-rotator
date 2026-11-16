// Orca ADE Antigravity Auto-Switcher Plugin Worker
// Handles real-time quota monitoring, model detection, status bar updates, and panel RPC.

import { execFile } from 'node:child_process';
import { createReadStream, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

function loadPluginConfig() {
  try {
    const cfgPath = join(fileURLToPath(new URL('..', import.meta.url)), 'config.json');
    if (existsSync(cfgPath)) {
      return JSON.parse(readFileSync(cfgPath, 'utf8'));
    }
  } catch {}
  return {};
}

const pluginConfig = loadPluginConfig();

const POLL_INTERVAL_MS = 3500;
const SETTLE_DELAY_MS = (pluginConfig.resume_delay_seconds ?? 2.0) * 1000;
const DEFAULT_COOLDOWN_MS = (pluginConfig.cooldown_seconds ?? 30.0) * 1000;
const CIRCUIT_BREAKER_MAX = pluginConfig.circuit_breaker_max_switches ?? 5;
const CIRCUIT_BREAKER_WINDOW_MS = (pluginConfig.circuit_breaker_window_seconds ?? 180.0) * 1000;
const TARGET_TERMINAL_CONFIG = pluginConfig.target_terminal ?? null;
const RESUME_COMMAND = pluginConfig.resume_command || 'lanjutkan pengerjaan tadi';

const DEFAULT_PRICING = {
  input: (pluginConfig.pricing && pluginConfig.pricing.input_per_million) ?? 1.25,
  output: (pluginConfig.pricing && pluginConfig.pricing.output_per_million) ?? 5.00,
  cache: (pluginConfig.pricing && pluginConfig.pricing.cache_read_per_million) ?? 0.30,
};

let lastSwitchTime = 0;
let isSwitching = false;
let switchHistory = [];
let isCircuitBreakerTripped = false;
let circuitBreakerTrippedAt = 0;

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

      // Only inspect terminals that explicitly belong to the Antigravity agent runtime
      for (const t of terms) {
        if (!t.connected) continue;
        const identity = (t.agentIdentity || '').toLowerCase();
        const preview = (t.preview || '').toLowerCase();
        const title = (t.title || '').toLowerCase();
        const combined = `${title} ${preview}`;

        // Explicit Antigravity identity or Antigravity runtime indicators
        const isAgyAgent = identity === 'antigravity' ||
          combined.includes('antigravity') ||
          (combined.includes('gemini') && !combined.includes('gpt-') && !identity.includes('omp') && !identity.includes('codex'));

        if (isAgyAgent) {
          // Detect specific Gemini or Antigravity internal model
          const match = combined.match(/(?:Gemini\s+[0-9\.]+(?:\s+[a-z]+)?|Argon(?:[\s\-][a-z0-9\.]+)?|Carbon(?:[\s\-][a-z0-9\.]+)?)/i);
          const modelName = match ? match[0].trim() : 'Gemini (Antigravity)';

          return {
            terminalId: t.handle,
            title: t.title || 'Antigravity Session',
            model: modelName,
            agent: 'antigravity',
            isAntigravityActive: true,
            lastOutputAt: t.lastOutputAt,
          };
        }
      }
    } catch (e) {
      // ignore
    }

    return {
      terminalId: null,
      title: 'Antigravity Standby',
      model: 'Tidak ada sesi Antigravity aktif',
      agent: 'antigravity',
      isAntigravityActive: false,
    };
  }

  const transcriptCache = new Map();

  async function getTranscriptRecords(tFile, st) {
    const cached = transcriptCache.get(tFile);
    if (cached && cached.mtimeMs === st.mtimeMs && cached.size === st.size) {
      return cached.records;
    }

    const records = [];
    const rl = createInterface({
      input: createReadStream(tFile, { encoding: 'utf8' }),
      crlfDelay: Infinity,
    });

    for await (const line of rl) {
      if (!line.includes('input_tokens')) continue;
      try {
        const d = JSON.parse(line);
        const inp = d.input_tokens || 0;
        const out = d.output_tokens || 0;
        const cch = d.cache_read_tokens || 0;
        const tot = inp + out + cch;
        if (!tot && !d.created_at) continue;

        const ts = d.created_at ? new Date(d.created_at).getTime() : Date.now();
        const dateStr = d.created_at ? d.created_at.slice(0, 10) : 'Today';
        const hourStr = (d.created_at ? d.created_at.slice(11, 13) : '12') + ':00';
        records.push({ ts, dateStr, hourStr, tot, inp, out, cch });
      } catch (e) {}
    }

    transcriptCache.set(tFile, { mtimeMs: st.mtimeMs, size: st.size, records });
    return records;
  }

  async function computeTokenTelemetry() {
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
          const st = statSync(tFile);
          const records = await getTranscriptRecords(tFile, st);
          for (const r of records) {
            const { ts, dateStr, hourStr, tot, inp, out, cch } = r;

            if (!dailyMap[dateStr]) dailyMap[dateStr] = { date: dateStr, total: 0, input: 0, output: 0, cache: 0, turns: 0 };
            dailyMap[dateStr].total += tot;
            dailyMap[dateStr].input += inp;
            dailyMap[dateStr].output += out;
            dailyMap[dateStr].cache += cch;
            dailyMap[dateStr].turns += 1;

            if (ts >= cutoffs.today) {
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
          }
        } catch (e) {}
      }

      for (const s of Object.values(stats)) {
        s.hitRate = s.total > 0 ? (s.cache / s.total) * 100 : 0;
        s.cost = (s.input * DEFAULT_PRICING.input + s.output * DEFAULT_PRICING.output + s.cache * DEFAULT_PRICING.cache) / 1_000_000;
        s.savings = (s.cache * (DEFAULT_PRICING.input - DEFAULT_PRICING.cache)) / 1_000_000;
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
    const telemetry = await computeTokenTelemetry();

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

  const maskFile = join(homedir(), '.config', 'orca', 'antigravity-chat', 'antigravity-acp', 'mask_state.json');
  let isMasked = true;
  try {
    if (existsSync(maskFile)) {
      const parsed = JSON.parse(readFileSync(maskFile, 'utf8'));
      if (parsed && typeof parsed.masked === 'boolean') {
        isMasked = parsed.masked;
      }
    }
  } catch (err) {
    orca.log(`Error reading mask state from ${maskFile}: ${err.message}`);
  }

  function saveMaskState(val) {
    try {
      const dir = dirname(maskFile);
      if (!existsSync(dir)) {
        mkdirSync(dir, { recursive: true });
      }
      writeFileSync(maskFile, JSON.stringify({ masked: val }), 'utf8');
    } catch (err) {
      orca.log(`saveMaskState failed for ${maskFile}: ${err.message}`);
    }
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

    const shortEmail = isMasked ? 'dev-lead' : formatEmailShort(activeAccount.email);
    const displayEmail = isMasked ? 'dev-lead@example.com' : activeAccount.email;
    const usedPct = Math.round(activeAccount.sessionUsed);
    const tone = activeAccount.isExhausted ? 'danger' : (usedPct >= 80 ? 'warning' : 'success');

    const resetStr = activeAccount.earliestReset ? ` · Reset in ${formatMinutesLeft(activeAccount.earliestReset)}` : '';
    const tooltip = `Antigravity: ${displayEmail} (${usedPct}% used) · Model: ${modelName}${resetStr}`;

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

    // 1. Check sliding-window circuit breaker
    if (isCircuitBreakerTripped) {
      const remainingCooldown = CIRCUIT_BREAKER_WINDOW_MS - (now - circuitBreakerTrippedAt);
      if (remainingCooldown > 0) {
        const remainingSec = Math.ceil(remainingCooldown / 1000);
        return {
          success: false,
          reason: `Circuit breaker aktif! Ditahan selama ${remainingSec}s lagi untuk mencegah loop.`,
        };
      }
      isCircuitBreakerTripped = false;
      switchHistory = [];
    }

    // 2. Check cooldown between switches
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
      switchHistory.push(lastSwitchTime);

      // Purge entries outside sliding window
      const cutoff = lastSwitchTime - CIRCUIT_BREAKER_WINDOW_MS;
      switchHistory = switchHistory.filter((t) => t >= cutoff);

      if (switchHistory.length >= CIRCUIT_BREAKER_MAX) {
        isCircuitBreakerTripped = true;
        circuitBreakerTrippedAt = lastSwitchTime;
        orca.log(`Circuit breaker tripped: ${switchHistory.length} switches in ${CIRCUIT_BREAKER_WINDOW_MS / 1000}s`);
        await orca.host.call('notifications.show', {
          title: 'Rotasi Ditahan (Circuit Breaker)',
          body: `Batas pergantian tercapai (${CIRCUIT_BREAKER_MAX}x dlm ${Math.round(CIRCUIT_BREAKER_WINDOW_MS / 1000)}s). Ditahan sementara.`,
        });
      }

      await orca.host.call('notifications.show', {
        title: 'Akun Dirotasi',
        body: `Beralih ke ${target.email}.`,
      });

      // Settle delay before resuming terminal
      await new Promise((resolve) => setTimeout(resolve, SETTLE_DELAY_MS));

      // Auto-resume active terminal
      const termsData = await runOrcaCommand(['terminal', 'list', '--json']);
      const terms = (termsData && termsData.result && termsData.result.terminals) || [];
      const writableTerms = terms.filter((t) => t.connected && t.writable);

      function isAgentTerminal(t) {
        const identity = (t.agentIdentity || '').toLowerCase();
        const text = `${t.title || ''} ${t.preview || ''}`.toLowerCase();

        // Must not be another external agent like OMP or Codex
        if (identity && identity !== 'antigravity') return false;

        return identity === 'antigravity' ||
          text.includes('antigravity') ||
          (text.includes('gemini') && !text.includes('gpt-'));
      }

      let targetTerm = null;

      // Respect target_terminal from config if specified
      if (TARGET_TERMINAL_CONFIG) {
        targetTerm = writableTerms.find((t) => t.handle === TARGET_TERMINAL_CONFIG || t.id === TARGET_TERMINAL_CONFIG);
        if (!targetTerm) {
          orca.log(`Configured target_terminal '${TARGET_TERMINAL_CONFIG}' not found or not writable.`);
        }
      }

      // If no valid target_terminal from config, pick only from terminals that pass isAgentTerminal
      if (!targetTerm) {
        const agentTerms = writableTerms.filter(isAgentTerminal);
        if (agentTerms.length > 0) {
          agentTerms.sort((a, b) => (b.lastOutputAt || 0) - (a.lastOutputAt || 0));
          targetTerm = agentTerms[0];
        }
      }

      if (targetTerm) {
        await orca.host.call('terminal.sendText', {
          terminalId: targetTerm.handle,
          text: RESUME_COMMAND,
          enter: true,
        });
        orca.log(`Auto-resume sent to agent terminal ${targetTerm.handle}`);
      } else {
        orca.log('Auto-resume skipped: no active Antigravity agent terminal found.');
        await orca.host.call('notifications.show', {
          title: 'Auto-Resume Dilewati',
          body: 'Tidak ditemukan terminal agen Antigravity aktif untuk dilanjutkan.',
        });
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
        const agentId = (event.agentIdentity || event.agent || event.title || '').toLowerCase();
        // Ignore events from other agents like codex, omp, etc.
        if (agentId && !agentId.includes('antigravity') && !agentId.includes('gemini') && (agentId.includes('omp') || agentId.includes('codex'))) {
          return;
        }

        orca.log(`Antigravity agent blocked: ${event.title || 'agent'}. Checking quota...`);
        const state = await fetchAccountsData();
        if (state && state.activeAccount && state.activeAccount.isExhausted) {
          await rotateToBestAccount('Agen Antigravity terhenti karena limit kuota');
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
      return await computeTokenTelemetry();
    });

    orca.panels.handle('accounts.rotateNow', async () => {
      return rotateToBestAccount('Triggered from UI panel');
    });

    orca.panels.handle('accounts.selectTarget', async (input) => {
      const target = (input && input.target) || input;
      if (!target) return { success: false, reason: 'Target missing' };
      orca.log(`Selecting account requested: ${target}`);
      const res = await runOrcaCommand(['account', 'select', '--agent', 'antigravity', '--account', target, '--json'], (msg) => orca.log(msg));
      lastSwitchTime = Date.now();

      // Short settle time for Orca account manager state to persist
      await new Promise((r) => setTimeout(r, 400));

      const state = await fetchAccountsData();
      if (state) {
        await updateStatusBar(state.activeAccount, state.activeSession?.model);
        if (orca.panels && orca.panels.post) {
          orca.panels.post('accounts.changed', state);
        }
      }
      return { success: true, result: res };
    });

    orca.panels.handle('mask.set', async (input) => {
      const val = Boolean(input && (input.masked !== undefined ? input.masked : input));
      isMasked = val;
      saveMaskState(isMasked);
      const state = await fetchAccountsData();
      if (state && state.activeAccount) {
        await updateStatusBar(state.activeAccount, state.activeSession?.model);
      }
      return { success: true, masked: isMasked };
    });

    orca.panels.handle('mask.get', async () => {
      return { masked: isMasked };
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

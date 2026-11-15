# Orca ADE Antigravity Auto-Switcher

> [!CAUTION]
> **DISCLAIMER & TERMS NOTICE**
> - **No Request Proxying & No Credential Storage:** This tool does not proxy requests or redirect network traffic, nor does it store, intercept, or manage user credentials. It only invokes the local `orca` CLI and reads local system status and log files.
> - **Terms of Service Compliance:** Automated account switching to circumvent quota limits may violate service provider Terms of Service (including Google Antigravity Additional Terms). This tool does not guarantee immunity from policy enforcement, quota restrictions, or account actions.
> - **Intended Usage:** Use solely with your own legitimately acquired paid accounts. All usage is at your own risk.
> - **Non-Affiliation:** This project is an independent community utility and is not affiliated with, endorsed by, or sponsored by Google or Orca.

Background failover daemon and native Orca ADE v2 plugin for automated account rotation and session continuation on the Antigravity (`antigravity`) agent runtime.

---

## Technical Background

In Orca ADE, multi-account authentication for the Antigravity agent is managed through the `orca account` subsystem:
- `orca account list --agent antigravity --json`: Reports registered accounts along with session and weekly quota consumption metrics (`usedPercent`).
- `orca account select --agent antigravity --account <id|email>`: Selects the active account used for subsequent agent invocations on the host.

Orca ADE does not provide native automatic account failover. When an active Antigravity account reaches its API quota or returns a rate limit error (`HTTP 429 Too Many Requests` or `RESOURCE_EXHAUSTED`):
1. Execution halts in the active terminal session.
2. The user must manually query `orca account list` to locate an account with available quota.
3. The user must execute `orca account select` to re-bind the host credentials.
4. The user must manually submit a prompt to the active agent terminal to resume execution.

This project implements an automated, event-driven supervisor that handles rate-limit detection, account rotation, credential synchronization, and terminal session re-triggering without manual intervention.

---

## System Architecture

```text
+--------------------------------------------------------------------------------+
|                                Orca ADE Host                                   |
|                                                                                |
|  +--------------------+    NDJSON Logs    +---------------------------------+  |
|  | Active Antigravity | ----------------> | Streaming Log Watcher           |  |
|  | Terminal Session   |                   | (Line-buffered regex scanner)   |  |
|  +--------------------+                   +---------------------------------+  |
|            ^                                               |                   |
|            | Resume Command                                v                   |
|            | ("lanjutkan pengerjaan")     +---------------------------------+  |
|            +----------------------------- | Failover & Safety Controller    |  |
|            |                              | - Cooldown gate (30s)           |  |
|            | Settle Delay (2.0s)          | - Sliding-window circuit breaker|  |
|            |                              | - PID file lock enforcement     |  |
|  +--------------------+                   +---------------------------------+  |
|  | Host Keyring       | <----------------                  |                   |
|  | Credential Store   |   orca account select              v                   |
|  +--------------------+                   +---------------------------------+  |
|            ^                              | Account Manager & Quota Ranker  |  |
|            |                              | - Reads session/weekly usage    |  |
|            +----------------------------- | - Selects lowest % used (0%)    |  |
|                   orca account list --json+---------------------------------+  |
+--------------------------------------------------------------------------------+
```

### Operational Workflow
1. **Detection (Daemon vs Plugin Differences):**
   - **Python Daemon:** Combines reactive and proactive scanning. Continuously monitors host log streams (`~/.config/orca/logs/main.trace.ndjson`, `daemon.log`, ACP brain transcripts) for `RESOURCE_EXHAUSTED`, `HTTP 429 Too Many Requests`, and quota limit patterns, in addition to background polling.
   - **Orca Plugin (`src/worker.mjs`):** Operates within Orca's extension sandbox without raw log file access. It detects quota exhaustion strictly via periodic polling of `orca account list --agent antigravity --json` and runtime event subscriptions (`agent.status.changed`, `agent.activity.changed`).
2. **Account Selection:**
   - Accounts are ranked by available quota using Orca's native integer scale (`usedPercent: 0-100`).
   - Prioritizes accounts with `usedPercent == 0` for both session and weekly windows.
   - If all accounts are exhausted, computes the shortest reset epoch (`resetsAt`) and holds execution safely until the nearest reset window opens.
3. **Failover Execution:**
   - Invokes `orca account select --agent antigravity --account <target_id>` via IPC.
   - Applies a configurable 2.0-second settle delay to allow OS keyring credential flush.
4. **Session Continuation:**
   - Resolves the active, writable agent terminal handle via `orca terminal list --json`.
   - Dispatches a continuation trigger (`orca terminal send --terminal <id> --text "lanjutkan pengerjaan tadi" --enter`) to resume autonomous execution.
5. **Safety Guardrails:**
   - **Cooldown:** Enforces a minimum interval (default: 30 seconds) between switch operations.
   - **Circuit Breaker:** Halts rotation and issues a system notification if switch frequency exceeds 5 transitions within 180 seconds.
   - **Process Lock:** Single-instance concurrency control via `/tmp/orca-agy-rotator.lock`.

---

## Components

The repository provides two deployment targets that can run independently or in tandem:

### 1. Linux Systemd User Daemon (`rotator/`)
- Pure Python 3.10+ service utilizing standard library modules (zero external dependencies).
- Runs under `systemd --user` as a persistent background supervisor.
- Real-time NDJSON log streaming and brain transcript regex scanner detecting `RESOURCE_EXHAUSTED` / `HTTP 429` errors.
- Provides interactive terminal monitoring (`main.py live`) and CLI operational controls.

### 2. Native Orca ADE Plugin v2 (`orca-plugin.json`)
- Conforms to Orca ADE Plugin Manifest v2 schema (`execution: "trusted-worker"`).
- Background worker (`src/worker.mjs`) monitoring quota and workspace status via polling (`orca account list`) and ADE runtime events (`agent.status.changed`).
- Native sliding-window circuit breaker (5 switches in 180s) and cooldown protections.
- Sidebar UI panel (`panel/index.html`) using native Orca design tokens (`var(--orca-*)`).
- Token telemetry with rough cost estimation (configurable assumptions) and cached stream parsing.
- Status bar item displaying real-time active account quota.
- Built-in Privacy Mask toggle to sanitize account identifiers for screencasts.

---

## Platform Compatibility & Installation

### Supported Environments
- **Native Orca ADE Plugin:** **Cross-Platform** (Linux, macOS, Windows / WSL). Runs directly inside Orca ADE's runtime environment via Node.js `trusted-worker` and standard Orca host APIs (`notifications.show`, `terminal.sendText`).
- **Python Daemon & CLI:** Linux (systemd user daemon), macOS (launchd / foreground CLI), and Windows (WSL / standard Python 3.10+).

### Prerequisites
- Python 3.10 or newer (Standard library only; zero external pip dependencies)
- Orca ADE (`>= 1.4.248`) with authenticated Antigravity accounts (`orca account add`)
- Desktop notifications: `notify-send` (Linux) or native AppleScript (`osascript`, macOS)

### Method A: Native Orca ADE Plugin

1. Clone repository:
   ```bash
   git clone https://github.com/Syharipf/orca-agy-rotator.git
   cd orca-agy-rotator
   ```

2. Validate manifest:
   ```bash
   orca plugin validate .
   ```

3. Load plugin in development mode:
   ```bash
   orca plugin dev load .
   ```

4. Open the panel in Orca:
   ```bash
   orca plugin open local.antigravity-rotator
   ```

### Method B: Linux Systemd User Service

1. Register and enable the systemd service:
   ```bash
   ./main.py install-service
   ```

2. Verify operational status:
   ```bash
   systemctl --user status orca-agy-rotator.service
   ```

3. View real-time service logs:
   ```bash
   journalctl --user -u orca-agy-rotator.service -f
   ```

To uninstall:
```bash
./main.py uninstall-service
```

---

## CLI Reference

The unified CLI entrypoint `main.py` provides system management and interactive monitoring:

```text
Usage: ./main.py [COMMAND] [OPTIONS]

Commands:
  status               Display daemon status, active quota, and active terminal handles
  accounts             List registered accounts ranked by quota usage
  accounts --mask      List accounts with email masking enabled
  live                 Launch interactive real-time terminal UI (TUI)
  switch               Trigger immediate rotation to lowest-usage candidate
  switch <account>     Switch explicitly to a designated account ID or email
  switch --dry-run     Simulate candidate evaluation without switching keyring
  resume --dry-run     Test active terminal detection and resume formatting
  test-notify          Send a test desktop notification
  run                  Run supervisor in foreground (debug mode)
  install-service      Register and start systemd user service
  uninstall-service    Stop and unregister systemd user service
```

### Live TUI Monitor Sample
```text
===============================================================================================
 STATUS         | EMAIL [PRIVACY MASK: ON]           | SESSION    | WEEKLY     | RESET TIME
===============================================================================================
 ▶ ● IN USE     | dev-lead@example.com               | 12%        | 4%         | 23:09:59 (109m)
  ╰─ Target sesi: Terminal 1 · main.py (Akun aktif untuk sesi ini)
   ○ READY      | worker-alpha@example.com           | 0%         | 0%         | 23:25:32 (124m)
===============================================================================================
[Hotkeys] (r) Rotate Best  |  (m) Toggle Mask  |  (1-2) Direct Switch  |  (q) Exit
```

---

## Configuration

Service parameters are defined in `config.json`:

```json
{
  "log_check_interval": 1.0,
  "quota_check_interval": 20.0,
  "cooldown_seconds": 30.0,
  "circuit_breaker_max_switches": 5,
  "circuit_breaker_window_seconds": 180.0,
  "rotation_strategy": "smart_quota",
  "auto_resume": true,
  "resume_delay_seconds": 2.0,
  "resume_command": "lanjutkan pengerjaan tadi",
  "target_terminal": null,
  "notifications_enabled": true,
  "notification_app_name": "Orca ADE Rotator"
}
```

### Field Definitions

| Parameter | Type | Default | Description |
|---|---|---|---|
| `log_check_interval` | float | `1.0` | Polling frequency for streaming log files (seconds) |
| `quota_check_interval` | float | `20.0` | Interval for proactive CLI quota evaluation (seconds) |
| `cooldown_seconds` | float | `30.0` | Minimum elapsed time required between consecutive rotations |
| `circuit_breaker_max_switches` | int | `5` | Maximum permitted transitions within window before trip |
| `circuit_breaker_window_seconds`| float | `180.0` | Sliding window duration for circuit breaker evaluation |
| `rotation_strategy` | string | `"smart_quota"` | `"smart_quota"` (lowest usage first) or `"round_robin"` |
| `auto_resume` | bool | `true` | Enables automatic prompt transmission to active terminal |
| `resume_delay_seconds` | float | `2.0` | Post-switch delay prior to terminal prompt injection |
| `resume_command` | string | `"lanjutkan pengerjaan tadi"` | Payload string injected into the terminal session |
| `target_terminal` | string/null | `null` | Explicit terminal handle or `null` for automated detection |
| `notifications_enabled` | bool | `true` | Dispatches desktop alerts via `notify-send` |

---

## Verification & Test Suite

The test suite exercises account selection, quota ranking, cooldown constraints, circuit breaker limits, streaming pattern detection, and terminal prioritization:

```bash
python3 test_rotator.py
```

Test output:
```text
Ran 8 tests in 0.006s

OK
```

### Test Coverage
- `test_quota_percentage_scale_is_already_percent`: Asserts that session and weekly quotas are treated natively as 0-100% values without redundant multiplication.
- `test_smart_quota_candidate_selection`: Validates 0% usage selection over partially consumed accounts.
- `test_all_accounts_exhausted_scenario`: Verifies correct fallback calculation and earliest reset timestamp resolution.
- `test_round_robin_selection`: Validates sequential cycling when round-robin strategy is selected.
- `test_cooldown_enforcement`: Asserts that rotation requests within the cooldown window are rejected.
- `test_circuit_breaker_trip`: Asserts that exceeding switch velocity trips the breaker and locks rotation.
- `test_rate_limit_detection`: Verifies regex pattern detection across simulated log streams.
- `test_terminal_selection_priority`: Asserts that writable Antigravity sessions take priority over generic terminals.

---

## Security & Isolation

- **Keyring Delegation:** Credentials are never cached, logged, or managed directly by this tool. Account switching relies exclusively on the `orca account select` CLI invocation delegating to system keyring stores.
- **Privacy Masking:** The `--mask` CLI flag and UI toggle replace real email addresses with deterministic dummy identifiers, ensuring safety during video capture and public demonstrations.
- **Privacy & Local Telemetry:** Token telemetry calculations strictly read local `transcript.jsonl` files on the host machine. Only token count metrics are parsed to aggregate session usage; user prompts, thoughts, transcripts, and source code are never uploaded, captured, or transmitted.
- **Unprivileged Execution:** Operates entirely within standard user permissions (`systemd --user`). Root privileges are not required.

---

## License

This project is licensed under the MIT License. See `LICENSE` for details.

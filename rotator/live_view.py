"""Interactive Live TUI Monitor for Orca Antigravity accounts."""

import datetime
import os
import select
import sys
import termios
import time
import tty
from typing import Optional

from .account_manager import AccountManager, format_ms_timestamp
from .config import RotatorConfig
from .terminal_manager import TerminalManager


# ANSI Color Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
BRIGHT_GREEN = "\033[1;32m"
CYAN = "\033[36m"
BRIGHT_CYAN = "\033[1;36m"
RED = "\033[31m"
BRIGHT_RED = "\033[1;31m"
YELLOW = "\033[33m"
GRAY = "\033[90m"
BG_DARK = "\033[48;5;234m"
BG_ACTIVE = "\033[48;5;236m"


def format_progress_bar(used_pct: float, width: int = 8) -> str:
    val = used_pct / 100.0 if used_pct > 1.0 else used_pct
    clamped = min(1.0, max(0.0, val))
    filled = int(clamped * width)
    unfilled = width - filled
    if clamped >= 1.0:
        bar = f"{RED}{'█' * filled}{RESET}"
    elif clamped >= 0.7:
        bar = f"{YELLOW}{'█' * filled}{GRAY}{'·' * unfilled}{RESET}"
    else:
        bar = f"{GREEN}{'█' * filled}{GRAY}{'·' * unfilled}{RESET}"
    return f"[{bar}]"


DUMMY_POOL = [
    "dev-lead@example.com",
    "worker-alpha@example.com",
    "runner-beta@example.com",
    "agent-gamma@example.com",
    "backup-ops@example.com",
    "standby-pool@example.com",
]


def run_live_monitor(config: RotatorConfig, mask: bool = False):
    """Runs a continuous real-time interactive terminal monitor with live hotkeys."""
    mgr = AccountManager()
    term_mgr = TerminalManager()
    is_masked = mask

    # Save original terminal settings for raw mode
    old_settings = None
    if sys.stdin.isatty():
        try:
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        except Exception:
            pass

    status_toast = ""
    status_toast_time = 0.0

    try:
        # Hide cursor
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        while True:
            # 1. Fetch live data
            accounts, active_id, active_account = mgr.fetch_accounts()
            active_term = term_mgr.find_active_terminal(target_handle=config.target_terminal)

            total_acc = len(accounts)
            avail_acc = sum(1 for a in accounts if not a.is_exhausted)
            health_pct = int((avail_acc / total_acc * 100)) if total_acc > 0 else 0

            # Detect active model
            model_name = "Gemini Models (Antigravity)"
            session_title = active_term.title if active_term else "Standby (No active session)"
            if is_masked:
                session_title = "Terminal 1 · main.py"
            elif active_term and active_term.preview:
                import re
                m = re.search(r"(?:Argon(?:\s+[a-z0-9\.-]+)?|Carbon(?:\s+[a-z0-9\.-]+)?|Gemini\s+[0-9\.]+(?:\s+[a-z]+)?|GPT-[0-9\.]+(?:\s+[a-z]+)?|Claude\s+[0-9\.]+(?:\s+[a-z]+)?|o[13](?:-mini|-preview)?|DeepSeek-[a-z0-9\.-]+)", active_term.preview, re.I)
                if m:
                    model_name = m.group(0).strip()

            now_str = datetime.datetime.now().strftime("%H:%M:%S")
            mask_badge = f"{GREEN}[MASK: ON]{RESET}" if is_masked else f"{GRAY}[MASK: OFF]{RESET}"

            # 2. Render Screen Buffer
            out = []
            # Home cursor
            out.append("\033[H")

            # Header Banner
            out.append(f"{BOLD}┌────────────────────────────────────────────────────────────────────────────────────────┐{RESET}")
            out.append(f"{BOLD}│  {BRIGHT_GREEN}●{RESET}{BOLD} Orca ADE Antigravity Auto-Switcher · {BRIGHT_CYAN}LIVE MONITOR{RESET}  {mask_badge}          {GRAY}{now_str}{RESET}{BOLD}  │{RESET}")
            out.append(f"{BOLD}│  Model: {BRIGHT_CYAN}{model_name:<26}{RESET}{BOLD} │ Pool: {GREEN}{avail_acc}/{total_acc} Siap ({health_pct}%){RESET}{BOLD} │ PID: {os.getpid():<10}{BOLD} │{RESET}")
            out.append(f"{BOLD}└────────────────────────────────────────────────────────────────────────────────────────┘{RESET}\n")

            # Table Header
            out.append(f"  {GRAY}{'STATUS':<11} {'ID':<9} {'ACCOUNT EMAIL':<33} {'SESSION':<17} {'WEEKLY':<10} {'RESET':<18}{RESET}")
            out.append(f"  {GRAY}{'─' * 98}{RESET}")

            # Accounts Loop
            for idx, acc in enumerate(accounts, 1):
                is_active = (acc.id == active_id)
                short_id = acc.id[:8]

                display_email = DUMMY_POOL[(idx - 1) % len(DUMMY_POOL)] if is_masked else acc.email

                session_used = acc.session_used
                weekly_used = acc.weekly_used
                session_pct = f"{int(session_used)}%"
                weekly_pct = f"{int(weekly_used)}%"
                session_bar = format_progress_bar(session_used / 100.0, width=6)
                reset_str = format_ms_timestamp(acc.earliest_reset_timestamp)

                if is_active:
                    status_badge = f"{BRIGHT_GREEN}● IN USE{RESET} "
                    prefix = f"{BRIGHT_GREEN}▶{RESET} "
                    email_styled = f"{BOLD}{display_email}{RESET}"
                elif acc.is_exhausted:
                    status_badge = f"{RED}✕ LIMIT {RESET} "
                    prefix = "  "
                    email_styled = f"{GRAY}{display_email}{RESET}"
                else:
                    status_badge = f"{CYAN}○ READY {RESET} "
                    prefix = "  "
                    email_styled = f"{display_email}"

                num_prefix = f"{GRAY}[{idx}]{RESET} "
                row = f"{prefix}{num_prefix}{status_badge} {short_id:<8} {email_styled:<32} {session_pct:>4} {session_bar}   {weekly_pct:>4}     {GRAY}{reset_str}{RESET}"
                out.append(row)

                if is_active:
                    routing_line = f"      {GRAY}╰─{RESET} {GREEN}Target sesi:{RESET} {BOLD}{session_title[:50]}{RESET}"
                    out.append(routing_line)

            out.append(f"  {GRAY}{'─' * 98}{RESET}")

            # Toast message if any
            if status_toast and (time.time() - status_toast_time < 3.5):
                out.append(f"  {YELLOW}⚡ {status_toast}{RESET}")
            else:
                out.append("  " + " " * 80)

            # Footer Hotkeys
            out.append(f"\n  {BOLD}Kontrol Cepat:{RESET} [{GREEN}r{RESET}] Rotasi  │  [{YELLOW}m{RESET}] Toggle Mask  │  [{CYAN}1-{total_acc}{RESET}] Pilih Akun  │  [{RED}q{RESET}] Tutup")
            out.append("\033[J")  # Clear remaining lines below

            sys.stdout.write("\n".join(out))
            sys.stdout.flush()

            # 3. Check for keyboard input non-blocking (poll 1 second)
            r, _, _ = select.select([sys.stdin], [], [], 1.0)
            if r:
                ch = sys.stdin.read(1)
                if ch.lower() in ["q", "\x03", "\x1b"]:  # 'q', Ctrl+C, Esc
                    break
                elif ch.lower() == "m":
                    is_masked = not is_masked
                    status_toast = "Privacy Mask AKTIF (Akun dummy)" if is_masked else "Privacy Mask NONAKTIF (Akun asli)"
                    status_toast_time = time.time()
                elif ch.lower() == "r":
                    status_toast = "Mencari akun terbaik & merotasi..."
                    status_toast_time = time.time()
                    candidate, reason, _ = mgr.find_best_candidate(strategy="smart_quota")
                    if candidate:
                        mgr.switch_account(candidate)
                        target_name = DUMMY_POOL[0] if is_masked else candidate.email
                        status_toast = f"Berhasil beralih ke: {target_name}"
                    else:
                        status_toast = f"Rotasi ditahan: {reason}"
                    status_toast_time = time.time()
                elif ch.isdigit() and 1 <= int(ch) <= len(accounts):
                    target = accounts[int(ch) - 1]
                    target_name = DUMMY_POOL[int(ch) - 1] if is_masked else target.email
                    status_toast = f"Beralih ke: {target_name}..."
                    status_toast_time = time.time()
                    mgr.switch_account(target)
                    status_toast = f"Aktif sekarang: {target_name}"
                    status_toast_time = time.time()

    finally:
        # Restore cursor and terminal settings
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()
        if old_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            except Exception:
                pass

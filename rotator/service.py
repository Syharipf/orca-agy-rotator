"""Central daemon service orchestrating log monitoring, smart rotation, and auto-resume."""

import logging
import signal
import sys
import time
from typing import Optional

from .account_manager import AccountManager, AccountInfo
from .config import RotatorConfig
from .monitor import LogMonitor, RateLimitEvent
from .notifier import Notifier
from .safety import SafetyManager, SingleInstanceLock, LockError
from .terminal_manager import TerminalManager


logger = logging.getLogger("orca_rotator.service")


class RotatorDaemon:
    def __init__(self, config: RotatorConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.running = False

        self.notifier = Notifier(
            enabled=config.notifications_enabled,
            app_name=config.notification_app_name,
        )
        self.lock = SingleInstanceLock(lock_path=config.lock_file)
        self.safety = SafetyManager(
            cooldown_seconds=config.cooldown_seconds,
            max_switches_in_window=config.circuit_breaker_max_switches,
            window_seconds=config.circuit_breaker_window_seconds,
        )
        self.account_mgr = AccountManager()
        self.terminal_mgr = TerminalManager()
        self.log_monitor = LogMonitor(
            log_files=config.log_files,
            patterns=config.rate_limit_patterns,
            monitor_brain=config.monitor_brain_transcripts,
            brain_dir=config.brain_dir,
        )

        self._last_quota_check: float = 0.0
        self._circuit_breaker_alerted: bool = False

    def _setup_signal_handlers(self):
        def handler(sig, frame):
            logger.info(f"Menerima signal {sig}. Menghentikan daemon...")
            self.running = False

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def trigger_rotation(self, trigger_reason: str):
        """Executes the rotation workflow."""
        can_switch, wait_reason = self.safety.can_switch()
        if not can_switch:
            if self.safety.is_circuit_breaker_tripped and not self._circuit_breaker_alerted:
                self.notifier.notify_circuit_breaker(
                    self.safety.max_switches_in_window,
                    self.safety.window_seconds,
                )
                self._circuit_breaker_alerted = True
            logger.info(f"Pergantian akun ditahan: {wait_reason}")
            return

        # Reset circuit breaker alert flag if cooldown passed
        self._circuit_breaker_alerted = False

        # 1. Fetch accounts and current active account
        accounts, active_id, active_account = self.account_mgr.fetch_accounts()
        old_email = active_account.email if active_account else (active_id or "Unknown")

        # 2. Pick candidate
        candidate, reason_code, reset_info = self.account_mgr.find_best_candidate(
            strategy=self.config.rotation_strategy
        )

        if reason_code == "all_exhausted":
            reset_str = reset_info.get("human_readable") if reset_info else None
            self.notifier.notify_all_exhausted(earliest_reset_info=reset_str)
            logger.warning(f"Semua akun Antigravity limit. Reset terdekat: {reset_str}")
            return

        if not candidate:
            logger.warning(f"Tidak dapat menemukan akun pengganti yang valid (alasan: {reason_code}).")
            return

        # 3. Perform switch
        logger.info(
            f"Melakukan rotasi akun dari {old_email} -> {candidate.email} (Alasan: {trigger_reason})"
        )
        success = self.account_mgr.switch_account(candidate, dry_run=self.dry_run)
        if not success:
            logger.error("Gagal mengganti akun melalui Orca CLI.")
            return

        # 4. Record switch in safety manager
        self.safety.record_switch(old_email, candidate.email)
        self.notifier.notify_switch(
            old_email=old_email,
            new_email=candidate.email,
            reason=trigger_reason,
            dry_run=self.dry_run,
        )

        # 5. Settle delay before resuming terminal
        if self.config.resume_delay_seconds > 0:
            logger.info(f"Menunggu {self.config.resume_delay_seconds}s agar kredensial OS keyring tersimpan...")
            time.sleep(self.config.resume_delay_seconds)

        # 6. Auto-resume terminal
        if self.config.auto_resume:
            terminal = self.terminal_mgr.find_active_terminal(
                target_handle=self.config.target_terminal
            )
            if terminal:
                logger.info(
                    f"Ditemukan terminal aktif: {terminal.handle} ({terminal.title or 'Tanpa judul'})"
                )
                self.terminal_mgr.send_resume(
                    terminal_handle=terminal.handle,
                    text=self.config.resume_command,
                    dry_run=self.dry_run,
                )
                self.notifier.notify_resume(terminal.handle, self.config.resume_command)
            else:
                logger.info(
                    "Tidak ada terminal aktif yang ditemukan untuk di-resume (bisa jadi sesi berupa inline chat)."
                )

    def run(self):
        """Main service loop."""
        try:
            self.lock.acquire()
        except LockError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

        self._setup_signal_handlers()
        self.running = True

        _, _, active_account = self.account_mgr.fetch_accounts()
        active_email = active_account.email if active_account else None
        self.notifier.notify_service_started(active_email=active_email)

        logger.info(
            f"Orca ADE Antigravity Rotator berjalan (Strategi: {self.config.rotation_strategy}, Dry-run: {self.dry_run})"
        )

        try:
            while self.running:
                now = time.time()

                # Step 1: Check log files and transcripts for rate limit error lines
                events = self.log_monitor.check_for_rate_limits()
                if events:
                    first_event = events[0]
                    trigger_msg = f"Log match [{first_event.pattern}] pada {first_event.source}"
                    self.trigger_rotation(trigger_reason=trigger_msg)

                # Step 2: Periodic direct quota check from Orca account API
                if now - self._last_quota_check >= self.config.quota_check_interval:
                    self._last_quota_check = now
                    try:
                        _, _, cur_active = self.account_mgr.fetch_accounts()
                        if cur_active and cur_active.is_exhausted:
                            trigger_msg = (
                                f"Kuota akun aktif {cur_active.email} habis "
                                f"(Session: {int(cur_active.session_used * 100)}%, Weekly: {int(cur_active.weekly_used * 100)}%)"
                            )
                            self.trigger_rotation(trigger_reason=trigger_msg)
                    except Exception as e:
                        logger.debug(f"Error checking active quota: {e}")

                time.sleep(self.config.log_check_interval)

        finally:
            self.running = False
            self.lock.release()
            self.notifier.notify_service_stopped()
            logger.info("Daemon Orca ADE Rotator telah berhenti dengan aman.")

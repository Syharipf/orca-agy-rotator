"""Desktop notifications and logging helper."""

import datetime
import logging
import os
import shutil
import subprocess
from typing import Optional


# Setup basic logger
logger = logging.getLogger("orca_rotator")


class Notifier:
    def __init__(self, enabled: bool = True, app_name: str = "Orca ADE Rotator"):
        self.enabled = enabled
        self.app_name = app_name
        self._notify_send_bin = shutil.which("notify-send")
        self._osascript_bin = shutil.which("osascript")

    def _send(self, title: str, message: str, urgency: str = "normal", icon: str = "dialog-information"):
        # Log to stdout/log file always
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{urgency.upper()}] {title}: {message}")
        print(f"[{timestamp}] [{title}] {message}")

        if not self.enabled:
            return

        import sys
        # macOS Notification via AppleScript
        if sys.platform == "darwin" and self._osascript_bin:
            clean_title = title.replace('"', '\\"')
            clean_msg = message.replace('"', '\\"').replace('\n', ' ')
            script = f'display notification "{clean_msg}" with title "{clean_title}"'
            try:
                subprocess.run([self._osascript_bin, "-e", script], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception as e:
                logger.debug(f"Failed to execute osascript: {e}")

        # Linux Notification via notify-send
        if self._notify_send_bin:
            env = dict(os.environ)
            if "DISPLAY" not in env:
                env["DISPLAY"] = ":0"
            if "DBUS_SESSION_BUS_ADDRESS" not in env:
                uid = os.getuid() if hasattr(os, "getuid") else 1000
                env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"

            cmd = [
                self._notify_send_bin,
                "-a", self.app_name,
                "-u", urgency,
                "-i", icon,
                title,
                message
            ]

            try:
                subprocess.run(cmd, env=env, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.debug(f"Failed to execute notify-send: {e}")

    def notify_switch(self, old_email: str, new_email: str, reason: str, dry_run: bool = False):
        prefix = "[DRY-RUN] " if dry_run else ""
        title = f"{prefix}Akun Dirotasi"
        msg = f"Beralih ke: {new_email}"
        self._send(title, msg, urgency="normal", icon="dialog-ok")

    def notify_all_exhausted(self, earliest_reset_info: Optional[str] = None):
        title = "Semua Akun Limit"
        reset_txt = f" (Reset: {earliest_reset_info})" if earliest_reset_info else ""
        msg = f"Semua kuota habis{reset_txt}. Rotasi dijeda."
        self._send(title, msg, urgency="critical", icon="dialog-warning")

    def notify_circuit_breaker(self, count: int, window_sec: float):
        title = "Rotasi Ditahan"
        msg = f"Batas pergantian tercapai ({count}x). Ditahan sementara."
        self._send(title, msg, urgency="critical", icon="dialog-error")

    def notify_resume(self, terminal_id: str, prompt: str):
        title = "Melanjutkan Pengerjaan"
        msg = f"Sesi terminal {terminal_id} otomatis dilanjutkan."
        self._send(title, msg, urgency="low", icon="media-playback-start")

    def notify_service_started(self, active_email: Optional[str] = None):
        title = "Antigravity Rotator Aktif"
        msg = f"Akun aktif: {active_email or 'Memeriksa...'}"
        self._send(title, msg, urgency="low", icon="dialog-information")

    def notify_service_stopped(self):
        title = "Antigravity Rotator Berhenti"
        msg = "Service dihentikan."
        self._send(title, msg, urgency="low", icon="process-stop")

    def notify_error(self, err_msg: str):
        title = "Orca Rotator Error"
        self._send(title, err_msg, urgency="normal", icon="dialog-error")

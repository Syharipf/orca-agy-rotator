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

    def _send(self, title: str, message: str, urgency: str = "normal", icon: str = "dialog-information"):
        # Log to stdout/log file always
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{urgency.upper()}] {title}: {message}")
        print(f"[{timestamp}] [{title}] {message}")

        if not self.enabled or not self._notify_send_bin:
            return

        # Prepare env for notify-send if run under systemd
        env = dict(os.environ)
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"
        if "DBUS_SESSION_BUS_ADDRESS" not in env:
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{os.getuid()}/bus"

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
        title = f"{prefix}Rotasi Akun Antigravity"
        msg = f"Limit terdeteksi pada {old_email or 'akun aktif'}.\nBeralih ke: {new_email}\nAlasan: {reason}"
        self._send(title, msg, urgency="normal", icon="dialog-ok")

    def notify_all_exhausted(self, earliest_reset_info: Optional[str] = None):
        title = "Peringatan: Semua Akun Limit!"
        msg = "Seluruh akun Antigravity terdaftar telah mencapai limit kuota (100%)."
        if earliest_reset_info:
            msg += f"\nReset terdekat: {earliest_reset_info}"
        msg += "\nRotasi dijeda sementara untuk keamanan."
        self._send(title, msg, urgency="critical", icon="dialog-warning")

    def notify_circuit_breaker(self, count: int, window_sec: float):
        title = "Circuit Breaker Aktif!"
        msg = f"Terjadi {count} kali rotasi dalam {int(window_sec)} detik.\nRotasi ditahan sementara agar terhindar dari pemblokiran (ban)."
        self._send(title, msg, urgency="critical", icon="dialog-error")

    def notify_resume(self, terminal_id: str, prompt: str):
        title = "Auto-Resume Triggered"
        msg = f"Perintah resume dikirim ke terminal {terminal_id}:\n\"{prompt}\""
        self._send(title, msg, urgency="low", icon="media-playback-start")

    def notify_service_started(self, active_email: Optional[str] = None):
        title = "Orca ADE Rotator Aktif"
        msg = f"Daemon auto-switcher berjalan di background.\nAkun aktif: {active_email or 'Memeriksa...'}"
        self._send(title, msg, urgency="low", icon="dialog-information")

    def notify_service_stopped(self):
        title = "Orca ADE Rotator Berhenti"
        msg = "Daemon auto-switcher dihentikan."
        self._send(title, msg, urgency="low", icon="process-stop")

    def notify_error(self, err_msg: str):
        title = "Orca Rotator Error"
        self._send(title, err_msg, urgency="normal", icon="dialog-error")

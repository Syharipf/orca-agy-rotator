#!/usr/bin/env python3
"""CLI interface for Orca ADE Antigravity Auto-Switcher."""

import argparse
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from rotator.account_manager import AccountManager, format_ms_timestamp
from rotator.config import RotatorConfig, DEFAULT_CONFIG_PATH
from rotator.notifier import Notifier
from rotator.service import RotatorDaemon
from rotator.terminal_manager import TerminalManager


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def cmd_run(args, config: RotatorConfig):
    if args.dry_run:
        config.auto_resume = not args.no_auto_resume
    if args.strategy:
        config.rotation_strategy = args.strategy
    if args.no_auto_resume:
        config.auto_resume = False

    daemon = RotatorDaemon(config=config, dry_run=args.dry_run)
    daemon.run()


def cmd_status(args, config: RotatorConfig):
    print("=" * 60)
    print("      Orca ADE Antigravity Auto-Switcher Status")
    print("=" * 60)

    # Check daemon lockfile
    lock_file = Path(config.lock_file)
    daemon_running = False
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            # Check if process is running
            os.kill(pid, 0)
            daemon_running = True
            print(f"Daemon Status    : AKTIF (PID: {pid})")
        except (ValueError, OSError):
            print("Daemon Status    : TIDAK AKTIF (Stale lockfile)")
    else:
        print("Daemon Status    : TIDAK AKTIF")

    # Check systemd user service
    try:
        svc_res = subprocess.run(
            ["systemctl", "--user", "is-active", "orca-agy-rotator.service"],
            capture_output=True,
            text=True,
        )
        svc_status = svc_res.stdout.strip()
        print(f"Systemd Service  : {svc_status}")
    except Exception:
        pass

    mgr = AccountManager()
    accounts, active_id, active_account = mgr.fetch_accounts()

    print("-" * 60)
    if active_account:
        print(f"Akun Aktif       : {active_account.email} (ID: {active_account.id})")
        print(f"Session Quota    : {int(active_account.session_used * 100)}% digunakan")
        print(f"Weekly Quota     : {int(active_account.weekly_used * 100)}% digunakan")
        print(f"Status Kuota     : {'HABIS / LIMIT' if active_account.is_exhausted else 'TERSEDIA'}")
        if active_account.earliest_reset_timestamp:
            print(f"Reset Terdekat   : {format_ms_timestamp(active_account.earliest_reset_timestamp)}")
    else:
        print("Akun Aktif       : Tidak dapat mendeteksi akun aktif")

    print("-" * 60)
    total_acc = len(accounts)
    available_acc = sum(1 for a in accounts if not a.is_exhausted and a.id != active_id)
    print(f"Total Akun       : {total_acc} akun")
    print(f"Akun Cadangan    : {available_acc} akun siap pakai")

    # Check terminals
    term_mgr = TerminalManager()
    terms = term_mgr.list_terminals()
    print("-" * 60)
    print(f"Terminal Terbuka : {len(terms)} terminal")
    active_term = term_mgr.find_active_terminal()
    if active_term:
        print(f"Target Resume    : {active_term.handle} ({active_term.title or 'Terminal'})")
    else:
        print("Target Resume    : Tidak ada terminal aktif")
    print("=" * 60)


def cmd_accounts(args, config: RotatorConfig):
    mgr = AccountManager()
    accounts, active_id, _ = mgr.fetch_accounts()

    if not accounts:
        print("Tidak ada akun Antigravity yang ditemukan di Orca.")
        return

    print("=" * 90)
    print(f"{'STATUS':<10} | {'EMAIL':<32} | {'SESSION':<10} | {'WEEKLY':<10} | {'RESET TERDEKAT':<20}")
    print("=" * 90)

    for acc in accounts:
        status = "[ACTIVE]" if acc.id == active_id else ("EXHAUST" if acc.is_exhausted else "READY")
        session_str = f"{int(acc.session_used * 100)}%"
        weekly_str = f"{int(acc.weekly_used * 100)}%"
        reset_str = format_ms_timestamp(acc.earliest_reset_timestamp)
        print(f"{status:<10} | {acc.email:<32} | {session_str:<10} | {weekly_str:<10} | {reset_str:<20}")

    print("=" * 90)


def cmd_switch(args, config: RotatorConfig):
    mgr = AccountManager()
    accounts, active_id, active_account = mgr.fetch_accounts()

    if args.account:
        # Match by email or ID
        target_acc = next(
            (a for a in accounts if a.email == args.account or a.id == args.account),
            None,
        )
        if not target_acc:
            print(f"Akun '{args.account}' tidak ditemukan di daftar akun Orca.")
            return
    else:
        # Auto-pick best
        candidate, reason, reset_info = mgr.find_best_candidate(strategy=config.rotation_strategy)
        if not candidate:
            if reason == "all_exhausted":
                reset_str = reset_info.get("human_readable") if reset_info else "Unknown"
                print(f"Semua akun telah mencapai limit kuota! Reset terdekat: {reset_str}")
            else:
                print(f"Tidak dapat memilih akun pengganti (alasan: {reason}).")
            return
        target_acc = candidate

    old_email = active_account.email if active_account else "Unknown"
    print(f"Beralih akun: {old_email} -> {target_acc.email}...")
    success = mgr.switch_account(target_acc, dry_run=args.dry_run)
    if success:
        print(f"Berhasil berganti ke akun {target_acc.email}!")
        if config.notifications_enabled:
            notifier = Notifier(enabled=True)
            notifier.notify_switch(old_email, target_acc.email, "Manual switch CLI", dry_run=args.dry_run)
    else:
        print("Gagal mengganti akun.")


def cmd_resume(args, config: RotatorConfig):
    term_mgr = TerminalManager()
    target_handle = args.terminal
    term = term_mgr.find_active_terminal(target_handle=target_handle)

    if not term:
        print("Tidak ada terminal aktif yang ditemukan untuk dikirimi perintah.")
        return

    text = args.text or config.resume_command
    print(f"Mengirim teks '{text}' ke terminal {term.handle} ({term.title or 'Tanpa judul'})...")
    success = term_mgr.send_resume(term.handle, text=text, dry_run=args.dry_run)
    if success:
        print("Perintah resume berhasil dikirim.")
    else:
        print("Gagal mengirim perintah resume.")


def cmd_test_notify(args, config: RotatorConfig):
    notifier = Notifier(enabled=True)
    print("Menguji desktop notification via notify-send...")
    notifier.notify_switch(
        old_email="akun-lama@example.com",
        new_email="akun-baru@example.com",
        reason="Pengujian sistem notifikasi",
    )
    print("Notifikasi pengujian telah dikirim.")


def cmd_install_service(args, config: RotatorConfig):
    project_dir = Path(__file__).resolve().parent
    python_bin = sys.executable
    service_src = project_dir / "orca-agy-rotator.service"

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    target_service_file = unit_dir / "orca-agy-rotator.service"

    # Read template and fill paths
    content = f"""[Unit]
Description=Orca ADE Antigravity Auto-Switcher Daemon
After=graphical-session.target network.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={python_bin} {project_dir / 'main.py'} run
WorkingDirectory={project_dir}
Restart=always
RestartSec=5
Environment="PATH={os.environ.get('PATH')}"
Environment="DISPLAY=:0"
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{os.getuid()}/bus"

[Install]
WantedBy=default.target
"""
    with open(target_service_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"File service ditulis ke: {target_service_file}")

    # Reload systemd and enable service
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "orca-agy-rotator.service"], check=True)
        print("Service 'orca-agy-rotator.service' berhasil diaktifkan dan dijalankan!")
        print("Periksa status dengan: systemctl --user status orca-agy-rotator.service")
    except Exception as e:
        print(f"Terjadi kesalahan saat mengaktifkan service: {e}")


def cmd_uninstall_service(args, config: RotatorConfig):
    try:
        subprocess.run(["systemctl", "--user", "stop", "orca-agy-rotator.service"], check=False)
        subprocess.run(["systemctl", "--user", "disable", "orca-agy-rotator.service"], check=False)
        target_service_file = Path.home() / ".config" / "systemd" / "user" / "orca-agy-rotator.service"
        if target_service_file.exists():
            target_service_file.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        print("Service 'orca-agy-rotator.service' berhasil dihentikan dan dihapus.")
    except Exception as e:
        print(f"Error saat uninstall service: {e}")


def main():
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path ke file konfigurasi JSON",
    )
    base_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulasi aksi (tidak benar-benar mengganti akun atau mengirim resume)",
    )

    parser = argparse.ArgumentParser(
        description="Orca ADE Antigravity Auto-Switcher Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[base_parser],
    )

    subparsers = parser.add_subparsers(dest="command", help="Perintah yang tersedia")

    # run command
    p_run = subparsers.add_parser("run", parents=[base_parser], help="Jalankan daemon rotator")
    p_run.add_argument(
        "--strategy",
        choices=["smart_quota", "round_robin"],
        help="Strategi rotasi akun",
    )
    p_run.add_argument(
        "--no-auto-resume",
        action="store_true",
        help="Nonaktifkan pengiriman trigger auto-resume ke terminal",
    )

    # status command
    subparsers.add_parser("status", parents=[base_parser], help="Lihat status daemon, akun aktif, dan terminal")

    # accounts command
    subparsers.add_parser("accounts", parents=[base_parser], help="Tampilkan daftar seluruh akun Antigravity dan kuotanya")

    # switch command
    p_switch = subparsers.add_parser("switch", parents=[base_parser], help="Ganti akun Antigravity sekarang")
    p_switch.add_argument("account", nargs="?", help="Email atau ID akun target (opsional)")

    # resume command
    p_resume = subparsers.add_parser("resume", parents=[base_parser], help="Kirim trigger resume ke terminal aktif")
    p_resume.add_argument("--terminal", "-t", help="Handle terminal tertentu")
    p_resume.add_argument("--text", help="Teks perintah resume kustom")

    # test-notify command
    subparsers.add_parser("test-notify", parents=[base_parser], help="Uji notifikasi desktop notify-send")

    # install-service command
    subparsers.add_parser("install-service", parents=[base_parser], help="Pasang dan aktifkan systemd user service")

    # uninstall-service command
    subparsers.add_parser("uninstall-service", parents=[base_parser], help="Hentikan dan copot systemd user service")

    args = parser.parse_args()

    # Load configuration
    config = RotatorConfig.load(args.config)

    # Route command
    cmd = args.command or "run"
    if cmd == "run":
        cmd_run(args, config)
    elif cmd == "status":
        cmd_status(args, config)
    elif cmd == "accounts":
        cmd_accounts(args, config)
    elif cmd == "switch":
        cmd_switch(args, config)
    elif cmd == "resume":
        cmd_resume(args, config)
    elif cmd == "test-notify":
        cmd_test_notify(args, config)
    elif cmd == "install-service":
        cmd_install_service(args, config)
    elif cmd == "uninstall-service":
        cmd_uninstall_service(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

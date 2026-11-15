"""Orca terminal discovery and resume sender."""

from dataclasses import dataclass
import json
import logging
import subprocess
from typing import List, Optional


logger = logging.getLogger("orca_rotator.terminal_manager")


@dataclass
class TerminalInfo:
    handle: str
    title: Optional[str]
    preview: Optional[str]
    worktree_path: Optional[str]
    connected: bool
    writable: bool
    last_output_at: Optional[int]
    agent_identity: Optional[str]

    @property
    def is_agent_related(self) -> bool:
        text = f"{self.title or ''} {self.preview or ''} {self.agent_identity or ''}".lower()
        agent_keywords = ["antigravity", "gemini", "agy", "model", "flash", "pro", "token"]
        return any(kw in text for kw in agent_keywords)


class TerminalManager:
    """Discovers active Orca terminals and sends auto-resume triggers."""

    def __init__(self, orca_bin: str = "orca"):
        self.orca_bin = orca_bin

    def list_terminals(self) -> List[TerminalInfo]:
        cmd = [self.orca_bin, "terminal", "list", "--json"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
        except Exception as e:
            logger.error(f"Gagal membaca daftar terminal Orca: {e}")
            return []

        result_data = data.get("result", {}) or {}
        raw_terminals = result_data.get("terminals", [])

        terminals: List[TerminalInfo] = []
        for item in raw_terminals:
            t = TerminalInfo(
                handle=item.get("handle", ""),
                title=item.get("title"),
                preview=item.get("preview"),
                worktree_path=item.get("worktreePath"),
                connected=bool(item.get("connected", False)),
                writable=bool(item.get("writable", False)),
                last_output_at=item.get("lastOutputAt"),
                agent_identity=item.get("agentIdentity"),
            )
            terminals.append(t)

        return terminals

    def find_active_terminal(self, target_handle: Optional[str] = None) -> Optional[TerminalInfo]:
        """
        Finds the best terminal to resume.
        If target_handle is specified, attempts to find that exact terminal.
        Otherwise selects the most recently active writable terminal, prioritizing agent sessions.
        """
        terminals = self.list_terminals()
        if not terminals:
            return None

        if target_handle:
            for t in terminals:
                if t.handle == target_handle:
                    return t
            logger.warning(f"Terminal target {target_handle} tidak ditemukan di daftar terminal aktif.")

        # Filter only connected and writable terminals
        valid_terminals = [t for t in terminals if t.connected and t.writable]
        if not valid_terminals:
            return None

        # Sort criteria:
        # 1. Is agent related (antigravity / gemini / session)
        # 2. Most recent last_output_at
        def sort_key(t: TerminalInfo):
            is_agent = 1 if t.is_agent_related else 0
            ts = t.last_output_at or 0
            return (is_agent, ts)

        valid_terminals.sort(key=sort_key, reverse=True)
        return valid_terminals[0]

    def send_resume(
        self,
        terminal_handle: str,
        text: str = "lanjutkan pengerjaan tadi",
        dry_run: bool = False,
    ) -> bool:
        """
        Executes: `orca terminal send --terminal <handle> --text "<text>" --enter --json`
        """
        cmd = [
            self.orca_bin,
            "terminal",
            "send",
            "--terminal",
            terminal_handle,
            "--text",
            text,
            "--enter",
            "--json",
        ]

        if dry_run:
            logger.info(f"[DRY-RUN] Would send resume trigger to {terminal_handle}: '{text}'")
            return True

        logger.info(f"Mengirim trigger resume ke terminal {terminal_handle}...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Trigger resume berhasil dikirim ke {terminal_handle}.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Gagal mengirim trigger resume ke {terminal_handle}: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error mengirim resume ke {terminal_handle}: {e}")
            return False

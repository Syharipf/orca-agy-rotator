"""Log file monitor and pattern detector."""

from dataclasses import dataclass
import glob
import logging
import os
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple


logger = logging.getLogger("orca_rotator.monitor")


@dataclass
class RateLimitEvent:
    source: str
    matched_text: str
    pattern: str


class FileWatcher:
    """Tracks byte offset and inode of an individual file to read only new appended bytes."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.last_offset: int = 0
        self.last_inode: int = 0
        # Initialize to current end of file on startup so we don't trigger on old historical logs
        self._init_to_eof()

    def _init_to_eof(self):
        if self.file_path.is_file():
            try:
                stat = self.file_path.stat()
                self.last_inode = stat.st_ino
                self.last_offset = stat.st_size
            except Exception:
                self.last_offset = 0

    def read_new_lines(self) -> List[str]:
        if not self.file_path.is_file():
            return []

        try:
            stat = self.file_path.stat()
            # If file rotated (inode changed) or truncated (size shrank), reset to 0
            if stat.st_ino != self.last_inode or stat.st_size < self.last_offset:
                self.last_inode = stat.st_ino
                self.last_offset = 0

            if stat.st_size == self.last_offset:
                return []

            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.last_offset)
                new_content = f.read()
                self.last_offset = f.tell()

            return new_content.splitlines()
        except Exception as e:
            logger.debug(f"Error reading file {self.file_path}: {e}")
            return []


class LogMonitor:
    """Monitors configured log files and Orca ACP brain transcripts for rate limit patterns."""

    def __init__(
        self,
        log_files: List[str],
        patterns: List[str],
        monitor_brain: bool = True,
        brain_dir: str = "~/.config/orca/antigravity-chat/antigravity-acp/brain",
    ):
        self.log_file_patterns = log_files
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self.monitor_brain = monitor_brain
        self.brain_dir = Path(os.path.expanduser(brain_dir))

        self.watchers: Dict[Path, FileWatcher] = {}
        self._discover_files()

    def _discover_files(self):
        """Finds all target log files and registers FileWatchers."""
        candidate_paths = set()

        for pattern in self.log_file_patterns:
            expanded = os.path.expanduser(pattern)
            for path_str in glob.glob(expanded):
                p = Path(path_str)
                if p.is_file():
                    candidate_paths.add(p)

        # Monitor brain transcripts if enabled
        if self.monitor_brain and self.brain_dir.is_dir():
            # Find the most recently modified transcript files (up to 3 latest sessions)
            brain_logs = glob.glob(str(self.brain_dir / "*" / ".system_generated" / "logs" / "transcript*.jsonl"))
            # Sort by mtime descending
            brain_logs.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
            for path_str in brain_logs[:4]:
                p = Path(path_str)
                if p.is_file():
                    candidate_paths.add(p)

        # Register new watchers
        for p in candidate_paths:
            if p not in self.watchers:
                self.watchers[p] = FileWatcher(p)

    def check_for_rate_limits(self) -> List[RateLimitEvent]:
        """Polls watched files for any new lines matching rate limit patterns."""
        self._discover_files()
        events: List[RateLimitEvent] = []

        for path, watcher in list(self.watchers.items()):
            new_lines = watcher.read_new_lines()
            for line in new_lines:
                for regex in self.compiled_patterns:
                    match = regex.search(line)
                    if match:
                        matched_str = match.group(0)
                        logger.warning(
                            f"Terdeteksi pattern limit '{matched_str}' pada {path.name}"
                        )
                        events.append(
                            RateLimitEvent(
                                source=str(path),
                                matched_text=line.strip()[:200],
                                pattern=regex.pattern,
                            )
                        )
                        # Avoid duplicate hits on the same line
                        break

        return events

"""Safety module: cooldown, loop protection, and instance locking."""

from collections import deque
import fcntl
import os
import sys
import time
from typing import Optional, Tuple, List


class LockError(Exception):
    pass


class SingleInstanceLock:
    """Ensures only one instance of the rotator daemon runs at a time."""

    def __init__(self, lock_path: str = "/tmp/orca-agy-rotator.lock"):
        self.lock_path = lock_path
        self.lock_file = None

    def acquire(self):
        try:
            self.lock_file = open(self.lock_path, "w")
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file.write(f"{os.getpid()}\n")
            self.lock_file.flush()
        except (IOError, BlockingIOError):
            raise LockError(
                f"Proses Orca ADE Rotator lain sedang berjalan (lockfile: {self.lock_path})."
            )

    def release(self):
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
                if os.path.exists(self.lock_path):
                    os.unlink(self.lock_path)
            except Exception:
                pass
            self.lock_file = None


class SafetyManager:
    """Manages cooldowns, loop prevention, and circuit breaking to prevent bans."""

    def __init__(
        self,
        cooldown_seconds: float = 30.0,
        max_switches_in_window: int = 5,
        window_seconds: float = 180.0,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.max_switches_in_window = max_switches_in_window
        self.window_seconds = window_seconds

        self.last_switch_time: float = 0.0
        self.switch_history: deque = deque()  # stores (timestamp, from_email, to_email)
        self.is_circuit_breaker_tripped: bool = False
        self.circuit_breaker_tripped_at: float = 0.0

    def can_switch(self) -> Tuple[bool, Optional[str]]:
        now = time.time()

        # Check circuit breaker
        if self.is_circuit_breaker_tripped:
            remaining_cooldown = self.window_seconds - (now - self.circuit_breaker_tripped_at)
            if remaining_cooldown > 0:
                return (
                    False,
                    f"Circuit breaker aktif! Ditahan selama {int(remaining_cooldown)}s lagi untuk mencegah loop/ban.",
                )
            else:
                # Reset circuit breaker
                self.is_circuit_breaker_tripped = False
                self.switch_history.clear()

        # Check single-switch cooldown
        elapsed_since_last = now - self.last_switch_time
        if elapsed_since_last < self.cooldown_seconds:
            remaining = self.cooldown_seconds - elapsed_since_last
            return (
                False,
                f"Dalam masa cooldown ({int(remaining)}s tersisa). Pergantian akun ditunda.",
            )

        return True, None

    def record_switch(self, from_email: str, to_email: str):
        now = time.time()
        self.last_switch_time = now
        self.switch_history.append((now, from_email, to_email))

        # Purge entries outside window
        cutoff = now - self.window_seconds
        while self.switch_history and self.switch_history[0][0] < cutoff:
            self.switch_history.popleft()

        # Check if circuit breaker should trip
        if len(self.switch_history) >= self.max_switches_in_window:
            self.is_circuit_breaker_tripped = True
            self.circuit_breaker_tripped_at = now

    def reset_cooldown(self):
        """Allows manual bypass/reset."""
        self.last_switch_time = 0.0
        self.is_circuit_breaker_tripped = False
        self.switch_history.clear()

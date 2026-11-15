"""Unit and integration tests for Orca ADE Antigravity Auto-Switcher."""

import unittest
from unittest.mock import patch, MagicMock
import tempfile
import time
from pathlib import Path

from rotator.account_manager import AccountManager, AccountInfo
from rotator.config import RotatorConfig
from rotator.monitor import LogMonitor, FileWatcher
from rotator.safety import SafetyManager, SingleInstanceLock, LockError
from rotator.terminal_manager import TerminalManager, TerminalInfo


class TestAccountManager(unittest.TestCase):
    def setUp(self):
        self.mgr = AccountManager()

    def test_smart_quota_candidate_selection(self):
        # 3 accounts:
        # acc1: active, 100% used
        # acc2: exhausted, 100% used
        # acc3: fresh, 0% used
        accounts = [
            AccountInfo(id="1", email="active@gmail.com", is_active=True, session_used=100.0, weekly_used=100.0),
            AccountInfo(id="2", email="exhausted@gmail.com", is_active=False, session_used=100.0, weekly_used=100.0),
            AccountInfo(id="3", email="fresh@gmail.com", is_active=False, session_used=0.0, weekly_used=0.0),
        ]

        with patch.object(self.mgr, "fetch_accounts", return_value=(accounts, "1", accounts[0])):
            candidate, reason, reset_info = self.mgr.find_best_candidate(strategy="smart_quota")
            self.assertIsNotNone(candidate)
            self.assertEqual(candidate.email, "fresh@gmail.com")
            self.assertEqual(reason, "smart_quota_available")

    def test_all_accounts_exhausted_scenario(self):
        accounts = [
            AccountInfo(id="1", email="acc1@gmail.com", is_active=True, session_used=100.0, weekly_used=100.0, session_resets_at=2000000),
            AccountInfo(id="2", email="acc2@gmail.com", is_active=False, session_used=100.0, weekly_used=100.0, session_resets_at=1000000),
        ]

        with patch.object(self.mgr, "fetch_accounts", return_value=(accounts, "1", accounts[0])):
            candidate, reason, reset_info = self.mgr.find_best_candidate(strategy="smart_quota")
            self.assertIsNone(candidate)
            self.assertEqual(reason, "all_exhausted")
            self.assertIsNotNone(reset_info)
            self.assertEqual(reset_info["account_email"], "acc2@gmail.com")
            self.assertEqual(reset_info["resets_at_ms"], 1000000)

    def test_round_robin_selection(self):
        accounts = [
            AccountInfo(id="1", email="acc1@gmail.com", is_active=True, session_used=100.0, weekly_used=100.0),
            AccountInfo(id="2", email="acc2@gmail.com", is_active=False, session_used=0.0, weekly_used=0.0),
            AccountInfo(id="3", email="acc3@gmail.com", is_active=False, session_used=0.0, weekly_used=0.0),
        ]

        with patch.object(self.mgr, "fetch_accounts", return_value=(accounts, "1", accounts[0])):
            candidate, reason, _ = self.mgr.find_best_candidate(strategy="round_robin")
            self.assertIsNotNone(candidate)
            self.assertEqual(candidate.email, "acc2@gmail.com")


class TestSafetyManager(unittest.TestCase):
    def test_cooldown_enforcement(self):
        safety = SafetyManager(cooldown_seconds=10.0, max_switches_in_window=5, window_seconds=60.0)

        # Initial state: should be allowed
        can_switch, reason = safety.can_switch()
        self.assertTrue(can_switch)

        # Record switch
        safety.record_switch("a@test.com", "b@test.com")

        # Immediate next check: should be blocked by cooldown
        can_switch, reason = safety.can_switch()
        self.assertFalse(can_switch)
        self.assertIn("cooldown", reason.lower())

    def test_circuit_breaker_trip(self):
        safety = SafetyManager(cooldown_seconds=0.0, max_switches_in_window=3, window_seconds=60.0)

        safety.record_switch("a", "b")
        safety.record_switch("b", "c")
        self.assertFalse(safety.is_circuit_breaker_tripped)

        safety.record_switch("c", "d")
        self.assertTrue(safety.is_circuit_breaker_tripped)

        can_switch, reason = safety.can_switch()
        self.assertFalse(can_switch)
        self.assertIn("circuit breaker", reason.lower())


class TestLogMonitor(unittest.TestCase):
    def test_rate_limit_detection(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            log_path = f.name

        try:
            patterns = [r"RESOURCE_EXHAUSTED", r"429\s+Too\s+Many\s+Requests", r"Quota\s+exceeded"]
            monitor = LogMonitor(log_files=[log_path], patterns=patterns, monitor_brain=False)

            # Initially empty
            events = monitor.check_for_rate_limits()
            self.assertEqual(len(events), 0)

            # Write regular lines
            with open(log_path, "a") as f:
                f.write("Normal operation line\n")
            events = monitor.check_for_rate_limits()
            self.assertEqual(len(events), 0)

            # Write error line
            with open(log_path, "a") as f:
                f.write("Error: rpc error: code = ResourceExhausted desc = RESOURCE_EXHAUSTED: Quota exceeded\n")

            events = monitor.check_for_rate_limits()
            self.assertEqual(len(events), 1)
            self.assertIn("RESOURCE_EXHAUSTED", events[0].pattern)
        finally:
            Path(log_path).unlink(missing_ok=True)


class TestTerminalManager(unittest.TestCase):
    def test_terminal_selection_priority(self):
        mgr = TerminalManager()

        terminals = [
            TerminalInfo(
                handle="term_bash",
                title="bash",
                preview="ls -la",
                worktree_path="/test",
                connected=True,
                writable=True,
                last_output_at=1000,
                agent_identity=None,
            ),
            TerminalInfo(
                handle="term_agy",
                title="π Polish code",
                preview="Gemini 3.8 Flash thinking...",
                worktree_path="/test",
                connected=True,
                writable=True,
                last_output_at=900,
                agent_identity="antigravity",
            ),
        ]

        with patch.object(mgr, "list_terminals", return_value=terminals):
            best = mgr.find_active_terminal()
            self.assertIsNotNone(best)
            self.assertEqual(best.handle, "term_agy")


if __name__ == "__main__":
    unittest.main()

"""Orca Antigravity account manager and quota analyzer."""

from dataclasses import dataclass, field
import datetime
import json
import logging
import subprocess
import time
from typing import List, Optional, Tuple, Dict, Any


logger = logging.getLogger("orca_rotator.account_manager")


@dataclass
class AccountInfo:
    id: str
    email: str
    is_active: bool
    session_used: float = 0.0  # Percentage 0-100 (e.g. 2 = 2%, 100 = 100% limit)
    weekly_used: float = 0.0
    session_resets_at: Optional[int] = None  # epoch ms
    weekly_resets_at: Optional[int] = None  # epoch ms
    buckets: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_exhausted(self) -> bool:
        """Account is considered exhausted if session or weekly used >= 100%."""
        return self.session_used >= 100.0 or self.weekly_used >= 100.0

    @property
    def earliest_reset_timestamp(self) -> Optional[int]:
        """Returns the earliest epoch ms when quota will reset."""
        timestamps = []
        if self.session_resets_at and self.session_resets_at > 0:
            timestamps.append(self.session_resets_at)
        if self.weekly_resets_at and self.weekly_resets_at > 0:
            timestamps.append(self.weekly_resets_at)
        for b in self.buckets:
            r = b.get("resetsAt")
            if r and r > 0:
                timestamps.append(r)
        return min(timestamps) if timestamps else None


def format_ms_timestamp(ts_ms: Optional[int]) -> str:
    if not ts_ms:
        return "Unknown"
    dt = datetime.datetime.fromtimestamp(ts_ms / 1000.0)
    now = datetime.datetime.now()
    diff = dt - now
    diff_minutes = max(0, int(diff.total_seconds() // 60))
    time_str = dt.strftime("%H:%M:%S")
    return f"{time_str} ({diff_minutes}m lagi)"


class AccountManager:
    """Interacts with Orca CLI to inspect Antigravity accounts and switch active credentials."""

    def __init__(self, orca_bin: str = "orca"):
        self.orca_bin = orca_bin

    def fetch_accounts(self) -> Tuple[List[AccountInfo], Optional[str], Optional[AccountInfo]]:
        """
        Runs `orca account list --agent antigravity --json`.
        Returns: (accounts_list, active_account_id, active_account_obj)
        """
        cmd = [self.orca_bin, "account", "list", "--agent", "antigravity", "--json"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
        except Exception as e:
            logger.error(f"Gagal menjalankan '{' '.join(cmd)}': {e}")
            return [], None, None

        result_data = data.get("result", {}) or {}
        active_id = result_data.get("activeAccountId")
        raw_accounts = result_data.get("accounts", [])

        accounts: List[AccountInfo] = []
        active_account: Optional[AccountInfo] = None

        for item in raw_accounts:
            acc_id = item.get("id", "")
            email = item.get("email", "")
            is_active = (acc_id == active_id)

            usage = item.get("usage", {}) or {}
            session = usage.get("session", {}) or {}
            weekly = usage.get("weekly", {}) or {}
            buckets = usage.get("buckets", []) or []

            session_used = float(session.get("usedPercent", 0.0) or 0.0)
            weekly_used = float(weekly.get("usedPercent", 0.0) or 0.0)
            session_resets_at = session.get("resetsAt")
            weekly_resets_at = weekly.get("resetsAt")

            acc = AccountInfo(
                id=acc_id,
                email=email,
                is_active=is_active,
                session_used=session_used,
                weekly_used=weekly_used,
                session_resets_at=session_resets_at,
                weekly_resets_at=weekly_resets_at,
                buckets=buckets,
            )
            accounts.append(acc)
            if is_active:
                active_account = acc

        return accounts, active_id, active_account

    def find_best_candidate(
        self,
        strategy: str = "smart_quota",
    ) -> Tuple[Optional[AccountInfo], str, Optional[Dict[str, Any]]]:
        """
        Finds the next account to switch to.
        Returns:
            (candidate_account, reason_code, reset_info)
            reason_code can be:
            - "smart_quota_available": an account with lowest usage found
            - "round_robin_available": next account selected via round robin
            - "all_exhausted": all accounts are at 100% or above
            - "no_accounts": no accounts configured
        """
        accounts, active_id, active_account = self.fetch_accounts()

        if not accounts:
            return None, "no_accounts", None

        # Filter out the currently active account
        non_active_accounts = [acc for acc in accounts if acc.id != active_id]

        if not non_active_accounts:
            return None, "only_one_account", None

        # Check for candidates with remaining quota (< 100% used)
        fresh_candidates = [acc for acc in non_active_accounts if not acc.is_exhausted]

        if fresh_candidates:
            if strategy == "smart_quota":
                # Prioritize:
                # 1. Accounts with completely 0% usage (session and weekly == 0)
                # 2. Lowest combined usage
                def sort_key(acc: AccountInfo):
                    is_zero = (acc.session_used == 0 and acc.weekly_used == 0)
                    total_used = acc.session_used + acc.weekly_used
                    return (0 if is_zero else 1, total_used)

                fresh_candidates.sort(key=sort_key)
                return fresh_candidates[0], "smart_quota_available", None

            elif strategy == "round_robin":
                # Find current active index in all accounts
                try:
                    active_idx = next(i for i, acc in enumerate(accounts) if acc.id == active_id)
                except StopIteration:
                    active_idx = -1

                # Loop round-robin starting from active_idx + 1
                n = len(accounts)
                for step in range(1, n):
                    candidate = accounts[(active_idx + step) % n]
                    if not candidate.is_exhausted:
                        return candidate, "round_robin_available", None

        # If we reached here, ALL non-active accounts (or even all accounts) are exhausted!
        # Find account that will reset earliest
        all_resets = []
        for acc in accounts:
            earliest_ts = acc.earliest_reset_timestamp
            if earliest_ts:
                all_resets.append((earliest_ts, acc))

        reset_info = {}
        if all_resets:
            all_resets.sort(key=lambda x: x[0])
            earliest_ts, earliest_acc = all_resets[0]
            reset_info = {
                "account_email": earliest_acc.email,
                "resets_at_ms": earliest_ts,
                "human_readable": format_ms_timestamp(earliest_ts),
            }

        return None, "all_exhausted", reset_info

    def switch_account(self, account: AccountInfo, dry_run: bool = False) -> bool:
        """
        Executes: `orca account select --agent antigravity --account <target_email>`
        """
        target = account.email or account.id
        cmd = [
            self.orca_bin,
            "account",
            "select",
            "--agent",
            "antigravity",
            "--account",
            target,
            "--json",
        ]

        if dry_run:
            logger.info(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
            return True

        logger.info(f"Mengganti akun Antigravity ke: {target}...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            result = data.get("result", {})
            new_active_id = result.get("activeAccountId")
            if new_active_id == account.id or result.get("currentAccount", {}).get("email") == account.email:
                logger.info(f"Berhasil beralih ke akun: {target}")
                return True
            else:
                logger.warning(f"Respon switch tidak menunjukkan activeAccountId baru: {res.stdout}")
                return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Gagal switch akun: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error eksekusi switch: {e}")
            return False

"""Configuration module for Orca ADE Antigravity Auto-Switcher."""

from dataclasses import dataclass, field, asdict
import json
import os
from pathlib import Path
from typing import List, Optional


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "orca" / "agy-rotator" / "config.json"


@dataclass
class RotatorConfig:
    # Polling & Check intervals (seconds)
    log_check_interval: float = 1.0
    quota_check_interval: float = 20.0
    
    # Safety & Cooldown (seconds)
    cooldown_seconds: float = 30.0
    circuit_breaker_max_switches: int = 5
    circuit_breaker_window_seconds: float = 180.0
    
    # Account switching
    rotation_strategy: str = "smart_quota"  # "smart_quota" or "round_robin"
    
    # Auto-resume
    auto_resume: bool = True
    resume_delay_seconds: float = 2.0
    resume_command: str = "lanjutkan pengerjaan tadi"
    target_terminal: Optional[str] = None  # None = auto-detect most active
    
    # Notifications
    notifications_enabled: bool = True
    notification_app_name: str = "Orca ADE Rotator"
    
    # Log files to monitor
    log_files: List[str] = field(default_factory=lambda: [
        "~/.config/orca/logs/main.trace.ndjson",
        "~/.config/orca/logs/daemon.log",
    ])
    
    # Dynamic brain/transcripts monitoring
    monitor_brain_transcripts: bool = True
    brain_dir: str = "~/.config/orca/antigravity-chat/antigravity-acp/brain"
    
    # Rate limit error patterns (case-insensitive regex)
    rate_limit_patterns: List[str] = field(default_factory=lambda: [
        r"RESOURCE_EXHAUSTED",
        r"429\s+Too\s+Many\s+Requests",
        r"HTTP\s+429",
        r"\"code\":\s*429",
        r"status_code\s*:\s*429",
        r"Quota\s+exceeded",
        r"quota_exceeded",
        r"Rate\s+limit\s+exceeded",
        r"rate_limit_exceeded",
        r"Resource\s+has\s+been\s+exhausted",
        r"exceeded\s+your\s+current\s+quota",
        r"Five\s+Hour\s+Limit\s+Remaining.*(?:exhausted|exceeded|0%)",
        r"Weekly\s+Limit\s+Remaining.*(?:exhausted|exceeded|0%)",
    ])
    
    # Lock file path
    lock_file: str = "/tmp/orca-agy-rotator.lock"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RotatorConfig":
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "RotatorConfig":
        config_path = path or DEFAULT_CONFIG_PATH
        config_path = Path(os.path.expanduser(str(config_path)))
        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return cls.from_dict(data)
            except Exception as e:
                print(f"[Config] Warning: Failed to load config from {config_path}: {e}. Using defaults.")
        return cls()

    def save(self, path: Optional[Path] = None):
        config_path = path or DEFAULT_CONFIG_PATH
        config_path = Path(os.path.expanduser(str(config_path)))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

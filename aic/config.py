"""Load and validate config/rubric.yaml. This is the only place rubric settings are read from."""
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config" / "rubric.yaml"


class ConfigError(ValueError):
    pass


def _require(cfg: Dict[str, Any], *keys: str) -> None:
    for k in keys:
        if k not in cfg:
            raise ConfigError(f"rubric config missing key: {k}")


def validate(cfg: Dict[str, Any]) -> Dict[str, Any]:
    _require(cfg, "criteria", "groups", "thresholds", "pedigree_cap", "integrity_cap", "arithmetic", "gates", "outreach")

    crit = cfg["criteria"]
    total = sum(c["weight"] for c in crit.values())
    if total != 100:
        raise ConfigError(f"criterion weights must sum to 100, got {total}")

    grouped = [c for g in cfg["groups"].values() for c in g]
    if sorted(grouped) != sorted(crit):
        raise ConfigError("groups must cover every criterion exactly once")

    t = cfg["thresholds"]
    _require(t, "call", "pass", "close_call_margin")
    if not (0 <= t["pass"] < t["call"] <= 100):
        raise ConfigError(f"thresholds must satisfy 0 <= pass < call <= 100, got pass={t['pass']} call={t['call']}")

    pc = cfg["pedigree_cap"]
    for c in [pc["criterion"], *pc["unless_any_of"]]:
        if c not in crit:
            raise ConfigError(f"pedigree_cap refers to unknown criterion {c}")

    tol = cfg["arithmetic"]["tolerance"]
    if not (0 < tol < 1):
        raise ConfigError(f"arithmetic tolerance must be between 0 and 1, got {tol}")

    if cfg["outreach"].get("dry_run") is not True:
        raise ConfigError("outreach.dry_run must be true until a partner approves live sending")
    return cfg


def load(path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else DEFAULT_PATH
    with open(p) as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ConfigError(f"{p} is not a mapping")
    return validate(cfg)

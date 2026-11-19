import copy

import pytest
import yaml

from aic import config


def test_loads_default_config():
    cfg = config.load()
    assert sum(c["weight"] for c in cfg["criteria"].values()) == 100
    assert cfg["thresholds"]["call"] == 70
    assert cfg["thresholds"]["pass"] == 55
    assert cfg["thresholds"]["close_call_margin"] == 5
    assert cfg["arithmetic"]["tolerance"] == 0.05
    assert cfg["outreach"]["dry_run"] is True


def test_group_weights_match_rubric_v1():
    cfg = config.load()
    w = {k: v["weight"] for k, v in cfg["criteria"].items()}
    sums = {g: sum(w[c] for c in cs) for g, cs in cfg["groups"].items()}
    assert sums == {"founder": 35, "path": 35, "thesis": 20, "structure": 10}


def _write(tmp_path, cfg):
    p = tmp_path / "rubric.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


@pytest.fixture
def base():
    return copy.deepcopy(config.load())


def test_rejects_weights_not_summing_to_100(tmp_path, base):
    base["criteria"]["F1"]["weight"] = 11
    with pytest.raises(config.ConfigError, match="sum to 100"):
        config.load(_write(tmp_path, base))


def test_rejects_inverted_thresholds(tmp_path, base):
    base["thresholds"]["pass"] = 80
    with pytest.raises(config.ConfigError, match="thresholds"):
        config.load(_write(tmp_path, base))


def test_rejects_missing_section(tmp_path, base):
    del base["thresholds"]
    with pytest.raises(config.ConfigError, match="missing key"):
        config.load(_write(tmp_path, base))


def test_rejects_criterion_missing_from_groups(tmp_path, base):
    base["groups"]["founder"].remove("F4")
    with pytest.raises(config.ConfigError, match="groups"):
        config.load(_write(tmp_path, base))


def test_rejects_live_sending(tmp_path, base):
    base["outreach"]["dry_run"] = False
    with pytest.raises(config.ConfigError, match="dry_run"):
        config.load(_write(tmp_path, base))

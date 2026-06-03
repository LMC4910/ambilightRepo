"""Tests for config merge, defaults, and atomic save (NFR-R-06)."""

from ambilight.config import _merge, _dict_to_dataclass, AppConfig, ConfigManager


def test_merge_is_recursive_and_non_destructive():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 20}, "c": 4}
    merged = _merge(base, override)
    assert merged == {"a": {"x": 1, "y": 20}, "b": 3, "c": 4}
    assert base["a"]["y"] == 2  # original untouched


def test_dict_to_dataclass_drops_unknown_keys():
    cfg = _dict_to_dataclass(AppConfig, {"capture": {"fps_target": 24, "bogus": 1}})
    assert isinstance(cfg, AppConfig)
    assert cfg.capture.fps_target == 24


def test_load_defaults_when_missing(tmp_path):
    cfg = ConfigManager.load(tmp_path / "does_not_exist.yaml")
    assert isinstance(cfg, AppConfig)
    assert cfg.capture.fps_target == 30  # default


def test_logging_defaults_bounded_and_split_level():
    cfg = AppConfig()
    assert cfg.logging.file_level == "INFO"           # file stays INFO by default
    # Bounded ceiling = max_bytes × (backup_count + 1); should be a sane finite cap.
    cap = cfg.logging.max_bytes * (cfg.logging.backup_count + 1)
    assert 0 < cap <= 512 * 1024 * 1024               # ≤ 512 MB


def test_atomic_save_round_trip(tmp_path):
    path = tmp_path / "configuration.yaml"
    ConfigManager.load(path)            # seeds defaults + records path
    ConfigManager.update({"capture": {"fps_target": 42}}, path=path)
    assert path.exists()
    reloaded = ConfigManager.load(path)
    assert reloaded.capture.fps_target == 42

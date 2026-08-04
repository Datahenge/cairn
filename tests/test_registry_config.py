"""Tests for the registry role's machine-local config (`BR-REG-002`).

Unlike the descriptor (`BR-DEPLOY-010a`), absence is not an error — a first-time operator
should get a working registry before ever hand-writing TOML, so every test that checks a
default also proves the file is optional.
"""

from __future__ import annotations

import pytest

from cairn import registry_config
from cairn.errors import RegistryConfigError


def _write(tmp_path, text):
    path = tmp_path / "registry.toml"
    path.write_text(text, encoding="utf-8")
    return path


# --- the fixed path, and absence being fine ---------------------------------


def test_the_path_is_fixed_not_searched():
    assert registry_config.CONFIG_PATH.is_absolute()
    assert str(registry_config.CONFIG_PATH) == "/etc/cairn/registry.toml"


def test_an_absent_file_loads_documented_defaults(tmp_path):
    loaded = registry_config.load(tmp_path / "absent.toml")

    assert loaded.port == 5000
    assert loaded.bind_address == "127.0.0.1"
    assert loaded.data_dir == registry_config._DEFAULT_DATA_DIR
    assert loaded.retention.enabled is False
    assert loaded.retention.keep_last == 10
    assert loaded.retention.max_age_days == 90
    assert loaded.gc.schedule == "weekly"
    assert loaded.path is None


def test_host_joins_bind_address_and_port(tmp_path):
    loaded = registry_config.load(tmp_path / "absent.toml")
    assert loaded.host == "127.0.0.1:5000"


# --- [registry] ---------------------------------------------------------


def test_a_present_file_overrides_defaults(tmp_path):
    text = '[registry]\nport = 5001\nbind_address = "0.0.0.0"\ndata_dir = "/data/registry"\n'
    loaded = registry_config.load(_write(tmp_path, text))

    assert loaded.port == 5001
    assert loaded.bind_address == "0.0.0.0"
    assert str(loaded.data_dir) == "/data/registry"
    assert loaded.path is not None


@pytest.mark.parametrize("port_toml", ["0", "-1", "65536", '"5000"', "true"])
def test_an_invalid_port_is_refused(tmp_path, port_toml):
    text = f"[registry]\nport = {port_toml}\n"
    with pytest.raises(RegistryConfigError, match="port must be"):
        registry_config.load(_write(tmp_path, text))


def test_a_relative_data_dir_is_refused(tmp_path):
    with pytest.raises(RegistryConfigError, match="must be an absolute path"):
        registry_config.load(_write(tmp_path, '[registry]\ndata_dir = "relative/path"\n'))


def test_an_unknown_registry_key_is_refused(tmp_path):
    with pytest.raises(RegistryConfigError, match="unknown key\\(s\\) hostname"):
        registry_config.load(_write(tmp_path, '[registry]\nhostname = "example.com"\n'))


def test_invalid_toml_is_reported_as_such(tmp_path):
    with pytest.raises(RegistryConfigError, match="not valid TOML"):
        registry_config.load(_write(tmp_path, "registry = \n"))


# --- [registry.retention] (BR-REG-006/007/008) ------------------------------


def test_retention_is_disabled_by_default_even_when_the_table_is_absent(tmp_path):
    loaded = registry_config.load(_write(tmp_path, "[registry]\nport = 5000\n"))
    assert loaded.retention.enabled is False


def test_retention_can_be_enabled_with_custom_thresholds(tmp_path):
    text = "[registry.retention]\nenabled = true\nkeep_last = 5\nmax_age_days = 30\n"
    loaded = registry_config.load(_write(tmp_path, text))

    assert loaded.retention.enabled is True
    assert loaded.retention.keep_last == 5
    assert loaded.retention.max_age_days == 30


@pytest.mark.parametrize("value", ["0", "-1", "true"])
def test_keep_last_must_be_a_positive_integer(tmp_path, value):
    text = f"[registry.retention]\nkeep_last = {value}\n"
    with pytest.raises(RegistryConfigError, match="keep_last must be a positive integer"):
        registry_config.load(_write(tmp_path, text))


def test_an_unknown_retention_key_is_refused(tmp_path):
    with pytest.raises(RegistryConfigError, match="unknown key\\(s\\) pattern"):
        registry_config.load(_write(tmp_path, '[registry.retention]\npattern = "*"\n'))


# --- [registry.gc] (BR-REG-010) ---------------------------------------------


def test_gc_schedule_defaults_to_weekly(tmp_path):
    loaded = registry_config.load(_write(tmp_path, "[registry]\nport = 5000\n"))
    assert loaded.gc.schedule == "weekly"


def test_gc_schedule_can_be_overridden(tmp_path):
    loaded = registry_config.load(_write(tmp_path, '[registry.gc]\nschedule = "daily"\n'))
    assert loaded.gc.schedule == "daily"


def test_an_empty_gc_schedule_is_refused(tmp_path):
    with pytest.raises(RegistryConfigError, match="schedule must be a non-empty string"):
        registry_config.load(_write(tmp_path, '[registry.gc]\nschedule = ""\n'))

"""Tests for the target's environment descriptor (`BR-DEPLOY-010`, `BR-DEPLOY-010a`).

Validation is strict on purpose: this file decides what a production host runs, and a typo
in it must fail here rather than converge the wrong thing. Every test therefore checks that
a mistake is *named*, not merely rejected.
"""

from __future__ import annotations

import pytest

from cairn import descriptor
from cairn.errors import DescriptorError

MINIMAL = """\
environment = "production"
registry_host = "ghcr.io"
image = "datahenge/erpnext-btu-v16"
tag = "production"
site = "erp.example.com"
"""


def _write(tmp_path, text):
    path = tmp_path / "adopt.toml"
    path.write_text(text, encoding="utf-8")
    return path


# --- the fixed path (BR-DEPLOY-010a, ADR-034) -------------------------------


def test_the_path_is_fixed_not_searched():
    """`reconcile` runs unattended: a search path could silently find the wrong environment."""
    assert descriptor.DESCRIPTOR_PATH.is_absolute()
    assert str(descriptor.DESCRIPTOR_PATH) == "/etc/cairn/adopt.toml"


def test_presence_is_the_role_signal(tmp_path):
    """A machine with a descriptor is a target — this is what `doctor` detects the role from."""
    assert descriptor.exists(tmp_path / "absent.toml") is False
    assert descriptor.exists(_write(tmp_path, MINIMAL)) is True


def test_a_missing_descriptor_says_what_is_missing_and_why(tmp_path):
    with pytest.raises(DescriptorError, match="does not know what this host runs"):
        descriptor.load(tmp_path / "absent.toml")


# --- the minimum a host must declare ----------------------------------------


def test_a_minimal_descriptor_loads(tmp_path):
    loaded = descriptor.load(_write(tmp_path, MINIMAL))

    assert loaded.environment == "production"
    assert loaded.site == "erp.example.com"
    assert loaded.reference == "ghcr.io/datahenge/erpnext-btu-v16:production"
    assert loaded.is_production is True


def test_the_watched_reference_joins_image_and_tag(tmp_path):
    """The reference is the desired-state pointer; assembling it wrongly deploys the wrong tag."""
    loaded = descriptor.load(
        _write(tmp_path, MINIMAL.replace('tag = "production"', 'tag = "v16"'))
    )

    assert loaded.reference == "ghcr.io/datahenge/erpnext-btu-v16:v16"


# --- registry_host: separate from image, not a combined string, and required ---


def test_registry_host_is_required(tmp_path):
    """Even Docker Hub has a canonical name for it (`"docker.io"`), so there is no case where
    this value would need to be fabricated — it is required, not defaulted."""
    text = "\n".join(
        line for line in MINIMAL.splitlines() if not line.startswith("registry_host")
    )

    with pytest.raises(DescriptorError, match="'registry_host' is required"):
        descriptor.load(_write(tmp_path, text))


def test_registry_host_and_image_are_joined_at_the_point_of_use(tmp_path):
    """Separate fields, not one string glued together — `repository`/`reference` join them."""
    text = MINIMAL.replace('registry_host = "ghcr.io"', 'registry_host = "127.0.0.1:5000"')
    text = text.replace(
        'image = "datahenge/erpnext-btu-v16"', 'image = "acmecorp/erpnext-v16"'
    )
    loaded = descriptor.load(_write(tmp_path, text))

    assert loaded.registry_host == "127.0.0.1:5000"
    assert loaded.image == "acmecorp/erpnext-v16"
    assert loaded.repository == "127.0.0.1:5000/acmecorp/erpnext-v16"
    assert loaded.reference == "127.0.0.1:5000/acmecorp/erpnext-v16:production"


@pytest.mark.parametrize("key", ["environment", "registry_host", "image", "tag", "site"])
def test_every_required_key_is_required_by_name(tmp_path, key):
    text = "\n".join(line for line in MINIMAL.splitlines() if not line.startswith(key))

    with pytest.raises(DescriptorError, match=f"'{key}' is required"):
        descriptor.load(_write(tmp_path, text))


def test_a_typo_names_the_key_and_the_alternatives(tmp_path):
    """The whole point of strict validation: a misspelled key must not be silently ignored,
    leaving the host converging on a default nobody chose."""
    with pytest.raises(DescriptorError, match="unknown key\\(s\\) sight"):
        descriptor.load(_write(tmp_path, MINIMAL + 'sight = "erp.example.com"\n'))


def test_invalid_toml_is_reported_as_such(tmp_path):
    with pytest.raises(DescriptorError, match="not valid TOML"):
        descriptor.load(_write(tmp_path, "environment = \n"))


# --- compose (BR-DEPLOY-010) ------------------------------------------------


def test_overrides_keep_their_declared_order(tmp_path):
    """Compose layers later files over earlier ones, so this order is semantic, not cosmetic."""
    loaded = descriptor.load(
        _write(tmp_path, MINIMAL + '[compose]\noverrides = ["mariadb", "redis", "https"]\n')
    )

    assert loaded.compose.overrides == ("mariadb", "redis", "https")


def test_a_non_list_of_overrides_is_refused_with_an_example(tmp_path):
    with pytest.raises(DescriptorError, match="list of override names"):
        descriptor.load(_write(tmp_path, MINIMAL + '[compose]\noverrides = "mariadb"\n'))


def test_compose_paths_are_expanded(tmp_path):
    loaded = descriptor.load(
        _write(tmp_path, MINIMAL + '[compose]\ndirectory = "~/frappe_docker"\n')
    )

    assert loaded.compose.directory is not None
    assert "~" not in str(loaded.compose.directory)


def test_an_unknown_compose_key_is_refused(tmp_path):
    with pytest.raises(DescriptorError, match="unknown key"):
        descriptor.load(_write(tmp_path, MINIMAL + '[compose]\noverride = ["mariadb"]\n'))


def test_the_compose_file_defaults_to_compose_yaml(tmp_path):
    """Not every deployment is a fresh `examine` output — an older or hand-written descriptor
    with no `file` key must still work the same way it always has."""
    loaded = descriptor.load(_write(tmp_path, MINIMAL))

    assert loaded.compose.file == descriptor.DEFAULT_COMPOSE_FILE == "compose.yaml"


def test_a_non_default_compose_file_name_is_honored(tmp_path):
    """A hand-built deployment may not call its compose file `compose.yaml` at all."""
    loaded = descriptor.load(_write(tmp_path, MINIMAL + '[compose]\nfile = "erpnext.yaml"\n'))

    assert loaded.compose.file == "erpnext.yaml"


def test_an_empty_compose_file_name_is_refused(tmp_path):
    with pytest.raises(DescriptorError, match="\\[compose\\] file must be a non-empty string"):
        descriptor.load(_write(tmp_path, MINIMAL + '[compose]\nfile = ""\n'))


# --- health (BR-DEPLOY-017) -------------------------------------------------


def test_health_has_workable_defaults(tmp_path):
    loaded = descriptor.load(_write(tmp_path, MINIMAL))

    assert loaded.health.timeout_seconds > 0
    assert loaded.health.interval_seconds <= loaded.health.timeout_seconds
    assert loaded.health.url is None  # container health only, until a URL is named


def test_an_interval_longer_than_the_timeout_is_refused(tmp_path):
    """It would give up before ever probing, which looks like a failing deploy."""
    text = MINIMAL + "[health]\ntimeout_seconds = 30\ninterval_seconds = 60\n"

    with pytest.raises(DescriptorError, match="would never be checked"):
        descriptor.load(_write(tmp_path, text))


@pytest.mark.parametrize("value", ["0", '"60"', "-5", "true"])
def test_health_seconds_must_be_whole_positive_numbers(tmp_path, value):
    with pytest.raises(DescriptorError, match="whole number of seconds"):
        descriptor.load(_write(tmp_path, MINIMAL + f"[health]\ntimeout_seconds = {value}\n"))


# --- secrets (BR-DEPLOY-011, BR-DEPLOY-013) ---------------------------------


def test_the_secret_mechanism_is_named_not_the_secret(tmp_path):
    """cairn wires secrets by mechanism and never handles a value (`BR-DEPLOY-011`)."""
    loaded = descriptor.load(
        _write(tmp_path, MINIMAL + '[secrets]\nmechanism = "docker-secrets"\n')
    )

    assert loaded.secret_mechanism == "docker-secrets"


def test_an_unsupported_mechanism_lists_the_supported_ones(tmp_path):
    with pytest.raises(DescriptorError, match="docker-secrets"):
        descriptor.load(_write(tmp_path, MINIMAL + '[secrets]\nmechanism = "vault"\n'))


def test_no_mechanism_means_none(tmp_path):
    assert descriptor.load(_write(tmp_path, MINIMAL)).secret_mechanism == "none"

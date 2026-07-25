"""Tests for manifest and build-config loading.

Covers BR-BUILD-001/002/003/005, BR-CFG-008/011/012, BR-CLI-014, ADR-029.
"""

from __future__ import annotations

import pytest

from cairn import config
from cairn.errors import (
    BuildConfigInvalidError,
    ManifestInvalidError,
    ManifestNotFoundError,
)

VALID = """\
[cairn]
image_name = "erpnext-btu-v16"

[cairn.frappe]
url = "https://github.com/frappe/frappe"
ref = "version-16"

# ORDERED (BR-BUILD-003)
[[cairn.apps]]
name = "erpnext"
url = "https://github.com/frappe/erpnext"
ref = "version-16"

[[cairn.apps]]
name = "btu"
url = "https://github.com/Datahenge/btu"
ref = "version-16"

[cairn.build]
python_version = "3.14.2"
install_chromium = true
debian_base = "bookworm"
"""


def _manifest(tmp_path, text: str = VALID):
    path = tmp_path / config.MANIFEST_NAME
    path.write_text(text, encoding="utf-8")
    return path


# --- manifest shape (BR-BUILD-002) ------------------------------------------


def test_loads_a_valid_manifest(tmp_path):
    """BR-BUILD-002: image_name, [cairn.frappe], apps, and build knobs are read."""
    manifest = config.load_manifest(_manifest(tmp_path))

    assert manifest.image_name == "erpnext-btu-v16"
    assert manifest.frappe == config.Frappe("https://github.com/frappe/frappe", "version-16")
    assert manifest.build["install_chromium"] is True


def test_app_order_is_preserved(tmp_path):
    """BR-BUILD-003: manifest order is the install sequence; cairn never reorders."""
    manifest = config.load_manifest(_manifest(tmp_path))

    assert [app.name for app in manifest.apps] == ["erpnext", "btu"]


def test_build_section_passes_through_unknown_knobs(tmp_path):
    """BR-BUILD-002: [cairn.build] carries a passthrough for the long tail."""
    manifest = config.load_manifest(_manifest(tmp_path))

    assert manifest.build["debian_base"] == "bookworm"


def test_zero_apps_is_valid(tmp_path):
    """A Frappe-only image is legal; the Containerfile tolerates an empty apps.json."""
    text = VALID.split("# ORDERED")[0] + '[cairn.build]\npython_version = "3.14.2"\n'

    assert config.load_manifest(_manifest(tmp_path, text)).apps == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[other]\nx = 1\n", r"missing the required \[cairn\] table"),
        # `[cairn.frappe]` implicitly creates `[cairn]`, so this reports the missing key.
        ('[cairn.frappe]\nurl = "u"\nref = "r"\n', "image_name is required"),
        ('[cairn]\nimage_name = "x"\n', r"\[cairn.frappe\]"),
        ('[cairn]\nimage_name = ""\n', "image_name is required"),
        ('[cairn]\nimage_name = "Bad_Name"\n', "not a valid image name"),
    ],
)
def test_structural_errors_are_actionable(tmp_path, text, expected):
    """BR-CLI-015: each failure names what is wrong and what shape is expected."""
    with pytest.raises(ManifestInvalidError, match=expected):
        config.load_manifest(_manifest(tmp_path, text))


def test_unknown_key_is_rejected_as_a_typo(tmp_path):
    """Strictness outside [cairn.build] turns a typo into a parse error, not a bad image."""
    text = VALID.replace("image_name =", "imagename =")

    with pytest.raises(ManifestInvalidError, match="unknown key"):
        config.load_manifest(_manifest(tmp_path, text))


def test_duplicate_app_rejected(tmp_path):
    """BR-BUILD-003: the app list is an ordered sequence; a repeat is ambiguous."""
    text = VALID + '\n[[cairn.apps]]\nname = "btu"\nurl = "u"\nref = "r"\n'

    with pytest.raises(ManifestInvalidError, match="listed more than once"):
        config.load_manifest(_manifest(tmp_path, text))


def test_commit_sha_ref_rejected(tmp_path):
    """BR-BUILD-005: refs pin by branch or tag; cairn resolves the commit itself."""
    text = VALID.replace('ref = "version-16"', f'ref = "{"a" * 40}"', 1)

    with pytest.raises(ManifestInvalidError, match="looks like a commit SHA"):
        config.load_manifest(_manifest(tmp_path, text))


def test_wrong_knob_type_rejected(tmp_path):
    text = VALID.replace("install_chromium = true", 'install_chromium = "yes"')

    with pytest.raises(ManifestInvalidError, match="install_chromium must be a bool"):
        config.load_manifest(_manifest(tmp_path, text))


def test_malformed_toml_is_reported_as_such(tmp_path):
    with pytest.raises(ManifestInvalidError, match="not valid TOML"):
        config.load_manifest(_manifest(tmp_path, "[cairn\n"))


# --- the declared environment list (BR-DEPLOY-009a, ADR-033) ----------------


def test_environments_are_optional(tmp_path):
    """A manifest that only ever builds declares none, and that is not a defect — the
    pointer verbs report that no environment exists rather than inventing one."""
    assert config.load_manifest(_manifest(tmp_path)).environments == {}


def test_environments_map_names_to_registry_tags(tmp_path):
    text = VALID + '\n[cairn.environments]\nproduction = "production"\nstaging = "stg"\n'

    manifest = config.load_manifest(_manifest(tmp_path, text))

    assert manifest.environments == {"production": "production", "staging": "stg"}


def test_two_environments_may_not_share_one_tag(tmp_path):
    """The tag *is* the desired-state pointer, so sharing one would make a retag of either
    deploy to both at once."""
    text = VALID + '\n[cairn.environments]\nstaging = "live"\nproduction = "live"\n'

    with pytest.raises(ManifestInvalidError, match="both point at"):
        config.load_manifest(_manifest(tmp_path, text))


def test_an_environment_needs_a_tag_string(tmp_path):
    text = VALID + "\n[cairn.environments]\nproduction = true\n"

    with pytest.raises(ManifestInvalidError, match="must name a registry tag"):
        config.load_manifest(_manifest(tmp_path, text))


def test_an_invalid_tag_is_rejected_at_parse_time(tmp_path):
    """A tag the registry would refuse must fail here, not after a build and a push."""
    text = VALID + '\n[cairn.environments]\nproduction = "not a tag"\n'

    with pytest.raises(ManifestInvalidError, match="not a valid image tag"):
        config.load_manifest(_manifest(tmp_path, text))


def test_environments_is_not_a_build_input(tmp_path):
    """No environment name may reach the image: it is promoted between environments, never
    built per environment."""
    text = VALID + '\n[cairn.environments]\nproduction = "production"\n'

    manifest = config.load_manifest(_manifest(tmp_path, text))

    assert "environments" not in manifest.build
    assert "production" not in str(manifest.build)


# --- discovery (BR-CFG-012, ADR-029) ----------------------------------------


def test_manifest_found_by_walking_up(tmp_path):
    """BR-CFG-012: the nearest cairn.toml above the working directory wins."""
    _manifest(tmp_path)
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)

    assert config.find_manifest(start=deep) == tmp_path / config.MANIFEST_NAME


def test_explicit_path_wins(tmp_path):
    """BR-CFG-012: --manifest overrides the search."""
    elsewhere = tmp_path / "other.toml"
    elsewhere.write_text(VALID, encoding="utf-8")
    _manifest(tmp_path)

    assert config.find_manifest(start=tmp_path, explicit=elsewhere) == elsewhere


def test_missing_manifest_names_the_fix(tmp_path):
    with pytest.raises(ManifestNotFoundError, match="--manifest"):
        config.find_manifest(start=tmp_path)


def test_explicit_missing_path_is_an_error(tmp_path):
    with pytest.raises(ManifestNotFoundError, match="No manifest at"):
        config.find_manifest(explicit=tmp_path / "nope.toml")


# --- build config layering (BR-CFG-008/012) ---------------------------------


def _user_config(monkeypatch, tmp_path, text: str):
    path = tmp_path / "user-config.toml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "USER_CONFIG_PATH", path)
    return path


def test_local_file_overrides_user_file_key_by_key(monkeypatch, tmp_path):
    """BR-CFG-012: cairn.local.toml overrides per key, leaving other keys intact."""
    _user_config(monkeypatch, tmp_path, 'engine = "podman"\nregistry = "ghcr.io"\n')
    deployment = tmp_path / "deployment"
    deployment.mkdir()
    (deployment / config.LOCAL_CONFIG_NAME).write_text(
        'namespace = "acme"\nregistry = "example.com"\n', encoding="utf-8"
    )

    loaded = config.load_build_config(deployment / config.MANIFEST_NAME)

    assert loaded.engine == "podman"  # untouched by the local file
    assert loaded.registry == "example.com"  # overridden
    assert loaded.namespace == "acme"


def test_absent_files_yield_defaults(monkeypatch, tmp_path):
    """BR-CFG-012: both files are optional."""
    monkeypatch.setattr(config, "USER_CONFIG_PATH", tmp_path / "absent.toml")

    loaded = config.load_build_config(tmp_path / config.MANIFEST_NAME)

    assert loaded == config.BuildConfig()


def test_unknown_build_config_key_rejected(monkeypatch, tmp_path):
    _user_config(monkeypatch, tmp_path, 'reg1stry = "ghcr.io"\n')

    with pytest.raises(BuildConfigInvalidError, match="unknown key"):
        config.load_build_config()


# --- image base composition (BR-CFG-011, BR-BUILD-008) ----------------------


@pytest.mark.parametrize(
    ("build_config", "expected"),
    [
        (config.BuildConfig(), "cairn/erpnext-btu-v16"),
        (config.BuildConfig(registry="ghcr.io", namespace="acme"), "ghcr.io/acme/erpnext-btu-v16"),
        (config.BuildConfig(registry="ghcr.io"), "ghcr.io/erpnext-btu-v16"),
        (config.BuildConfig(image_base="explicit/base"), "explicit/base"),
    ],
)
def test_image_base_resolution(build_config, expected):
    """BR-CFG-011: registry configured -> registry path; absent -> local cairn/<name>."""
    assert build_config.resolve_image_base("erpnext-btu-v16") == expected

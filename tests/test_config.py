"""Tests for manifest and build-config loading.

Covers BR-BUILD-001/002/003/005, BR-CFG-008/011/012, BR-CLI-014, ADR-029, ADR-042.
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


@pytest.mark.parametrize(
    ("environments_table", "expected"),
    [
        # sharing a tag would make a retag of either deploy to both at once — the tag *is*
        # the desired-state pointer.
        ('staging = "live"\nproduction = "live"\n', "both point at"),
        ("production = true\n", "must name a registry tag"),
        # a tag the registry would refuse must fail here, not after a build and a push.
        ('production = "not a tag"\n', "not a valid image tag"),
    ],
)
def test_environment_tags_are_validated(tmp_path, environments_table, expected):
    text = VALID + "\n[cairn.environments]\n" + environments_table

    with pytest.raises(ManifestInvalidError, match=expected):
        config.load_manifest(_manifest(tmp_path, text))


def test_environments_is_not_a_build_input(tmp_path):
    """No environment name may reach the image: it is promoted between environments, never
    built per environment."""
    text = VALID + '\n[cairn.environments]\nproduction = "production"\n'

    manifest = config.load_manifest(_manifest(tmp_path, text))

    assert "environments" not in manifest.build
    assert "production" not in str(manifest.build)


# --- discovery (BR-CFG-012, ADR-042) ----------------------------------------


def test_explicit_path_wins(tmp_path, monkeypatch):
    """BR-CFG-012: --manifest wins even when $CAIRN_MANIFEST also names a file."""
    elsewhere = tmp_path / "other.toml"
    elsewhere.write_text(VALID, encoding="utf-8")
    env_target = _manifest(tmp_path)
    monkeypatch.setenv(config.MANIFEST_ENV_VAR, str(env_target))

    assert config.find_manifest(explicit=elsewhere) == elsewhere


def test_env_var_is_used_absent_a_flag(tmp_path, monkeypatch):
    """BR-CFG-012, ADR-042: $CAIRN_MANIFEST is the only implicit path."""
    target = _manifest(tmp_path)
    monkeypatch.setenv(config.MANIFEST_ENV_VAR, str(target))

    assert config.find_manifest() == target


def test_no_directory_is_ever_searched(tmp_path, monkeypatch):
    """ADR-042: a cairn.toml in the working directory is never picked up implicitly."""
    _manifest(tmp_path)
    monkeypatch.delenv(config.MANIFEST_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ManifestNotFoundError, match="--manifest"):
        config.find_manifest()


def test_missing_manifest_names_the_fix(monkeypatch):
    monkeypatch.delenv(config.MANIFEST_ENV_VAR, raising=False)
    with pytest.raises(ManifestNotFoundError, match=r"--manifest.*CAIRN_MANIFEST"):
        config.find_manifest()


def test_explicit_missing_path_is_an_error(tmp_path):
    with pytest.raises(ManifestNotFoundError, match="No manifest at"):
        config.find_manifest(explicit=tmp_path / "nope.toml")


def test_env_var_missing_path_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv(config.MANIFEST_ENV_VAR, str(tmp_path / "nope.toml"))
    with pytest.raises(ManifestNotFoundError, match="CAIRN_MANIFEST"):
        config.find_manifest()


# --- build config layering (BR-CFG-008/012, ADR-042) ------------------------


def _user_config(monkeypatch, tmp_path, text: str):
    path = tmp_path / "builder.toml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", path)
    return path


def _clear_build_config_env(monkeypatch):
    for key in config.BUILD_CONFIG_KEYS:
        monkeypatch.delenv(f"{config.BUILD_CONFIG_ENV_PREFIX}{key.upper()}", raising=False)


def test_env_overrides_user_file_key_by_key(monkeypatch, tmp_path):
    """BR-CFG-012: CAIRN_* env vars override per key, leaving other keys intact."""
    _clear_build_config_env(monkeypatch)
    _user_config(monkeypatch, tmp_path, 'engine = "podman"\nregistry = "ghcr.io"\n')
    monkeypatch.setenv("CAIRN_NAMESPACE", "acme")
    monkeypatch.setenv("CAIRN_REGISTRY", "example.com")

    loaded = config.load_build_config(tmp_path / "deployment" / config.MANIFEST_NAME)

    assert loaded.engine == "podman"  # untouched by the env override
    assert loaded.registry == "example.com"  # overridden
    assert loaded.namespace == "acme"


def test_absent_files_and_env_yield_defaults(monkeypatch, tmp_path):
    """BR-CFG-012: the builder file and every CAIRN_* var are optional."""
    _clear_build_config_env(monkeypatch)
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", tmp_path / "absent.toml")

    loaded = config.load_build_config(tmp_path / config.MANIFEST_NAME)

    assert loaded == config.BuildConfig()


def test_unknown_build_config_key_rejected(monkeypatch, tmp_path):
    _clear_build_config_env(monkeypatch)
    _user_config(monkeypatch, tmp_path, 'reg1stry = "ghcr.io"\n')

    with pytest.raises(BuildConfigInvalidError, match="unknown key"):
        config.load_build_config()


def test_empty_env_var_is_treated_as_absent(monkeypatch, tmp_path):
    _clear_build_config_env(monkeypatch)
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", tmp_path / "absent.toml")
    monkeypatch.setenv("CAIRN_ENGINE", "")

    loaded = config.load_build_config()

    assert loaded.engine is None


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


# --- the legible tag half (BR-BUILD-008, ADR-032) ----------------------------


def _with_series(text: str, value: str) -> str:
    """Insert a `series` key into `[cairn]`, where the tag's readable half is declared."""
    return text.replace(
        'image_name = "erpnext-btu-v16"',
        f'image_name = "erpnext-btu-v16"\nseries = {value}',
    )


def test_series_is_optional(tmp_path):
    """Absent it, the legible half is derived from the ref as it always was."""
    assert config.load_manifest(_manifest(tmp_path)).series is None


def test_series_is_read_when_declared(tmp_path):
    text = _with_series(VALID, '"v16"')

    assert config.load_manifest(_manifest(tmp_path, text)).series == "v16"


@pytest.mark.parametrize(
    ("series_literal", "expected"),
    [
        # the tag reads as '<series>-<hash>', so a hyphen inside the series makes it
        # ambiguous to the human it exists for.
        ('"v16-erp"', "no hyphens"),
        ("16", "series must be a non-empty string"),
        ('"v 16"', "cannot be used in an image tag"),
    ],
)
def test_an_invalid_series_is_refused(tmp_path, series_literal, expected):
    text = _with_series(VALID, series_literal)

    with pytest.raises(ManifestInvalidError, match=expected):
        config.load_manifest(_manifest(tmp_path, text))


# --- registry coordinates in the manifest (BR-CFG-013/014, ADR-038/039) ------


def _deployment(tmp_path, manifest_text=None):
    """A deployment directory, optionally with a manifest."""
    directory = tmp_path / "deployment"
    directory.mkdir(exist_ok=True)
    if manifest_text is not None:
        (directory / config.MANIFEST_NAME).write_text(manifest_text, encoding="utf-8")
    return directory / config.MANIFEST_NAME


def _with_registry(host="ghcr.io", namespace="acme-corp"):
    table = f'\n[cairn.registry]\nhost = "{host}"\n'
    if namespace is not None:
        table += f'namespace = "{namespace}"\n'
    return VALID + table


def test_the_manifest_declares_where_its_images_belong(monkeypatch, tmp_path):
    """The client's registry is a property of the deployment, not of Brian's laptop — so it
    travels with the deployment and the client can take it over."""
    _clear_build_config_env(monkeypatch)
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", tmp_path / "absent.toml")
    manifest = _deployment(tmp_path, manifest_text=_with_registry())

    loaded = config.load_build_config(manifest)

    assert loaded.registry == "ghcr.io"
    assert loaded.namespace == "acme-corp"
    assert loaded.resolve_image_base("erpnext-acme") == "ghcr.io/acme-corp/erpnext-acme"


def test_the_manifest_overrides_the_machine_wide_default(monkeypatch, tmp_path):
    """Otherwise a machine-wide namespace would silently publish a client's image into the
    operator's own account — the exact failure BR-CFG-013 exists to prevent."""
    _clear_build_config_env(monkeypatch)
    _user_config(monkeypatch, tmp_path, 'engine = "podman"\nnamespace = "datahenge"\n')
    manifest = _deployment(tmp_path, manifest_text=_with_registry())

    loaded = config.load_build_config(manifest)

    assert loaded.namespace == "acme-corp"  # the client's, not the operator's
    assert loaded.engine == "podman"  # machine facts still come from the machine


def test_env_vars_still_override_the_manifest(monkeypatch, tmp_path):
    """The deliberate override, replacing what used to be cairn.local.toml (`ADR-042`):
    publish a client's deployment elsewhere for a test without editing, and committing,
    their manifest."""
    _clear_build_config_env(monkeypatch)
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", tmp_path / "absent.toml")
    monkeypatch.setenv("CAIRN_REGISTRY", "localhost:5000")
    monkeypatch.setenv("CAIRN_NAMESPACE", "scratch")
    manifest = _deployment(tmp_path, manifest_text=_with_registry())

    loaded = config.load_build_config(manifest)

    assert loaded.registry == "localhost:5000"
    assert loaded.namespace == "scratch"


def test_env_vars_override_one_key_without_discarding_the_others(monkeypatch, tmp_path):
    _clear_build_config_env(monkeypatch)
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", tmp_path / "absent.toml")
    monkeypatch.setenv("CAIRN_NAMESPACE", "scratch")
    manifest = _deployment(tmp_path, manifest_text=_with_registry())

    loaded = config.load_build_config(manifest)

    assert loaded.registry == "ghcr.io"  # still the manifest's
    assert loaded.namespace == "scratch"


def test_a_namespace_is_optional_for_registries_that_have_none(monkeypatch, tmp_path):
    _clear_build_config_env(monkeypatch)
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", tmp_path / "absent.toml")
    manifest = _deployment(tmp_path, manifest_text=_with_registry(namespace=None))

    loaded = config.load_build_config(manifest)

    assert loaded.registry == "ghcr.io"
    assert loaded.namespace is None
    assert loaded.resolve_image_base("erp") == "ghcr.io/erp"


def test_a_manifest_without_a_registry_leaves_the_image_local(monkeypatch, tmp_path):
    """BR-CFG-011: absent a registry, images stay local. cairn never infers one."""
    _clear_build_config_env(monkeypatch)
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", tmp_path / "absent.toml")
    manifest = _deployment(tmp_path, manifest_text=VALID)

    loaded = config.load_build_config(manifest)

    assert loaded.registry is None
    assert loaded.resolve_image_base("erp") == "cairn/erp"


@pytest.mark.parametrize(
    ("manifest_text", "expected"),
    [
        (VALID + '\n[cairn.registry]\nnamespace = "x"\n', "requires 'host'"),
        # `engine` describes this machine, not the deployment, and must not travel with it.
        (
            VALID + '\n[cairn.registry]\nhost = "ghcr.io"\nengine = "podman"\n',
            "unknown key",
        ),
        # `registry = "ghcr.io"` under [cairn] is the natural mistake, and it must name the
        # table it should have been rather than being silently ignored.
        (
            VALID.replace(
                'image_name = "erpnext-btu-v16"',
                'image_name = "erpnext-btu-v16"\nregistry = "ghcr.io"',
            ),
            r"\[cairn.registry\] must be a table",
        ),
    ],
)
def test_the_registry_table_is_validated(monkeypatch, tmp_path, manifest_text, expected):
    _clear_build_config_env(monkeypatch)
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", tmp_path / "absent.toml")
    manifest = _deployment(tmp_path, manifest_text=manifest_text)

    with pytest.raises(ManifestInvalidError, match=expected):
        config.load_build_config(manifest)


def test_an_unreadable_user_config_is_treated_as_absent(monkeypatch, tmp_path):
    """A root-owned config must not turn every command into a traceback when the documented
    defaults would have worked."""
    _clear_build_config_env(monkeypatch)
    unreadable = tmp_path / "builder.toml"
    unreadable.write_text('engine = "podman"\n', encoding="utf-8")
    monkeypatch.setattr(config, "BUILDER_CONFIG_PATH", unreadable)
    monkeypatch.setattr(
        config.Path, "is_file", lambda self: (_ for _ in ()).throw(PermissionError("denied"))
    )

    assert config.load_build_config() == config.BuildConfig()


def test_the_sources_record_every_layer_that_contributed(monkeypatch, tmp_path):
    """`doctor` reports these, so an unexpected namespace can be traced to the layer that set
    it rather than guessed at."""
    _clear_build_config_env(monkeypatch)
    user = _user_config(monkeypatch, tmp_path, 'engine = "podman"\n')
    monkeypatch.setenv("CAIRN_NAMESPACE", "scratch")
    manifest = _deployment(tmp_path, manifest_text=_with_registry())

    loaded = config.load_build_config(manifest)

    assert loaded.sources == (str(user), str(manifest), "environment (namespace)")

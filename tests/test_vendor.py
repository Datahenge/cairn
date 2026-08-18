"""Tests for the recipe tree's build-input completeness check (BR-VEND-003)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn import vendor
from cairn.errors import VendorInputsMissingError

CONTAINERFILE = """\
FROM base AS builder
COPY resources/nginx/nginx-template.conf /templates/nginx/frappe.conf.template
COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench
COPY resources/start.sh /usr/local/bin/start.sh
RUN echo not-a-copy
"""


def _recipe_tree(root, containerfile: str = CONTAINERFILE) -> None:
    """Materialize a minimal recipe tree under *root*."""
    custom = root / vendor.CUSTOM_CONTAINERFILE
    custom.parent.mkdir(parents=True)
    custom.write_text(containerfile, encoding="utf-8")
    for name in ("resources/nginx/nginx-template.conf", "resources/start.sh"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


# --- assert_build_inputs (BR-VEND-003) ---------------------------------------


def test_assert_build_inputs_passes_when_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "RECIPE_DIR", tmp_path)
    _recipe_tree(tmp_path)

    vendor.assert_build_inputs()  # must not raise


def test_assert_build_inputs_raises_when_containerfile_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "RECIPE_DIR", tmp_path)

    with pytest.raises(VendorInputsMissingError, match="images/Containerfile"):
        vendor.assert_build_inputs()


def test_assert_build_inputs_raises_when_a_copied_resource_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "RECIPE_DIR", tmp_path)
    _recipe_tree(tmp_path)
    (tmp_path / "resources/start.sh").unlink()

    with pytest.raises(VendorInputsMissingError, match=r"resources/start\.sh"):
        vendor.assert_build_inputs()


def test_context_copies_skips_build_stage_copies(tmp_path):
    """Only build-context paths are required; `COPY --from=<stage>` sources are not."""
    containerfile = tmp_path / "Containerfile"
    containerfile.write_text(CONTAINERFILE, encoding="utf-8")

    assert vendor._context_copies(containerfile) == [
        "resources/nginx/nginx-template.conf",
        "resources/start.sh",
    ]


def test_resolves_accepts_a_glob(tmp_path):
    """A wildcard COPY source is satisfied by at least one match."""
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "a.conf").write_text("x", encoding="utf-8")

    assert vendor._resolves(tmp_path, "resources/*.conf")
    assert not vendor._resolves(tmp_path, "resources/*.missing")


# --- recipe_commit (BR-BUILD-011, ADR-059) -----------------------------------


def test_recipe_commit_reads_git_log(monkeypatch):
    def _run(command, **kwargs):
        assert command[:4] == ["git", "log", "-1", "--format=%H"]
        return type("R", (), {"returncode": 0, "stdout": "deadbeef\n"})()

    monkeypatch.setattr(vendor.subprocess, "run", _run)

    assert vendor.recipe_commit() == "deadbeef"


def test_recipe_commit_degrades_to_empty_when_git_fails(monkeypatch):
    monkeypatch.setattr(
        vendor.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": ""})(),
    )

    assert vendor.recipe_commit() == ""


def test_recipe_commit_degrades_to_empty_when_git_is_missing(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(vendor.subprocess, "run", _raise)

    assert vendor.recipe_commit() == ""


# --- image reference has no silent fallback (BR-VEND-006) --------------------


def _recipe_compose_files() -> list[Path]:
    """Every shipped compose file in the owned recipe tree."""
    recipe = Path(vendor.__file__).parent / "recipe"
    return [recipe / "compose.yaml", *sorted((recipe / "overrides").glob("*.yaml"))]


@pytest.mark.parametrize("path", _recipe_compose_files(), ids=lambda p: p.name)
def test_recipe_image_reference_has_no_default(path: Path) -> None:
    """BR-VEND-006: the image reference must never carry a `:-` fallback.

    Upstream ships `${CUSTOM_IMAGE:-frappe/erpnext}`, which suits an audience trying stock
    Frappe and actively harms cairn's, where the custom image *is* the deployment: a `:-`
    default suppresses Compose's unset-variable warning, so a hand-run `docker compose up -d`
    starts somebody else's image against a real site in silence. This guards the whole
    recipe tree, not just the two files that carried it, because the line is copied between
    compose files whenever a new override is added.
    """
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or "image:" not in stripped:
            continue
        for variable in ("CUSTOM_IMAGE", "CUSTOM_TAG"):
            if f"${{{variable}:-" in stripped:
                pytest.fail(
                    f"{path.name}:{number} gives {variable} a `:-` default — an unset value "
                    f"would silently start an unrelated image. Use `${{{variable}:?...}}`."
                )

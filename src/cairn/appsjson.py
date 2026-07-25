"""Compile the manifest's app list into the ``apps.json`` the build consumes.

Upstream's contract (`frappe_docker/docs/02-setup/02-build-setup.md`) is a JSON array of
``{"url", "branch"}`` objects, passed **only** as a build secret
(``--secret=id=apps_json,src=…``) and never as a build-arg — a build-arg would be
permanently readable via image history, and app URLs may carry tokens for private repos
(`BR-BUILD-006`).

Two contents decisions are load-bearing:

* **Frappe is absent.** It is supplied via the ``FRAPPE_PATH``/``FRAPPE_BRANCH``
  build-args; ``apps.json`` carries ERPNext and custom apps only (`BR-BUILD-004`).
* **Declared refs, not resolved commits.** ``bench init`` clones ``--branch <ref>``, and
  `BR-BUILD-005` says cairn records resolved commits in provenance but never freezes them
  into the build. The resolved commits drive `CACHE_BUST` and the image tag instead.

Manifest order is preserved verbatim into the file, because it is the install sequence
(`BR-BUILD-003`).
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .config import Manifest

#: The secret id the vendored Containerfile mounts (`Containerfile:128`).
SECRET_ID = "apps_json"


def entries(manifest: Manifest) -> list[dict[str, str]]:
    """Return the ``apps.json`` payload — apps in manifest order (BR-BUILD-003/004)."""
    return [{"url": app.url, "branch": app.ref} for app in manifest.apps]


def render(manifest: Manifest) -> str:
    """Return the ``apps.json`` document as text.

    Trailing newline and stable key order keep the rendering byte-identical for identical
    input, so `--dry-run` output can be diffed (`BR-BUILD-012`).
    """
    return json.dumps(entries(manifest), indent=2, sort_keys=False) + "\n"


@contextmanager
def secret_file(manifest: Manifest) -> Iterator[Path]:
    """Write ``apps.json`` to a private temporary file for the duration of the build.

    The file lives outside cairn's installation and outside the deployment directory
    (`BR-BUILD-011` — cairn writes no markers into its own tree), and is removed on the
    way out whether or not the build succeeded. ``mkstemp`` creates it owner-only, which
    matters while it holds repository tokens (`BR-CFG-010`).
    """
    descriptor, name = tempfile.mkstemp(suffix=".apps.json", prefix="cairn-")
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(render(manifest))
        yield path
    finally:
        path.unlink(missing_ok=True)

"""Stage every ``apps.json`` app that lives in a repository subfolder (`BR-BUILD-020`).

``bench init --apps_path`` clones each entry's ``url`` at its root, and bench has no notion
of a subfolder. For each entry carrying ``"subdir"``, this script clones the repository at the
entry's ``branch``, copies the subfolder out, commits it as a fresh local git repository on a
branch of the same name, and rewrites the entry to point at that repository. bench then
treats it as an app on disk and clones it like any other. Entries without ``"subdir"`` pass
through untouched, in order (`BR-BUILD-003`).

Runs inside the builder stage, stdlib only: ``stage_subdir_apps.py <apps.json> <workdir>``,
writing ``<workdir>/apps.json``. The caller deletes *workdir* in the same ``RUN``, because the
rewritten file still carries any token layered onto other apps' URLs (`BR-BUILD-016`). The
clone here never sees that token: credentials are stripped from the URL, and the credential
helper the Containerfile configures supplies them instead, so git cannot echo them.
"""

import json
import os
import shutil
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit


def plain(url):
    """Return a `github.com` *url* without userinfo, so cairn's token never reaches git's argv
    or output. cairn layers a token onto `github.com` URLs only, and always mounts the
    credential helper's secret beside it; any other URL is left exactly as declared."""
    parts = urlsplit(url)
    if parts.hostname != "github.com" or not (parts.username or parts.password):
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.rpartition("@")[2]))


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True)


def stage(entry, workdir, index):
    subdir = entry.pop("subdir")
    branch = entry["branch"]
    clone = os.path.join(workdir, f"clone-{index}")
    url = plain(entry["url"])
    git(
        "-c",
        "advice.detachedHead=false",
        "clone",
        "--quiet",
        "--depth",
        "1",
        "--branch",
        branch,
        url,
        clone,
    )

    source = os.path.realpath(os.path.join(clone, subdir))
    if not source.startswith(os.path.realpath(clone) + os.sep) or not os.path.isdir(source):
        sys.exit(f"subdir '{subdir}' is not a folder in {url} at '{branch}'.")

    # bench names the app's folder after this path's last part, so keep the subfolder's name.
    app = os.path.join(workdir, f"app-{index}", os.path.basename(subdir))
    shutil.copytree(source, app, symlinks=True)
    shutil.rmtree(clone)
    git("init", "--quiet", "--initial-branch", branch, cwd=app)
    git("add", "--all", cwd=app)
    git(
        "-c",
        "user.name=cairn",
        "-c",
        "user.email=cairn@localhost",
        "commit",
        "--quiet",
        "--no-verify",
        "-m",
        f"{subdir} at {branch}",
        cwd=app,
    )
    entry["url"] = os.path.abspath(app)


def main(apps_json, workdir):
    with open(apps_json, encoding="utf-8") as handle:
        entries = json.load(handle)
    os.makedirs(workdir, exist_ok=True)
    for index, entry in enumerate(entries):
        if "subdir" in entry:
            stage(entry, workdir, index)
    with open(os.path.join(workdir, "apps.json"), "w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2)


if __name__ == "__main__":
    main(*sys.argv[1:])

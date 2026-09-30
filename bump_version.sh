#!/bin/bash
#
# Bump the version in pyproject.toml and re-lock, so uv.lock never drifts from it.
#
# pyproject.toml is the single source of truth for the version. uv.lock records the whole
# resolved dependency graph, and this project is a node in that graph, so the lock carries a
# copy of the version too. uv keeps them in step whenever it runs -- but a bump done by hand
# never runs uv, which is how the lock sat at 0.4.9 for seven weeks and five bumps while
# pyproject moved on. Nothing warns you: the drift only surfaces if someone runs the check.
#
# Usage:
#     ./bump_version.sh              # patch bump, e.g. 0.4.15 -> 0.4.16
#     ./bump_version.sh 0.5.0        # set an explicit version
#     ./bump_version.sh --check      # verify pyproject and uv.lock agree; change nothing

set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f pyproject.toml ]]; then
    echo "No pyproject.toml here -- run this from the repository root." >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not on PATH. It owns uv.lock; without it a bump would drift the lock again." >&2
    exit 1
fi

current=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -1)
if [[ -z "$current" ]]; then
    echo "Could not read 'version = \"...\"' from pyproject.toml." >&2
    exit 1
fi

# --check is the guard the manual routine never had: it answers "are these two in step?"
# without touching anything, so it is safe in a pre-push hook or CI.
if [[ "${1:-}" == "--check" ]]; then
    echo "pyproject.toml is at ${current}."
    if uv lock --check >/dev/null 2>&1; then
        echo "uv.lock agrees. Nothing to do."
        exit 0
    fi
    echo "uv.lock is out of step with pyproject.toml. Run './bump_version.sh ${current}'" >&2
    echo "to re-lock without changing the version, or 'uv lock' directly." >&2
    exit 1
fi

if [[ $# -gt 0 ]]; then
    target="$1"
else
    IFS=. read -r major minor patch <<<"$current"
    target="${major}.${minor}.$((patch + 1))"
fi

if [[ ! "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "'${target}' is not a MAJOR.MINOR.PATCH version." >&2
    exit 1
fi

# Re-locking at the current version is a legitimate call -- it is how you repair a drifted
# lock without inventing a release nobody asked for -- so this is not an error.
if [[ "$target" == "$current" ]]; then
    echo "Version stays at ${current}; re-locking only."
else
    echo "Bumping ${current} -> ${target}"
    sed -i "0,/^version = \"${current}\"$/s//version = \"${target}\"/" pyproject.toml
fi

echo "Running uv lock so uv.lock follows pyproject.toml ..."
uv lock

echo
echo "Done. Changed:"
git --no-pager diff --stat -- pyproject.toml uv.lock
echo
echo "Commit with:  git commit -m 'Bump to ${target}' -- pyproject.toml uv.lock"

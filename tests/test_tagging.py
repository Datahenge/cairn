"""Tests for cache-bust and tag derivation (BR-BUILD-007, BR-BUILD-008, BR-BUILD-013)."""

from __future__ import annotations

import re

import pytest

from cairn import tagging
from cairn.resolve import RefKind, Resolution, ResolvedRef

BUILD_ARGS = {"PYTHON_VERSION": "3.14.2", "NODE_VERSION": "24.13.0", "INSTALL_CHROMIUM": "true"}


def _ref(name: str, commit: str, ref: str = "version-16", kind: RefKind = RefKind.BRANCH):
    return ResolvedRef(
        name=name, url=f"https://example.com/{name}", ref=ref, commit=commit, kind=kind
    )


def _resolution(frappe_commit="a" * 40, erpnext_commit="b" * 40, btu_commit="c" * 40):
    return Resolution(
        frappe=_ref("frappe", frappe_commit),
        apps=(_ref("erpnext", erpnext_commit), _ref("btu", btu_commit)),
    )


# --- determinism (BR-BUILD-013) ---------------------------------------------


def test_same_inputs_give_the_same_tag():
    """BR-BUILD-013: same resolved inputs -> same declared image."""
    assert tagging.primary_tag(_resolution(), BUILD_ARGS) == tagging.primary_tag(
        _resolution(), BUILD_ARGS
    )


def test_build_arg_key_order_does_not_matter():
    """[cairn.build] is a mapping; reordering its keys must not change image identity."""
    reordered = dict(reversed(list(BUILD_ARGS.items())))

    assert tagging.input_hash(_resolution(), reordered) == tagging.input_hash(
        _resolution(), BUILD_ARGS
    )


# --- CACHE_BUST (BR-BUILD-007) ----------------------------------------------


def test_moved_app_changes_the_cache_bust():
    """Editing apps.json cannot bust the cache by itself; CACHE_BUST must."""
    assert tagging.cache_bust(_resolution()) != tagging.cache_bust(_resolution(btu_commit="d" * 40))


def test_moved_frappe_changes_the_cache_bust():
    """BR-BUILD-007 (revised): FRAPPE_BRANCH enters the cache key by name, so a branch
    that moves would otherwise reuse a stale bench-init layer."""
    assert tagging.cache_bust(_resolution()) != tagging.cache_bust(
        _resolution(frappe_commit="d" * 40)
    )


def test_build_args_change_the_tag_but_not_the_cache_bust():
    """The two hashes answer different questions and must not be conflated.

    A different Python version is a different image, so it must change the tag. It is not
    a reason to re-clone every app, so it must not change the cache bust — the engine's own
    layer cache already accounts for a changed build-arg.
    """
    other_args = {**BUILD_ARGS, "PYTHON_VERSION": "3.13.1"}

    assert tagging.input_hash(_resolution(), other_args) != tagging.input_hash(
        _resolution(), BUILD_ARGS
    )
    assert tagging.cache_bust(_resolution()) == tagging.cache_bust(_resolution())


def test_swapping_two_apps_urls_changes_the_hash():
    """Names are hashed alongside commits, so a re-pointed app is not a cache hit."""
    swapped = Resolution(
        frappe=_ref("frappe", "a" * 40),
        apps=(_ref("btu", "b" * 40), _ref("erpnext", "c" * 40)),
    )

    assert tagging.cache_bust(swapped) != tagging.cache_bust(_resolution())


# --- input hash / tags (BR-BUILD-008) ---------------------------------------


def test_changed_build_arg_changes_the_input_hash():
    """Same sources, different Python version -> a different image, so a different tag."""
    other = {**BUILD_ARGS, "PYTHON_VERSION": "3.13.1"}

    assert tagging.input_hash(_resolution(), other) != tagging.input_hash(_resolution(), BUILD_ARGS)


@pytest.mark.parametrize(
    ("frappe_ref", "expected"),
    [
        ("version-16", "v16"),
        ("version-15", "v15"),
        ("v15.0.0", "v15.0.0"),
        ("develop", "develop"),
        ("feature/some_thing", "feature-some_thing"),
    ],
)
def test_legible_slug(frappe_ref, expected):
    """BR-BUILD-008: the legible half aids recognition; the hash guarantees uniqueness."""
    assert tagging.legible_slug(frappe_ref) == expected


def test_primary_tag_shape():
    """BR-BUILD-008: <legible>-<inputhash>."""
    tag = tagging.primary_tag(_resolution(), BUILD_ARGS)
    legible, _, digest = tag.rpartition("-")

    assert legible == "v16"
    assert len(digest) == tagging.DIGEST_LENGTH
    assert digest.isalnum()


def test_tags_pair_includes_the_moving_tag():
    """BR-BUILD-008: cairn also applies a moving `latest`."""
    primary, moving = tagging.tags(_resolution(), BUILD_ARGS)

    assert moving == "latest"
    assert primary.startswith("v16-")


def test_tag_is_valid_for_an_oci_registry():
    """Tags must match [A-Za-z0-9_][A-Za-z0-9._-]* to be pushable."""
    tag = tagging.primary_tag(_resolution(), BUILD_ARGS)

    assert re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}", tag)

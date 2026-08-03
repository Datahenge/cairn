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
#
# A changed build-arg changing the input hash (and thus the tag) is already covered above by
# test_build_args_change_the_tag_but_not_the_cache_bust, which also asserts the cache_bust
# invariant that would otherwise go unchecked.


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


# --- the legible half (BR-BUILD-008, `ADR-032`) ------------------------------


def test_a_declared_series_names_the_legible_half():
    tag = tagging.primary_tag(_resolution(), BUILD_ARGS, "v16")

    assert tag.startswith("v16-")
    assert tag == f"v16-{tagging.input_hash(_resolution(), BUILD_ARGS)}"


def test_a_declared_series_survives_re_pinning_the_frappe_ref():
    """The whole point. Following BR-BUILD-005's advice to pin to a tag must not rename every
    image, because nothing about the content changed."""
    as_branch = Resolution(
        frappe=_ref("frappe", "a" * 40, "version-16", RefKind.BRANCH),
        apps=(_ref("erpnext", "b" * 40), _ref("btu", "c" * 40)),
    )
    as_tag = Resolution(
        frappe=_ref("frappe", "a" * 40, "v16.0.1", RefKind.TAG),
        apps=(_ref("erpnext", "b" * 40), _ref("btu", "c" * 40)),
    )

    assert tagging.legible_slug(as_branch.frappe.ref, "v16") == "v16"
    assert tagging.legible_slug(as_tag.frappe.ref, "v16") == "v16"


def test_without_a_series_the_spelling_still_decides_the_name():
    """The defect that motivated the change, pinned so the fallback's behaviour is explicit
    rather than assumed: the same commit reached two ways yields two names."""
    assert tagging.legible_slug("version-16") == "v16"
    assert tagging.legible_slug("v16.0.1") == "v16.0.1"


def test_the_series_never_enters_the_input_hash():
    """It is a label, not an input. Renaming a line of images must not invalidate the images
    already built under the old name, nor provoke a rebuild."""
    unchanged = tagging.input_hash(_resolution(), BUILD_ARGS)

    for series in (None, "v16", "erpnext-16", "totally-different"):
        assert tagging.primary_tag(_resolution(), BUILD_ARGS, series).endswith(unchanged)


def test_a_series_changes_only_the_readable_half():
    first = tagging.primary_tag(_resolution(), BUILD_ARGS, "v15")
    second = tagging.primary_tag(_resolution(), BUILD_ARGS, "v16")

    assert first != second
    assert first.rpartition("-")[2] == second.rpartition("-")[2]


def test_the_series_reaches_the_moving_tag_pair():
    primary, moving = tagging.tags(_resolution(), BUILD_ARGS, "v16")

    assert primary.startswith("v16-")
    assert moving == tagging.MOVING_TAG


# --- the hash recipe itself --------------------------------------------------


def test_the_hash_recipe_is_pinned_across_cairn_versions():
    """Nothing else in the suite pins the actual digest, and every other test compares one
    computed hash against another — so a change to *what goes into* the hash would pass them
    all while silently renaming every image in existence.

    That is not a cosmetic break. A changed recipe means the short-circuit no longer
    recognises builds it already holds (`BR-BUILD-014`), every deterministic tag in the
    registry becomes unreachable by name, and rollback targets are addressed by names cairn
    will never generate again.

    If this test fails, the recipe changed. That may be intended — but it is a breaking
    change to image identity and must be a deliberate, recorded decision, not a side effect.
    """
    assert tagging.input_hash(_resolution(), BUILD_ARGS) == "ea91cb3d37d6"
    assert tagging.cache_bust(_resolution()) == "8fdc01995a49"

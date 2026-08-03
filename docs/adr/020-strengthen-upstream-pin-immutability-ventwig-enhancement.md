---
status: exploratory
owner: technical
purpose: ADR-020 — Strengthen upstream-pin immutability (ventwig enhancement)
---

# ADR-020 — Strengthen upstream-pin immutability (ventwig enhancement)

The vendored pin currently uses a release **tag** (ventwig 0.2.0 clones via
`git clone --depth 1 --branch <ref>`, which cannot take a raw SHA). Tags are mutable
upstream — they can be force-moved or deleted. Our committed tree + `.ventwig.lock`
already makes *builds* immutable regardless (`ADR-007`), but a *re-sync* could silently
pull a moved tag. Options:
- **(a)** status quo — tag pin + committed-tree/lock anchor;
- **(b)** teach ventwig to pin by immutable commit **SHA**;
- **(c)** teach ventwig to verify, on `sync`, that `ref` still resolves to the commit
  recorded in `.ventwig.lock`, and refuse on mismatch;
- **(b)+(c)**.

**Lean:** at minimum (c) — cheap, high-value guard against ref movement whether pinning
by tag or SHA — ideally (b)+(c). This is a ventwig enhancement (Brian owns ventwig),
tracked here; **not a cairn blocker**. `BR-VEND-002` is written pin-mechanism-
agnostic so nothing here changes when this lands. _Open._

# Open Decisions

Unresolved questions, each with current lean/recommendation where one exists.
IDs continue the `ADR-00N` sequence; when closed, a decision moves to
`01-decisions-closed.md` keeping its ID.

_Last updated: 2026-07-21_

---

### ADR-020 — Strengthen upstream-pin immutability (ventwig enhancement)
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

---

### ADR-021 — Deliberate fork of frappe_docker as the sanctioned escape hatch
frappe_docker is **MIT-licensed** and adds *no capability* to Frappe/ERPNext — it merely
codifies the documented manual install into a repeatable recipe. So forking it into our
own spinoff is legally permitted (retain the notice) and defensible by transparency
(publish the Dockerfile + build commands).

**Stance:** a fork is the **sanctioned escape hatch** for control we cannot get while
vendoring unmodified (`ADR-001`) — e.g. hard commit-pinning (see `ADR-020`, and the
build immutability model in `docs/requirements/02-build.md`), which is impossible via
bench's `git clone --branch` without editing the vendored tree. If such a need becomes
essential, the honest move is a *deliberate, eyes-open fork recorded as its own decision*
— not silent local edits (which `BR-VEND-004` forbids) nor Option C's build-time git-
mirror machinery.

**Cost to weigh when the time comes:** a fork transfers frappe_docker's real value — the
*continuous maintenance* of a correct recipe as Python/Node/wkhtmltopdf/Debian/Frappe
churn — onto us, and forfeits the deliberate drift-checked sync we built with ventwig
(`ADR-007`). Therefore: **deferred, not a default.** Revisit only against a concrete,
essential need. _Open._

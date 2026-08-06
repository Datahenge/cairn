---
status: authoritative
owner: technical
purpose: ADR-055 — docs_check.py's default word-count ceiling raised from 1800 to 2200
---

# ADR-055 — docs_check.py's default word-count ceiling raised from 1800 to 2200

**Decided:** 2026-08-04

**Problem.** `ai/tools/docs_check.py`'s DOC002 check (`DEFAULT_MAX_WORDS = 1800`) had, in practice,
become a check that always failed on the project's three most substantial requirement docs
(`02-build.md`, `03-deploy.md`, `06-cli.md`) and was "fixed" by bumping their
`.docs_check_allowlist` entries — repeatedly, same-day, by just enough to clear the next
addition. Raised by Brian: a ceiling that gets widened every cycle to accommodate whatever
just landed isn't testing anything — it's the documentation equivalent of editing a failing
unit test instead of fixing the root cause.

**Decision:**

- `DEFAULT_MAX_WORDS` raised from 1800 to **2200**. Against the actual distribution across
  `docs/requirements/` (six files at 414–1519 words needing no override; three at
  1986–3129 needing one under the old default), 1800 drew the line through the middle of the
  project's normal shape rather than around its actual outliers.
- `docs/requirements/02-build.md`'s override **removed** — its 1986 words clear the new 2200
  default without one.
- `docs/requirements/06-cli.md`'s override raised from 3150 to **4000** — real headroom above
  its current ~3130 words, not the few-dozen-word margin it had drifted to. See
  `.docs_check_allowlist` for the reasoning on where an actual split (not just another bump)
  becomes the right call for that file.
- `docs/requirements/03-deploy.md`'s override (2450, actual 2362) is left as-is — still above
  the new 2200 default, correctly.

**Why not remove the ceiling entirely.** A check with no ceiling can't distinguish genuine
growth from sprawl (restated content, drift, scope creep) at all — it would just stop asking
the question. The problem wasn't that the check fires; it's that 1800 was calibrated for a
different shape of document than this project's requirement docs actually take, so it fired on
routine, legitimate growth instead of on the cases actually worth a pause.

**Scope.** `ai/tools/docs_check.py` (`DEFAULT_MAX_WORDS`), `.docs_check_allowlist`. No requirement
or code behavior changed — tooling/convention only.

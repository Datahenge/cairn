---
status: authoritative
owner: technical
purpose: Owns the voice, structure, and reader-path rules for everything under userdocs/.
---

# cairn user documentation: style and structure

This document governs everything under `userdocs/`. It is written to be read by an agent
before writing or editing documentation, and applied without further instruction. It is
Path 1 of the fork at the top of `AGENTS.md`.

It does not govern `README.md`, code comments, docstrings, `CHANGELOG.md`, or anything
under `ai/` or `docs/`.

The rules below own voice, structure, and the reader's path. They do not displace the
project invariants that bind on every path: internal identifiers never appear in
user-visible text, no command or key is documented without verifying it in `src/cairn/`,
a gap is a question for Brian rather than something to fill in, and the revision is
recorded in `docs/CHANGELOG.md` in the same change.

---

## 1. Who you are writing for

One reader, in one situation: a technical person who administers or integrates ERPNext,
who has landed here because they suspect their current deployment process is worse than
it needs to be, and who has not yet decided to trust this project.

They are competent. They know Docker, SSH, and systemd. Do not explain those.

They are also not yet convinced, not yet installed, and not yet in possession of your
vocabulary. Do not assume any of the three.

## 2. The reader's path

The documentation is ordered as a funnel. Each tier assumes the reader has finished the
one above it and has not read anything below it.

| Tier | Pages | The reader's question |
| --- | --- | --- |
| 1. Orientation | `index.md`, `why-cairn.md` | What is this, and why would I care? |
| 2. Understanding | `workflow.md`, `concepts.md` | What would my life look like? |
| 3. Doing | `install.md`, `setup/*` | How do I stand it up? |
| 4. Operating | `operating/*` | How do I live with it? |
| 5. Reference | `reference/*` | What is every flag and key? |

**Never organize navigation around the software's internal decomposition.** The three
roles (registry, builder, target) are how cairn is built, not how it is encountered.
Roles belong in `concepts.md` and in tier 3 and 4 page titles. They must not be top-level
navigation, because a first-time reader does not yet know they are a "target."

> **The current tree does not follow this yet, deliberately.** `userdocs/` is still organized
> as `registry/`, `builder/`, `target/`. Brian deferred the restructure on 2026-08-20 until
> roughly 90% of the pages exist, since the right grouping is easier to see once the full
> catalog is known. Until then: write new pages in this voice, place them where the current
> tree puts them, and do not move navigation around one page at a time. Tracked as `W-039` in
> `docs/open/OPEN_WORK.md`.

**Information belongs to the tier where the reader needs it.** Before adding a fact to a
page, ask what question the reader of that page is holding. If the fact does not answer
it, it belongs elsewhere.

> **Anti-pattern, from the old install page.** It enumerated all thirty-odd subcommands
> across the three binaries. The reader of an install page is holding one question: is it
> installed? The list answered nothing, arrived with no context, and was silently wrong
> (it omitted `logs`, `shell`, `console`, `mariadb`, `stop`, `start`, `restart`, and
> `prune`). Correct version: name the three commands in one sentence, say that which one
> you use depends on the machine's job, and link to `concepts.md`.

## 3. Voice

### 3.1 Do not write defensively

This is the single most important rule, and the one most easily violated.

The failure looks like a sentence that states a fact, then immediately guards it against a
misreading, then restates the guard. It is the natural product of writing with the whole
codebase in mind, arguing with a reviewer who is not present. It reads as anxious, and it
buries the fact the reader came for.

State the fact. Stop. If a genuine misconception is likely, address it in its own
sentence, once.

> **Before**
> `--environment` is a label you choose, not something `examine` detects or validates
> against the host — nothing about the running deployment says what "environment" means.

> **After**
> `--environment` is a label you choose. A running deployment carries nothing that
> indicates which environment it is, so cairn cannot detect it for you.

One idea per sentence. One guard per idea, at most.

### 3.2 Do not use em dashes

Not as parentheses, not as a pause, not as a substitute for a colon. Use a period, a
comma, a colon, or parentheses.

This rule exists because the em dash is a symptom. Reaching for one usually means a
sentence is carrying two thoughts that want to be two sentences, or is about to defend
itself per 3.1. Removing the punctuation forces the underlying fix.

> **Before**
> Progress prints as it works — resolving refs, building, verifying the image landed,
> naming the reusable build-cache layer — and, at a terminal, the whole run is also saved
> to a transcript file, since nothing else is keeping it.

> **After**
> Progress prints as it works: resolving refs, building, verifying the image landed, and
> naming the build-cache layer. At a terminal, the run is also saved to a transcript file.

### 3.3 Do not write slogans

No coined phrases, no numbered abstractions, no aphorisms. They read as marketing, they
carry no information, and they are the first thing a skeptical reader discounts.

Banned by example: "Two pillars." "It ships code, not data." "A strict data-plane
boundary." "Low-thought."

Say the thing plainly. "cairn does not read or write your database, except for the
`bench migrate` that follows a deploy" is longer than "it ships code, not data" and
communicates roughly infinitely more.

### 3.4 Lead with the reader's benefit, not the implementation

> **Before**
> A thin, opinionated wrapper around Frappe/ERPNext's Docker build tooling, built from
> cairn's own owned Docker build recipe.

> **After**
> Frappe + ERPNext + your custom apps, on one VPS, running the commit you last pushed.

"Wrapper," "opinionated," "thin," and "tooling" describe the code to a maintainer. The
after version describes an outcome to a stranger.

### 3.5 Mechanics

- Second person, present tense, active voice. "You push a commit." Not "a commit is
  pushed" and not "the operator pushes a commit."
- Short sentences. If a sentence needs a comma to survive, consider two sentences.
- Prefer the concrete noun to the abstract one. "The compose file," not "the deployment
  configuration surface."
- No exclamation points. No emoji in body text.
- No hedging adverbs: "simply," "just," "merely," "obviously," "of course." Everything is
  obvious to whoever wrote it.
- No "note that," "it is worth mentioning that," "keep in mind that." Delete the preamble
  and keep the sentence.
- Bold is for the load-bearing clause of a paragraph, used sparingly. Never bold a whole
  sentence. Never bold for emphasis in the middle of an already-emphatic sentence.
- Headings are sentence case, and describe what the reader will do or learn, not the
  component involved. "Taking the stack down," not "Stop/start semantics."

## 4. Structure of a page

Every page opens with one or two sentences stating what the page is for and who should be
reading it. No preamble before that.

Every tier 2, 3, and 4 page ends with an explicit next step. A reader should never finish
a page without knowing where to go.

**Prerequisites go at the top, as prose, not as a bulleted contract.** A reader who has
followed the funnel already meets them. A reader who arrived from a search engine needs to
find out in one sentence that they are in the wrong place.

**Do not restate a page's own table of contents.** MkDocs already renders it.

Admonitions (`!!! note`, `!!! warning`) are for content that is genuinely out of the
reading flow: a security consequence, a destructive operation, a footgun. If everything on
a page is in an admonition, nothing is.

## 5. Commands, output, and examples

- **Never document a command, flag, or configuration key without verifying it exists in
  the source.** Documentation invented from plausibility is the single most expensive kind
  of error this project can ship, because it is indistinguishable from documentation until
  someone runs it.
- **Terminal output must be real**, copied from an actual run and anonymized, not
  composed. Fabricated output that does not match the code teaches the reader to distrust
  every other block on the page.
- One consistent example deployment throughout: client `acmecorp`, site
  `erp.acmecorp.com`, environment `production`, image `erpnext-v16`. Do not invent a new
  fictional client per page.
- Show the safe form first. Where a command has `--dry-run`, show it before the real
  invocation, every time.
- Do not annotate a command block with a comment explaining what the reader is about to
  read. Explain before the block, in prose.

## 6. Honesty conventions

These already exist in the docs and are correct. Formalize them.

**Per-page verification footers stay.** Ending a page with a note stating which verbs have
been exercised against a live host and which have not is credibility, not weakness. Keep
the italic footer form.

**Project-status disclaimers do not go on `index.md`.** A reader deciding whether to care
must not first read an inventory of which pages are unverified. Orientation pages sell;
verification footers live where the commands live.

**Say "I don't know" in the docs rather than guessing.** If behavior is unverified, write
that it is unverified. Never fill a gap with what the code probably does.

**Comparison pages carry a re-verification date.** Any page describing another project
(currently `why-cairn.md`) states the commit or date it was checked against, and must be
re-verified whenever it is edited. Upstream projects change: frappe_docker moved its
documented build from `--build-arg=APPS_JSON_BASE64` to a BuildKit secret, which silently
invalidated a claim that had been true for years.

**Never write a comparison as a takedown.** cairn descends from frappe_docker. The
defensible argument is about scope: frappe_docker ships parts on purpose and does not ship
a lifecycle on purpose. Credit what is inherited, explicitly.

## 7. Vocabulary

Use these terms and only these terms. Define each once, in `concepts.md`, and link there
on first use per page.

| Term | Means | Do not also call it |
| --- | --- | --- |
| manifest | the `cairn.toml` describing one environment's apps and registry | config, spec, definition |
| descriptor | `/etc/cairn/adopt.toml` on a target, describing what that host runs | target config, adopt file |
| environment | a named, moving registry tag a target watches (`production`, `staging`) | stage, deployment, instance |
| environment tag | the registry tag an environment moves | the pointer, the moving tag |
| input hash | the digest of the resolved build inputs | build hash, content hash |
| hold | a deliberately stopped environment that automation will not resume | pause, freeze, maintenance mode |
| converge / reconcile | bringing a host to the image its environment tag names | deploy, sync, update |
| target | a machine running a deployment under cairn's management | host, server, node |
| builder | a machine that builds and pushes images | build host, CI |

"Deploy" is acceptable as an ordinary English verb in orientation pages. Below tier 2, use
"converge" or "reconcile" for what cairn actually does.

## 8. Before committing

Check every item. Each one has been violated in this repository's documentation before.

1. No em dashes anywhere in the diff.
2. No sentence states a fact and then defends it twice.
3. No coined phrase, slogan, or numbered abstraction.
4. Every command, flag, and configuration key appears in `src/cairn/`.
5. Every terminal block is real output, not composed.
6. Every fact on the page answers the question the reader of that page is holding.
7. The page opens by saying what it is for.
8. The page ends by saying where to go next.
9. Nothing unverified is stated as verified.
10. Read the diff aloud. Anything that sounds like a product launch gets rewritten.

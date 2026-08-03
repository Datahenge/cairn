---
status: authoritative
owner: technical
purpose: ADR-038 — The image belongs in the account that owns the source
---

# ADR-038 — The image belongs in the account that owns the source

**Decided:** 2026-07-25 · **Raised by Brian, and it should have been raised far earlier**
Every registry decision so far — `ADR-009` registry-agnosticism, `BR-CFG-011`'s image base,
`ADR-036`'s client — was made without ever stating *whose account the image lands in*. The
documented example throughout was `ghcr.io/datahenge/…`, and `ABOUT_GHCR.md` mentioned the
ownership problem only as the fourth bullet of a subsection. That is a professional-liability
constraint on the whole deploy architecture, and it belonged in the requirements before the
first line of registry code.

Brian's statement of it: he is an ERPNext consultant who builds **clients'** private
customizations and apps. **He must never be the sole owner of a client's image.** If the
relationship ends badly, the client is left unable to deploy or roll back software they own —
"the equivalent of holding a client's business hostage." He also will not maintain one GitHub
account per client: browsers cache logins, and "which account am I in right now" is both costly
and genuinely dangerous.

**Decision:** the image belongs in the account that owns the source. Recorded as `BR-CFG-013`:
cairn MUST support publishing to a namespace the operator does not own, MUST NOT assume the
operator's own, and MUST NOT infer one from anything.

**One of Brian's three objections does not survive contact with the mechanism.** A GHCR namespace
can be an **organization the operator does not own**. The client creates (or already has) a
GitHub org, adds the operator's *single* account, and the package belongs to the client's org:
the operator pushes with one account and one token, authorization resolves server-side, billing
accrues to the client, and revoking membership at the end of an engagement leaves the client
whole. The objection was to one-account-per-client, which was never the only pattern — it was
simply the only one documented.

**A fourth objection, raised in follow-up, is the most useful of the four**, because it survives
whatever registry is chosen. Brian asked whether write access to a client's registry is
*boundless* — could he write or overwrite all 100 of their packages? — and named the reason it
matters: "not because I would be malicious, but because I can make mistakes. I'm a few typos away
from destroying their non-ERPNext images." He contrasted GitHub's per-repository model, where a
client grants read on 5 repos, write on 2, and nothing at all on the other 50.

Factually, GHCR is better than he feared: `write:packages` is a ceiling on what the *token* may
attempt, not a grant. Packages carry their own Read/Write/Admin access list, plain org membership
conveys nothing on existing private packages, repo-linked packages **inherit the repo's
permissions** (so the per-repo model he likes *is* available for packages), and a mistyped push
either creates a new package or is denied — it cannot overwrite one he was never granted. The
genuinely dangerous configuration is being made an org owner, which is a setup mistake to avoid
rather than a property of the model.

But the principle is right and was unstated, so it is now `BR-CFG-013`'s second half: **the
operator's credential MUST be scopeable to the images of the engagement and nothing else.**
Least privilege here is not primarily a security control — it is *liability containment for the
operator*. A credential that can write exactly one repository cannot be the cause of a
catastrophe, which protects the consultant at least as much as the client. This becomes a
**selection criterion** rather than a preference: it is why per-repository IAM scoping (ECR,
Artifact Registry) ranks above a registry whose credentials are account-wide.

**The cost objection survives, and is the one that actually constrains the choice.** GitHub
Packages prices multi-gigabyte artifacts badly regardless of who pays: a small included
allowance, then per-GB storage at roughly 2.5× a purpose-built registry's, plus per-GB egress on
every pull to a VPS. Purpose-built registries (ECR, Artifact Registry, ACR, DigitalOcean) price
storage flat with no small cap, and egress is often free when the target is in the same cloud.
Brian's point about `frappe_docker` having no intermediate-image seam compounds it exactly as it
compounds build time (`ADR-021`, register entry 1): every build is a fresh full-size layer, so
layer sharing buys almost nothing and each retained rollback version costs close to a full image.

**Therefore cairn takes no position on the registry product.** Two patterns are documented as
supported — a client-owned GitHub org, and a client-owned cloud registry — with the choice
per-engagement on cost and on where the client's VPS already lives. A registry on the client's
own VPS is recorded as a third possibility, noting that its rollback history then shares a
failure domain with the host it would roll back.

**The operator's own namespace remains correct for the operator's own projects.** `datahenge` was
never wrong; it was wrong as a *default*.
*(BR-CFG-013, BR-CFG-014, BR-CFG-009, BR-CFG-011, ADR-009, ADR-036, ADR-039)*

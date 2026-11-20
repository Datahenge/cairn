---
status: exploratory
owner: technical
purpose: ADR-082 — proposed; the recipe's frontend sends an explicit cache policy for /assets so browsers and CDNs never keep stale plain-path JavaScript after a deploy
---

# ADR-082 — The frontend states a cache policy for `/assets`

**Proposed:** 2026-11-20 (analysis from a stale-JavaScript incident on a client target; awaiting
Brian). **Nothing here is accepted.** The recommendation and its alternatives are recorded so
Brian can rule on them.

**Would add:** a `BR-VEND` requirement for the frontend's asset cache policy, numbered on
acceptance. **Relates to:** `BR-VEND-001`, `ADR-059`, `ADR-074`, `ADR-081`.

## Context

Findings are in
[`04h-lessons-frappe-asset-caching.md`](../technical/04h-lessons-frappe-asset-caching.md). In short:

1. Frappe gives hashed URLs only to `*.bundle.*` files. Apps that list plain
   `/assets/<app>/js/...` paths in `app_include_js` (or `app_include_css`) get the same URL on
   every deploy.
2. The recipe's nginx sends no `Cache-Control` for `/assets`, so browsers and any CDN in front
   choose a lifetime. Behind Cloudflare that was 4 hours, at the browser and at the edge.
3. Result: after a deploy, users can run an app's old form scripts against new server code for
   hours. A normal reload does not fix it.

cairn owns the recipe outright (`ADR-059`), so cairn can fix the cause for every Frappe app it
serves, without any app changing.

## Proposal (recommendation, awaiting Brian)

In `nginx-template.conf`, split `/assets` into two locations:

| Files | Header |
| --- | --- |
| Hashed bundles: `/assets/<app>/dist/**/*.<HASH>.(js\|css\|map)`, hash = eight uppercase letters or digits | `Cache-Control: public, max-age=31536000, immutable` |
| Everything else under `/assets` | `Cache-Control: no-cache` |

`no-cache` means the browser keeps the file but checks it with the origin before each use.
nginx already sends `ETag`, so an unchanged file costs a 304 with no body. Desk is a
single-page application, so these checks happen on full page loads, not on every navigation.

Implementation notes:

- nginx does not inherit a server-level `add_header` into a location that sets its own. Each
  new location must `include /etc/nginx/snippets/security_headers.conf;` again, as the
  `/files/` location already does.
- The hashed-file pattern should be tested against Frappe's current esbuild naming at the
  pinned series and fail safe: a file the pattern misses falls into `no-cache`, never into
  `immutable`.

### Opting out

The frontend's config is rendered at start by `nginx-entrypoint.sh` through `envsubst`, the same
way as `PROXY_READ_TIMEOUT` and `CLIENT_MAX_BODY_SIZE`. A frontend environment variable (name
to be chosen) could select the policy, defaulting in the entrypoint when unset. Because the
operator owns the compose file after the first render (`ADR-074`), an existing target picks up
the entrypoint default with no compose edit.

## Effect on existing deployments

- **No app has to change.** Plain-path apps keep working; their files are revalidated instead of
  cached blind. Bundled apps cache better than before.
- **Adoption follows the image.** The template is baked into the image by `cairn-build`, so a
  target changes behaviour only when it runs an image built with a cairn release that contains
  this. A client that pins its cairn version adopts it when it chooses. A CI pipeline that
  layers app source onto an older base image (see the lessons file) picks it up only on its next
  full build.
- **A CDN in front still matters.** Cloudflare normally honours an origin `Cache-Control`, but
  whether a zone's "Browser Cache TTL" setting overrides it, and how its edge treats `no-cache`,
  have **not been tested**. Verify on a live target before the user docs make any claim.

## Alternatives weighed (Brian has not ruled on these)

- **Leave caching to apps.** Each app converts to bundles, or adds a content hash to each plain
  include path (`?v=<hash>`). Both work and both stay available to apps. Neither is something
  cairn can do for an app, and neither helps the next app that uses plain paths.
- **cairn rewrites app include paths.** Out of bounds: cairn does not edit application code.
- **Purge the CDN on each deploy.** Needs a CDN API token on the target and is specific to a
  provider. Worth revisiting only if the origin headers prove insufficient.
- **Do nothing and document hard reloads.** Leaves the failure in place for every plain-path
  app.

## Open for Brian

1. Accept the policy, and should the default be the new policy (recommended) or today's behaviour?
2. Name and values of the opt-out variable, or no opt-out at all.
3. Whether cairn's user docs should state what a CDN in front must do, once the Cloudflare
   behaviour above has been verified (`W-047`).

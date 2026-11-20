---
status: authoritative
owner: technical
purpose: Durable findings about how Frappe names its JS and CSS files, what the recipe's frontend tells browsers about caching them, and why a deploy can leave browsers running old code.
---

# Lessons: Frappe asset URLs, caching, and stale JavaScript after a deploy

What turned out to be true about the files a Frappe Desk page loads from `/assets`, and how
long a browser or CDN keeps them. Illuminates `BR-VEND-001` and `ADR-081`; the proposed
response is `ADR-082`.

_Last updated: 2026-11-20._

## The symptom

**Measured**, 2026-11-20, on a client's staging target built by cairn and served behind
Cloudflare. A merged change to an app's form script was in the running image, and the file the
frontend served held the new code, yet a user's browser kept running the old script until a hard
reload (Ctrl+Shift+R). Nothing was wrong with the deploy or the code.

## Frappe gives two kinds of asset URL

**Measured**, reading `frappe/utils/jinja_globals.py` (`include_script`, `bundled_asset`) at
Frappe v16.25.0.

| How the app declares it | URL the page uses | Changes when the file changes? |
| --- | --- | --- |
| A `*.bundle.js` / `*.bundle.css` entry point, e.g. `app_include_js = "myapp.bundle.js"` | `/assets/<app>/dist/js/myapp.bundle.<HASH>.js`, looked up in `sites/assets/assets.json` | Yes: `bench build` (esbuild) writes a new hash |
| A plain path, e.g. `app_include_js = ["/assets/<app>/js/form.js"]` | Exactly that path | No |

`bundled_asset()` only looks a path up in `assets.json` when it contains `.bundle.` **and does
not start with `/assets`**. Any path an app writes as `/assets/...` is passed through unchanged.
Plain paths are still supported for apps that predate v14's esbuild pipeline, and many custom
apps use them. Frappe's and ERPNext's own Desk code is all bundled, so an upgrade of either
never leaves stale Frappe code; only apps that use plain paths are exposed.

On v16 the hash is eight uppercase letters and digits: `erpnext.bundle.W4BKB7EY.js`,
`desk.bundle.<HASH>.js`, plus a `.map` beside each.

## The recipe's frontend sends no cache policy for `/assets`

**Measured**, 2026-11-20, against the frontend container directly and in
`src/cairn/recipe/resources/nginx/nginx-template.conf`.

`location /assets { try_files $uri =404; }` serves the files with `ETag` and `Last-Modified`
but **no `Cache-Control` or `Expires`**, for hashed and plain files alike. Every cache
downstream is therefore free to choose its own lifetime:

- **A browser with no proxy in front** applies heuristic freshness (commonly a fraction of the
  time since `Last-Modified`), so even a direct deployment can serve stale plain files for a
  while.
- **Cloudflare**, with no origin `Cache-Control`, applied its account default browser lifetime:
  responses reached the browser with `cache-control: max-age=14400` (4 hours). It also cached
  `.js` at its edge (`cf-cache-status: HIT`, `age: 990`), so for a time after a deploy even a
  hard reload can be answered with the old file from the edge.
- The same 4 hours applied to Frappe's hashed bundles, which could safely be cached for a year.

## A plain reload does not refresh cached scripts

**Reasoned**, not measured. Current browsers answer a normal reload's subresources from cache
while they are still fresh; only a hard reload bypasses it. An app or tool that tells users to
"refresh" after a deploy (with `location.reload()`) does not fix stale plain-path scripts.
Changing the URL or sending `Cache-Control: no-cache` does.

## A server can query-string a plain asset URL safely

**Measured**, 2026-11-20. The recipe's nginx (`try_files $uri`) ignores the query string, so
`/assets/<app>/js/form.js?v=<anything>` returns the file. `abs_url()` passes a `/`-prefixed
path through unchanged. An app can therefore bust caches itself by putting a per-file content
hash in each plain include path, with no build step. Cloudflare's default cache key includes the
query string, so this also gets past its edge.

## Bundles need `bench build`, which a source-only image layer skips

**Measured**, 2026-11-20, on a client CI pipeline that speeds up builds by appending a layer of
changed app source to a full cairn-built base image instead of rerunning `cairn-build`.
That shortcut works for plain-path JS, which is served from source as-is, but not for bundles:
the hashed file and `assets.json` only change when `bench build` runs, so a bundle edited
through a source-only layer keeps serving the base image's compiled copy. Converting an app to
bundles under such a pipeline silently stops its JS changes from deploying unless the pipeline
falls back to a full build whenever `public/` JS changes.

## Old hashed bundles disappear on a deploy unless something keeps them

**Reasoned**, from `ADR-081`'s "What it does not do". A tab opened before a deploy keeps asking
for the bundle hashes it booted with, and only the old image has them. Under hot swap, a
downstream fork of `reconcile` was observed (2026-11-20) copying the old frontend's
`apps/*/*/public/dist`, `assets/js` and `assets/css` into the new frontend, keeping copies for
24 hours. Plain-path files are not copied and need not be: they always serve the newest version.

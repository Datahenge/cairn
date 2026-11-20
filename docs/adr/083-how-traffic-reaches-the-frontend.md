---
status: exploratory
owner: technical
purpose: ADR-083 — proposed; one deploy setting names how public traffic reaches the stack's frontend (no proxy, a cairn-bundled proxy, or the operator's own), and with it which overrides, checks and hot-swap rules apply
---

# ADR-083 — How traffic reaches the frontend: none, bundled, or external

**Proposed:** 2026-11-20 (Brian's framing of the cases; the shape below is a recommendation,
awaiting Brian). **Nothing here is accepted.**

**Would add:** a `BR-DEPLOY` or `BR-CFG` requirement for the setting, numbered on acceptance.
**Relates to:** `ADR-068`, `ADR-074`, `ADR-081` (`BR-DEPLOY-025`), `BR-VEND-001`, `BR-CLI-021`.

## Context

cairn is open source, so it cannot predict how an adopter's host is laid out. Brian's cases:

1. **ERPNext is the only consumer of port 443 on the host.**
   - **1A, no hot swap.** A front-facing reverse proxy is optional.
   - **1B, hot swap.** A front-facing reverse proxy is required: two frontends exist for a few
     seconds and cannot both bind a host port, so something stable must hold the port while
     they change (`BR-DEPLOY-025` already refuses a web service that publishes a host port).
     cairn could bring its own.
2. **ERPNext shares port 443 with other applications.** A front-facing reverse proxy is
   required whatever the strategy. cairn could bring one, but the host's owner may already have
   one and a preference. On one client target the owner had installed another application and a
   Caddy edge proxy before ERPNext arrived; fitting cairn in meant editing their Caddy config by
   hand and joining the stack to their Docker network.

### What the recipe already ships

From `frappe_docker`, kept under `src/cairn/recipe/overrides/` (`ADR-059`):

| Override | Effect |
| --- | --- |
| `compose.noproxy.yaml` | `frontend` publishes 8080, plain HTTP |
| `compose.proxy.yaml` | A Traefik container on 80, HTTP |
| `compose.https.yaml` | A Traefik container on 80 and 443, Let's Encrypt |
| `compose.traefik.yaml`, `compose.custom-domain.yaml` | A shared Traefik on an external `traefik-public` network |
| `compose.nginxproxy.yaml` | `nginxproxy/nginx-proxy` on 80 |

Two facts follow:

- **The frontend's nginx never terminates TLS.** `nginx-template.conf` listens on 8080 only.
  So 1A without any proxy is plain HTTP, unless something off the host terminates TLS (a CDN
  or a cloud load balancer). A public site with its own certificate on a 1A host in practice
  uses `compose.https.yaml`, which brings Traefik.
- **The bundled Traefik suits hot swap.** It discovers containers through the Docker API by
  label, so during a swap it sees both frontends and drops the old one when it is removed, and
  `frontend` publishes no port. **Reasoned, not yet run** behind a hot swap.

## Proposal (recommendation, awaiting Brian)

One setting, read when cairn writes the first compose file (`ADR-068`) and by `doctor`
afterwards. Name and home (descriptor or manifest) to be chosen.

| Value | Case | What cairn does |
| --- | --- | --- |
| `none` | 1A | Layers `compose.noproxy.yaml`. Hot swap is refused, as `BR-DEPLOY-025` already does |
| `bundled` | 1A with TLS, 1B | Layers `compose.https.yaml` (cairn's Traefik). Hot swap allowed |
| `external` | 2 | No proxy of cairn's. Joins `frontend` to an operator-named external Docker network under a network alias (not `container_name`, which hot swap forbids). Prints a proxy snippet for review. Hot swap allowed, with the proxy requirement below stated |

### `external`: help them, don't take their control (`ADR-074`)

- **cairn never edits the operator's proxy.** It prints what to add, consistent with "cairn
  prints host configuration for review" (`docs/requirements/06b-cli-adopt.md`): for example
  Caddy (`reverse_proxy <alias>:8080` with `lb_try_duration`), nginx (`resolver 127.0.0.11`
  with a variable in `proxy_pass`), and Traefik labels.
- **The proxy requirement for hot swap:** the proxy runs in Docker on the shared network and
  resolves the frontend's name per connection, or watches the Docker API. Caddy and Traefik
  do so by default; nginx and HAProxy can with configuration (not yet tested with cairn).
- **`doctor` checks the seam:** the named network exists, the alias resolves on it, and the
  frontend answers there.

### Ownership after the first write

The compose file is the operator's after cairn writes it (`ADR-074`). Changing the setting later
does not rewrite their file; `doctor` reports where the file and the setting disagree.

## Alternatives weighed (Brian has not ruled on these)

- **Always bundle a proxy.** Simplest for 1B, but collides with case 2: a host that already
  has an edge proxy on 443 cannot run a second one.
- **Never bundle a proxy; always external.** Pushes every 1B adopter to build what cairn
  already ships.
- **TLS in the frontend's nginx, so 1A needs no proxy.** Certificate renewal would live in a
  container that every deploy replaces. Not recommended.
- **cairn edits the operator's proxy config.** Breaks `ADR-074`'s ownership line and would tie
  cairn to each proxy's config format.

## Open for Brian

1. Accept the three values, and their names?
2. Where the setting lives: target descriptor (per host) or manifest (per environment)?
3. For `bundled`, keep the inherited Traefik, or another proxy?
4. Which proxies get a printed snippet in the first version?
5. How `doctor` treats a compose file that disagrees with the setting: report only, or refuse
   hot swap until they agree?

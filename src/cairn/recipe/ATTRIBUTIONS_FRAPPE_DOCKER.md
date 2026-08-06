# Attribution: frappe_docker

The Docker build recipe and Compose configuration in `frappe_docker/` next to this file were
originally based on [`frappe/frappe_docker`](https://github.com/frappe/frappe_docker), the
official Docker packaging for the Frappe Framework and ERPNext, published by Frappe
Technologies Pvt. Ltd. under the MIT License.

cairn no longer tracks, pins, or syncs with that upstream project — the files here are cairn's
own, maintained directly and diverging freely over time. This notice exists so the origin isn't
lost once that link is gone.

## What's here

- `images/custom/Containerfile` and the files it copies from `resources/core/` — the image
  build recipe cairn's builder uses.
- `compose.yaml`, `overrides/*.yaml`, and `example.env` — the Compose stack cairn provisions
  and reconciles deployments against.

These are a subset of what upstream `frappe_docker` ships: its own documentation site, test
suite, CI workflows, contributor tooling, and alternate build strategies cairn doesn't use were
not carried over, since none of them are part of what cairn actually builds or runs. Anyone
wanting the full upstream project, including everything not kept here, can find it at the link
above.

## License

The original files are MIT licensed. That notice is preserved verbatim at
[`frappe_docker/LICENSE`](frappe_docker/LICENSE).

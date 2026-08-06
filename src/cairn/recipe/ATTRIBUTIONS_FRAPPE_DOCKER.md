# Attribution: frappe_docker

The Docker build recipe and Compose configuration next to this file were originally based on
[`frappe/frappe_docker`](https://github.com/frappe/frappe_docker), the official Docker
packaging for the Frappe Framework and ERPNext, published by Frappe Technologies Pvt. Ltd.
under the MIT License.

cairn no longer tracks, pins, or syncs with that upstream project — the files here are cairn's
own, maintained directly and diverging freely over time. This notice exists so the origin isn't
lost once that link is gone.

## What's here

- `images/Containerfile` and the files it copies from `resources/` — the image build recipe
  cairn's builder uses.
- `compose.yaml`, `overrides/*.yaml`, and `example.env` — the Compose stack cairn provisions
  and reconciles deployments against.

These are a subset of what upstream `frappe_docker` ships: its own documentation site, test
suite, CI workflows, contributor tooling, and alternate build strategies cairn doesn't use were
not carried over, since none of them are part of what cairn actually builds or runs. Anyone
wanting the full upstream project, including everything not kept here, can find it at the link
above.

## License

The original files are MIT licensed:

```
MIT License

Copyright (c) 2017 Frappe Technologies Pvt. Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

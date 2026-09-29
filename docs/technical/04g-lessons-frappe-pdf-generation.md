---
status: authoritative
owner: technical
purpose: Durable findings about Frappe/ERPNext v16 PDF generation and why the recipe's Chromium package is not wired to it.
---

# Lessons: v16 PDF generation and the recipe's Chromium

What turned out to be true about how Frappe v16 produces PDFs, and where the recipe's
`INSTALL_CHROMIUM` stops short of making it work. Illuminates `BR-VEND-001` and the `CFG` area.

_Last updated: 2026-09-29._

## v16 needs both generators, not one

**Measured**, 2026-09-29, against `frappe` and `erpnext` at `version-16` (`5c16f12`, `6bcab7c`).

`wkhtmltopdf` is the default in five places — the `Print Format` and `Print Settings` field
defaults, `print_utils.py:55`, `print_format.py:239`, `print.js:706` — and a migration patch
(`print_format/patches/sets_wkhtmltopdf_as_default_for_pdf_generator_field.py`) actively backfills
every existing row to it. So it is the default, deliberately.

But `erpnext` ships 44 print formats, and **nine declare `pdf_generator: chrome`**: Accounts
Receivable/Payable (Standard and Summary), General Ledger, Trial Balance, Balance Sheet, P&L
Statement, Cash Flow Statement. None uses Print Designer. These are wide, long, tabular financial
reports — the case wkhtmltopdf paginates worst. Chrome is not an experimental opt-in here; ERPNext
depends on it for financial reporting.

The consequence for cairn: the image needs a working `wkhtmltopdf` **and** a working Chromium.
Dropping either breaks a documented ERPNext feature.

## Frappe does not search `PATH` for Chromium

**Measured.** `find_or_download_chromium_executable()` (`frappe/utils/print_utils.py:193-222`)
opens with:

```python
if chromium_path := shutil.which(frappe.get_common_site_config().get("chromium_path", "")):
```

With no `chromium_path` key, that is `shutil.which("")`, which returns `None` — confirmed
directly, not inferred. `PATH` is never consulted. It then looks for
`{bench}/chromium/chrome-linux/headless_shell` — a chrome-for-testing layout produced by its own
`download_chromium()`, which renames `chrome-headless-shell-linux64/chrome-headless-shell` into
that shape — and failing that, **downloads Chromium over the network at request time**, pinned to
`133.0.6943.35`.

So the recipe's `INSTALL_CHROMIUM=true` (`images/Containerfile:11,68`) installs
`chromium-headless-shell` at `/usr/bin/chromium-headless-shell` and Frappe never looks there. The
package is currently inert: it costs image size and buys nothing. Worse, the fallback download
lands in `/home/frappe/frappe-bench/chromium`, which is **not** a volume (only `sites/` and
`logs/` are, `Containerfile:169-172`), so it is lost on every container recreate and re-fetched,
and it requires outbound internet from the backend container.

Failure is at least loud: `_verify_chromium_installation()` (`chrome_pdf_generator.py:88-96`)
calls `frappe.throw`. And an *unrecognised* generator degrades to wkhtmltopdf — `print_utils.py`
falls through to `get_pdf()` when no hook returns a PDF — but a chrome-selected format with no
Chromium raises rather than falling back.

`--no-sandbox` and `--disable-dev-shm-usage` are both in the launch flags
(`chrome_pdf_generator.py:121-169`), so no container capability or `/dev/shm` change is needed.

## The chrome path is functional but unfinished

Relevant because it bounds how much to trust it, and how much cairn should invest in it.

- **No test coverage at all.** 271 `test_*.py` files in `frappe`; none mentions chrome or chromium.
- `get_chrome_pdf` is decorated `@measure_time` (`pdf.py:154-165`), which unconditionally
  `print()`s its timing. In a container that goes to the logs on every chrome PDF.
- Print Designer is the first-class path; `is_print_designer` branches through header/footer
  generation and merging (`browser.py:254,375,382,387`, `pdf_merge.py:60,75`, `page.py:266`).
  Ordinary formats take the other branch.
- Self-declared gaps: one Chromium process per worker with no multi-instance logic
  (`chrome_pdf_generator.py:71`), no persistent-process support (`:76`), browser not closed when a
  worker is killed (`:15`), external Chromium "not implemented/tested yet" (`:62`), and a macOS
  path hardcoded into the developer-mode debug branch (`:110`).
- The pinned download version is Chrome 133 (≈ February 2025) on a branch dated June 2026.

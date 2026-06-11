# Print Studio

An easy, drag-and-drop **print format designer for Frappe / ERPNext**. Built so a
non-technical user can design complex invoices, challans, and labels — with QR codes,
barcodes, repeating item tables, and field-wise calculations — without writing code or
knowing database field names.

* Drag friendly-named fields onto the page (no field-name typing)
* Visual calculation builder — click fields + operators, see the live answer
* Smart Blocks — drop a whole Company Header / Items Table / Totals in one click
* Live data on the canvas (what you see is what prints)
* Saving auto-creates a Print Format that appears in the normal ERPNext print menu

---

## Install

```bash
# from your frappe-bench directory
bench get-app /path/to/print_studio        # or your git URL
bench --site yoursite.local install-app print_studio
bench --site yoursite.local migrate
bench build --app print_studio
bench restart
```

Python deps (`qrcode`, `python-barcode`, `pillow`) install automatically from
`pyproject.toml`. If your bench skips them, install once into the bench env:

```bash
./env/bin/pip install qrcode python-barcode pillow
```

> Requires Frappe **v15+**.
>
> Upgrading from 0.1.x/0.2.0? `bench --site yoursite migrate` runs a patch that removes the
> old "Print Studio" Workspace so the designer page can own `/app/print-studio`.

## Use

1. Open **`/app/print-studio`** in the Desk (this is the designer). Or open any saved layout and click **Open in Print Studio**.
2. Pick a DocType (e.g. *Sales Invoice*) — its real fields load on the left.
3. Drag fields, drop Blocks, add a QR/Barcode, build a calculation. The canvas shows
   real data from your most recent document.
4. Click **Save** and give it a name. A Print Format called **`PS · <name>`** is created.
5. Open any document of that type → **Print** → choose **`PS · <name>`**. Done.

Use **PDF preview** in the toolbar to see the server-rendered output with real
QR codes and barcodes before printing.


## Import an existing format

In the designer toolbar, **⇩ Import format** reads a file you already have and lays it
out on the canvas. Static text and headings are placed for you; you then select the ones
that should be dynamic and click **Convert to variable (field)** to bind them.

| Source | Fidelity |
|---|---|
| **PDF** | accurate — real x/y of every text line, plus lines & boxes |
| **Excel (.xlsx)** | accurate — the cell grid maps straight to positions |
| **Word (.docx)** | approximate — a vertical stack of paragraphs + tables you rearrange |
| **Image (.png/.jpg)** | dropped as a background **tracing layer**; place fields on top (OCR used only if the server has `pytesseract`) |

Parser libraries (`pymupdf`, `python-docx`, `openpyxl`, `pillow`) install with the app.
If your bench skips them: `./env/bin/pip install pymupdf python-docx openpyxl pillow`.
Image OCR is optional and never required.

## How it fits together

| Piece | Role |
|---|---|
| `Print Studio Layout` (DocType) | stores the visual layout as `config_json` |
| `print_studio.api` | meta-driven field discovery, preview data, QR/barcode, the renderer |
| Page `print-studio` | hosts the designer (isolated iframe) and bridges it to `frappe.call` |
| Auto-synced `Print Format` | makes each design printable from the standard menu |

The renderer is generic: it reads `frappe.get_meta()` so it works for **any** DocType
and its child tables / linked documents — not just invoices.

## Notes / roadmap

* **Page-repeating headers & footers**: bands typed *Repeat Top* / *Repeat Bottom* are
  intended for per-page repetition. The body renderer currently emits the one-time
  sections; wire repeating bands through the Print Format Header/Footer HTML (or switch
  the site PDF engine to WeasyPrint/Chrome for stronger paged-media support).
* QR/barcode libraries are vendored under `public/js` — no external CDN is used.
* Built by Neotec Integrated Solution.

# Copyright (c) 2026, Neotec Integrated Solution
# Public API + server-side renderer for Print Studio.
import base64
import io
import json
import re

import frappe
from frappe.utils import flt

NUM_FT = {"Currency", "Float", "Int", "Percent"}
DATE_FT = {"Date", "Datetime"}
SKIP_FT = {"Section Break", "Column Break", "Tab Break", "HTML", "Button",
           "Table MultiSelect", "Fold", "Heading"}
LINK_OK_FT = {"Data", "Small Text", "Text", "Select", "Link", "Read Only",
              "Phone", "Currency", "Float", "Int", "Percent", "Date", "Datetime"}


def _ftype(ft):
    if ft in NUM_FT:
        return "num"
    if ft in DATE_FT:
        return "date"
    return "txt"


# ---------------------------------------------------------------- field discovery
@frappe.whitelist()
def list_doctypes(search=None):
    """DocTypes a user can build a print format for (no child / single tables)."""
    filters = {"istable": 0, "issingle": 0}
    or_filters = None
    if search:
        or_filters = [["name", "like", "%{0}%".format(search)]]
    rows = frappe.get_all("DocType", filters=filters, or_filters=or_filters,
                          fields=["name"], order_by="name", limit_page_length=50)
    return [r["name"] for r in rows]


@frappe.whitelist()
def get_print_fields(doctype):
    """Return data sources grouped with friendly labels:
       { doc:{label,fields[]}, <link_field>:{label,link,fields[]}, <child_field>:{label,table,fields[]} }
    """
    meta = frappe.get_meta(doctype)
    sources = {}

    doc_fields = [{"name": "name", "label": "{0} ID".format(doctype), "type": "txt"}]
    for df in meta.fields:
        if df.fieldtype in SKIP_FT or df.fieldtype == "Table":
            continue
        doc_fields.append({"name": df.fieldname, "label": df.label or df.fieldname,
                           "type": _ftype(df.fieldtype)})
    sources["doc"] = {"label": doctype, "fields": doc_fields}

    # Link fields -> browsable as their own source (e.g. customer.gstin)
    for df in meta.fields:
        if df.fieldtype == "Link" and df.options:
            try:
                lmeta = frappe.get_meta(df.options)
            except Exception:
                continue
            lf = [{"name": "name", "label": "{0} ID".format(df.options), "type": "txt"}]
            for x in lmeta.fields:
                if x.fieldtype in LINK_OK_FT:
                    lf.append({"name": x.fieldname, "label": x.label or x.fieldname,
                               "type": _ftype(x.fieldtype)})
            sources[df.fieldname] = {"label": df.label or df.fieldname, "link": 1, "fields": lf}

    # Child tables -> repeatable sources
    for df in meta.fields:
        if df.fieldtype == "Table" and df.options:
            try:
                cmeta = frappe.get_meta(df.options)
            except Exception:
                continue
            cf = [{"name": "idx", "label": "Row No.", "type": "num"}]
            for x in cmeta.fields:
                if x.fieldtype in SKIP_FT or x.fieldtype == "Table":
                    continue
                cf.append({"name": x.fieldname, "label": x.label or x.fieldname,
                           "type": _ftype(x.fieldtype)})
            sources[df.fieldname] = {"label": df.label or df.fieldname, "table": 1, "fields": cf}

    return sources


def _jsonable(doc):
    out = {}
    for k, v in doc.as_dict().items():
        if isinstance(v, (list, dict)):
            continue
        out[k] = "" if v is None else (v if isinstance(v, (int, float)) else str(v))
    return out


@frappe.whitelist()
def get_preview_doc(doctype, name=None):
    """Real data for the live preview. Falls back to the most recent document."""
    if not name:
        rows = frappe.get_all(doctype, fields=["name"], order_by="modified desc",
                              limit_page_length=1)
        if rows:
            name = rows[0]["name"]
    if not name:
        return {}
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    out = {"doc": _jsonable(doc)}
    for df in doc.meta.fields:
        if df.fieldtype == "Link" and df.options and doc.get(df.fieldname):
            try:
                out[df.fieldname] = _jsonable(frappe.get_cached_doc(df.options, doc.get(df.fieldname)))
            except Exception:
                pass
        elif df.fieldtype == "Table":
            out[df.fieldname] = [_jsonable(r) for r in (doc.get(df.fieldname) or [])]
    return out


# ---------------------------------------------------------------- QR / barcode
def get_qr(data, ecc="M"):
    import qrcode
    from qrcode.constants import (ERROR_CORRECT_H, ERROR_CORRECT_L,
                                  ERROR_CORRECT_M, ERROR_CORRECT_Q)
    lvl = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q,
           "H": ERROR_CORRECT_H}.get(ecc, ERROR_CORRECT_M)
    qr = qrcode.QRCode(error_correction=lvl, box_size=10, border=0)
    qr.add_data(str(data or ""))
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def get_barcode(data, fmt="code128", show_value=True):
    import barcode
    from barcode.writer import ImageWriter
    cls = barcode.get_barcode_class((fmt or "code128").lower())
    buf = io.BytesIO()
    cls(str(data or "0"), writer=ImageWriter()).write(
        buf, options={"write_text": bool(show_value), "module_height": 12, "quiet_zone": 1})
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- renderer
def _resolve_sources(doc):
    sources = {"doc": doc}
    for df in doc.meta.fields:
        if df.fieldtype == "Link" and df.options and doc.get(df.fieldname):
            try:
                sources[df.fieldname] = frappe.get_cached_doc(df.options, doc.get(df.fieldname))
            except Exception:
                pass
    return sources


def _get(obj, field, default=""):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(field, default)
    return obj.get(field) if hasattr(obj, "get") else getattr(obj, field, default)


def _fmt(val, props):
    if val in (None, ""):
        return ""
    dec = props.get("decimals")
    if dec not in (None, ""):
        try:
            val = frappe.utils.fmt_money(flt(str(val).replace(",", "")), precision=int(dec))
        except Exception:
            pass
    return "{0}{1}{2}".format(props.get("prefix", ""), val, props.get("suffix", ""))


def _esc(s):
    return frappe.utils.escape_html(str(s if s is not None else ""))


def _text_style(p):
    ff = p.get("fontFamily")
    ff_css = "font-family:{0};".format(ff) if ff else ""
    nowrap = "white-space:nowrap;overflow:hidden;" if p.get("nowrap") else ""
    return ("font-size:{fs}pt;font-weight:{fw};font-style:{fi};text-align:{al};"
            "color:{c};background:{bg};line-height:1.15;padding:0 0.4mm;{ff}{nw}").format(
        fs=p.get("fontSize", 9), fw="700" if p.get("bold") else "400",
        fi="italic" if p.get("italic") else "normal", al=p.get("align", "left"),
        c=p.get("color", "#000"), bg=p.get("bg") or "transparent", ff=ff_css, nw=nowrap)


def _eval_formula(formula, sources, band, row):
    def repl(m):
        s, f = m.group(1), m.group(2)
        if row is not None and band and s == band.get("dataSource"):
            v = _get(row, f)
        else:
            v = _get(sources.get(s), f)
        v = str(v if v not in (None, "") else "0").replace(",", "")
        try:
            return repr(float(v))
        except ValueError:
            return repr(v)
    expr = re.sub(r"\{([a-zA-Z_]+)\.([a-zA-Z_0-9]+)\}", repl, formula or "")
    try:
        return frappe.safe_eval(expr)
    except Exception:
        return ""


def _print_if(p, sources, band, row):
    cond = (p.get("printIf") or "").strip()
    if not cond:
        return True
    try:
        return bool(_eval_formula(cond, sources, band, row))
    except Exception:
        return True


def _el_html(el, sources, band=None, row=None):
    t = el.get("type")
    p = el.get("props", {})
    if not _print_if(p, sources, band, row):
        return ""
    style = ("position:absolute;left:{x}mm;top:{y}mm;width:{w}mm;height:{h}mm;overflow:hidden;"
             ).format(x=el.get("x", 0), y=el.get("y", 0), w=el.get("w", 10), h=el.get("h", 5))

    def fval(src, field):
        if row is not None and band and src == band.get("dataSource"):
            return _get(row, field)
        return _get(sources.get(src), field)

    if t == "text":
        return '<div style="{0}{1}">{2}</div>'.format(style, _text_style(p), _esc(p.get("text", "")))
    if t == "field":
        return '<div style="{0}{1}">{2}</div>'.format(
            style, _text_style(p), _esc(_fmt(fval(p.get("source"), p.get("field")), p)))
    if t == "formula":
        v = _eval_formula(p.get("formula", ""), sources, band, row)
        v = _fmt(v, p) if p.get("dtype") == "number" else v
        return '<div style="{0}{1}">{2}</div>'.format(style, _text_style(p), _esc(v))
    if t == "qr":
        return '<div style="{0}"><img src="{1}" style="width:100%;height:100%;object-fit:contain"></div>'.format(
            style, get_qr(fval(p.get("source"), p.get("field")), p.get("ecc", "M")))
    if t == "barcode":
        return '<div style="{0}"><img src="{1}" style="width:100%;height:100%;object-fit:contain"></div>'.format(
            style, get_barcode(fval(p.get("source"), p.get("field")), p.get("format", "CODE128"), p.get("showValue", True)))
    if t == "image":
        src = (p.get("src", "") or "").replace(" ", "%20")
        return '<div style="{0}"><img src="{1}" style="width:100%;height:100%;object-fit:{2}"></div>'.format(
            style, src, p.get("fit", "contain"))
    if t == "rect":
        bd = "border:{0}mm solid {1};".format(p.get("borderW", 0.3), p.get("borderColor", "#333")) if p.get("border") == "all" else ""
        return '<div style="{0}{1}background:{2}"></div>'.format(style, bd, p.get("bg") or "transparent")
    if t == "hline":
        return '<div style="{0}background:{1};height:{2}mm"></div>'.format(style, p.get("color", "#000"), p.get("thick", 0.4))
    if t == "vline":
        return '<div style="{0}background:{1};width:{2}mm"></div>'.format(style, p.get("color", "#000"), p.get("thick", 0.4))
    if t == "html":
        try:
            ctx = {"doc": sources.get("doc"), "row": row}
            for k, v in sources.items():
                ctx.setdefault(k, v)
            inner = frappe.render_template(p.get("html", ""), ctx)
        except Exception:
            inner = frappe.utils.escape_html(p.get("html", ""))
        ff = "font-family:{0};".format(p.get("fontFamily")) if p.get("fontFamily") else ""
        hstyle = "font-size:{fs}pt;color:{c};text-align:{al};line-height:1.25;{ff}".format(
            fs=p.get("fontSize", 9), c=p.get("color", "#1f2733"), al=p.get("align", "left"), ff=ff)
        return '<div style="{0}{1}">{2}</div>'.format(style, hstyle, inner)
    if t == "table":
        return _table_html(el, sources, style)
    return ""


def _table_html(el, sources, style):
    p = el["props"]
    rows = _get(sources.get("doc"), p.get("source")) or []
    cols = p.get("columns", [])
    fs = p.get("fontSize", 8)
    row_mm = p.get("rowH", 6)
    fixed = p.get("heightMode") == "fixed"
    show_header = p.get("showHeader", True)
    bd = "border:0.2mm solid #bbb;" if p.get("showBorders", True) else ""
    bd_h = "border:0.2mm solid #999;" if p.get("showBorders", True) else ""
    if show_header:
        head = "".join(
            '<th style="width:{w}%;background:{bg};{bd}padding:0.3mm 0.5mm;text-align:{al}">{lb}</th>'.format(
                w=c.get("w", 10), bg=p.get("headerBg", "#eee") if p.get("showBorders", True) else "transparent",
                bd=bd_h, al=c.get("align", "left"), lb=_esc(c.get("label", "")))
            for c in cols)
        thead = "<thead><tr>{0}</tr></thead>".format(head)
    else:
        # invisible sizing row so column widths still apply when overlaying a template
        thead = "<thead><tr>" + "".join(
            '<th style="width:{w}%;height:0;padding:0;border:0"></th>'.format(w=c.get("w", 10)) for c in cols) + "</tr></thead>"
    body = ""
    for r in rows:
        body += '<tr style="height:{h}mm">'.format(h=row_mm) + "".join(
            '<td style="{bd}padding:0.3mm 0.5mm;text-align:{al}">{v}</td>'.format(
                bd=bd, al=c.get("align", "left"), v=_esc(_get(r, c.get("field"), "")))
            for c in cols) + "</tr>"
    height_css = ""
    if fixed:
        avail = max(0, el.get("h", 24) - row_mm)        # minus header row
        total = max(len(rows), int(avail / row_mm) if row_mm else len(rows))
        er = p.get("emptyRows", "lines")
        if not p.get("showBorders", True):
            er = "blank"
        ncols = len(cols)
        def _filler_td(i):
            if er == "blank":
                bd = ""
            elif er == "cols":
                bd = "border-left:0.2mm solid #bbb;" + ("border-right:0.2mm solid #bbb;" if i == ncols - 1 else "")
            else:
                bd = "border:0.2mm solid #bbb;"
            return '<td style="{0}">&nbsp;</td>'.format(bd)
        for _i in range(total - len(rows)):              # fill the box per the empty-row style
            body += '<tr style="height:{h}mm">'.format(h=row_mm) + "".join(
                _filler_td(i) for i in range(ncols)) + "</tr>"
        height_css = "height:{0}mm;".format(el.get("h", 24))
    return ('<div style="{0}{hc}"><table style="width:100%;height:100%;border-collapse:collapse;'
            'font-size:{fs}pt;table-layout:fixed">{th}<tbody>{b}</tbody></table></div>'
            ).format(style, hc=height_css, fs=fs, th=thead, b=body)


def _render_body(doc, layout):
    sources = _resolve_sources(doc)
    blocks = []
    for band in layout.get("bands", []):
        bt = band.get("type")
        if bt in ("page_header", "page_footer"):
            continue  # repeat on every page via the Print Format header/footer
        h = band.get("height", 10)
        has_table = any(e.get("type") == "table" for e in band.get("elements", []))
        if bt == "detail" and band.get("dataSource") and not has_table:
            for row in (doc.get(band["dataSource"]) or []):
                inner = "".join(_el_html(e, sources, band, row) for e in band.get("elements", []))
                blocks.append('<div style="position:relative;height:{0}mm">{1}</div>'.format(h, inner))
        else:
            inner = "".join(_el_html(e, sources) for e in band.get("elements", []))
            blocks.append('<div style="position:relative;height:{0}mm">{1}</div>'.format(h, inner))
    return '<div class="ps-root" style="position:relative;width:100%">{0}</div>'.format("".join(blocks))


def _page_number_html(pn):
    fmt = pn.get("format", "x_of_y")
    if fmt == "x_of_y":
        inner = 'Page <span class="page"></span> of <span class="topage"></span>'
    elif fmt == "x_slash_y":
        inner = '<span class="page"></span> / <span class="topage"></span>'
    else:
        inner = '<span class="page"></span>'
    al = {"R": "right", "C": "center", "L": "left"}.get(pn.get("pos", "BR")[-1], "right")
    subst = ("<script>function subst(){var v={},p=document.location.search.substring(1).split('&');"
             "for(var i in p){var z=p[i].split('=',2);v[z[0]]=unescape(z[1]);}"
             "var k=['page','topage','frompage'];for(var i in k){var e=document.getElementsByClassName(k[i]);"
             "for(var j=0;j<e.length;++j)e[j].textContent=v[k[i]];}}</script>")
    return ('<div id="footer-html" style="font-size:{sz}pt;text-align:{al};'
            'padding:2mm 6mm" onload="subst()">{inner}</div>{subst}'
            ).format(sz=pn.get("fontSize", 8), al=al, inner=inner, subst=subst)


def _header_html(doc, layout):
    """Repeating header: render the Page Top / Page Header band on every page."""
    bands = layout.get("bands", [])
    band = next((b for b in bands if b.get("type") == "page_header"), None)         or next((b for b in bands if b.get("type") == "report_header"), None)
    if not band:
        return ""
    sources = _resolve_sources(doc)
    inner = "".join(_el_html(e, sources) for e in band.get("elements", []))
    return ('<div id="header-html" style="position:relative;height:{h}mm;width:100%">{inner}</div>'
            ).format(h=band.get("height", 20), inner=inner)


def render_layout(doc, layout_name):
    """Jinja entry point used inside the auto-generated Print Format."""
    cfg = frappe.db.get_value("Print Studio Layout", layout_name, "config_json")
    if not cfg:
        return "<div>Print Studio: layout '{0}' not found.</div>".format(_esc(layout_name))
    return _assemble(doc, json.loads(cfg))


def _assemble(doc, layout):
    """Body + optional combined layout + repeating header + page numbers."""
    html = _render_body(doc, layout)
    page = layout.get("page", {}) or {}
    appended = page.get("appendLayout")
    if appended:
        cfg2 = frappe.db.get_value("Print Studio Layout", appended, "config_json")
        if cfg2:
            html += '<div style="page-break-before:always"></div>' + _render_body(doc, json.loads(cfg2))
    try:
        if page.get("repeatHeader"):
            html = _header_html(doc, layout) + html
        pn = page.get("pageNumber") or {}
        if pn.get("show"):
            html = html + _page_number_html(pn)
    except Exception:
        frappe.log_error(title="Print Studio header/footer", message=frappe.get_traceback())
    orient = page.get("orientation", "portrait")
    size = "297mm 210mm" if orient == "landscape" else "210mm 297mm"
    return '<style>@page{{size:{0};margin:0}}</style>'.format(size) + html


@frappe.whitelist()
def render_preview(doctype, docname=None, layout_json=None):
    """Server-rendered HTML for the in-designer 'true preview' (real QR/barcodes)."""
    if not docname:
        rows = frappe.get_all(doctype, fields=["name"], order_by="modified desc", limit_page_length=1)
        docname = rows[0]["name"] if rows else None
    if not docname:
        return "<div>No document found to preview.</div>"
    doc = frappe.get_doc(doctype, docname)
    doc.check_permission("read")
    return _assemble(doc, json.loads(layout_json))


# ---------------------------------------------------------------- layout CRUD
@frappe.whitelist()
def list_layouts(ref_doctype=None):
    filters = {}
    if ref_doctype:
        filters["ref_doctype"] = ref_doctype
    return frappe.get_all("Print Studio Layout", filters=filters,
                          fields=["name", "title", "slug", "ref_doctype", "modified"],
                          order_by="modified desc")


@frappe.whitelist()
def load_layout(name):
    d = frappe.get_doc("Print Studio Layout", name)
    d.check_permission("read")
    return {"name": d.name, "title": d.title, "ref_doctype": d.ref_doctype,
            "config_json": d.config_json}


@frappe.whitelist()
def save_layout(title, ref_doctype, config_json, name=None):
    if name and frappe.db.exists("Print Studio Layout", name):
        d = frappe.get_doc("Print Studio Layout", name)
    else:
        existing = frappe.db.get_value("Print Studio Layout", {"title": title}, "name")
        d = frappe.get_doc("Print Studio Layout", existing) if existing else frappe.new_doc("Print Studio Layout")
    d.title = title
    d.ref_doctype = ref_doctype
    d.config_json = config_json
    d.save(ignore_permissions=False)
    frappe.db.commit()
    return {"name": d.name, "print_format": "PS · {0}".format(d.title)}


# ---------------------------------------------------------------- import existing format
@frappe.whitelist()
def import_format(filename, content_b64, doctype, mode="text"):
    """Read a PDF / XLSX / DOCX / image into a Print Studio layout draft."""
    from print_studio import importer
    return importer.import_format(filename, content_b64, doctype, mode=mode)


def ps_address(address_name, show_title=False, gstin=True):
    """Clean multi-line formatted address for printing (excludes the '-Billing' title)."""
    if not address_name:
        return ""
    try:
        a = frappe.get_cached_doc("Address", address_name)
    except Exception:
        return ""
    lines = []
    if show_title and a.get("address_title"):
        lines.append("<b>{0}</b>".format(_esc(a.get("address_title"))))
    for fld in ("address_line1", "address_line2"):
        if a.get(fld):
            lines.append(_esc(a.get(fld)))
    cityline = ", ".join([x for x in [a.get("city"), a.get("pincode")] if x])
    if cityline:
        lines.append(_esc(cityline))
    stateline = a.get("state") or ""
    if a.get("gst_state_number"):
        stateline = (stateline + " (State Code: {0})".format(a.get("gst_state_number"))).strip()
    if stateline:
        lines.append(_esc(stateline))
    if a.get("country"):
        lines.append(_esc(a.get("country")))
    if gstin and a.get("gstin"):
        lines.append("GSTIN: " + _esc(a.get("gstin")))
    if a.get("phone"):
        lines.append("Ph: " + _esc(a.get("phone")))
    return "<br>".join(lines)


# ================================================================ CODE EXPORT
# Convert a visual layout into a standalone Jinja/HTML print format that
# developers can hand-edit and that runs without the layout record.

def ps_field(obj, source, field, decimals=None, prefix="", suffix=""):
    """Resolve a field for the generated code (doc field, row field, or linked doc)."""
    try:
        if source in ("doc", "row") or obj is None:
            v = obj.get(field) if obj is not None else ""
        else:
            link_val = obj.get(source)
            if not link_val:
                return ""
            df = obj.meta.get_field(source) if hasattr(obj, "meta") else None
            target = df.options if df else None
            v = frappe.get_cached_doc(target, link_val).get(field) if target else ""
    except Exception:
        v = ""
    return _fmt(v, {"decimals": decimals, "prefix": prefix or "", "suffix": suffix or ""})


def ps_formula(obj, formula, decimals=None):
    def repl(m):
        s, fld = m.group(1), m.group(2)
        v = ps_field(obj, s, fld)
        v = str(v if v not in (None, "") else "0").replace(",", "")
        try:
            return repr(float(v))
        except ValueError:
            return repr(v)
    expr = re.sub(r"\{([a-zA-Z_]+)\.([a-zA-Z_0-9]+)\}", repl, formula or "")
    try:
        out = frappe.safe_eval(expr)
    except Exception:
        return ""
    if decimals not in (None, ""):
        return _fmt(out, {"decimals": decimals})
    return out


JO, JC = "{{ ", " }}"
TO, TC = "{% ", " %}"


def _gen_el(el, band, in_loop):
    import json as _json
    t = el.get("type")
    p = el.get("props", {})
    st = "position:absolute;left:{x}mm;top:{y}mm;width:{w}mm;height:{h}mm;overflow:hidden;".format(
        x=el.get("x", 0), y=el.get("y", 0), w=el.get("w", 10), h=el.get("h", 5))
    detail_src = band.get("dataSource") if band else None

    def expr(source, field, fmt=True):
        if in_loop and source == detail_src:
            o, sname = "row", "row"
        else:
            o, sname = "doc", source
        args = ""
        if fmt:
            if p.get("decimals") not in (None, ""):
                args += ', decimals="{0}"'.format(p.get("decimals"))
            if p.get("prefix"):
                args += ', prefix={0}'.format(_json.dumps(p.get("prefix")))
            if p.get("suffix"):
                args += ', suffix={0}'.format(_json.dumps(p.get("suffix")))
        return 'ps_field({0}, "{1}", "{2}"{3})'.format(o, sname, field, args)

    if t == "text":
        return '<div style="{0}{1}">{2}</div>'.format(st, _text_style(p), _esc(p.get("text", "")))
    if t == "field":
        return '<div style="{0}{1}">{2}{3}{4}</div>'.format(st, _text_style(p), JO, expr(p.get("source"), p.get("field")), JC)
    if t == "formula":
        o = "row" if (in_loop) else "doc"
        dec = ', decimals="{0}"'.format(p.get("decimals")) if p.get("decimals") not in (None, "") else ""
        return '<div style="{0}{1}">{2}ps_formula({3}, {4}{5}){6}</div>'.format(
            st, _text_style(p), JO, o, _json.dumps(p.get("formula", "")), dec, JC)
    if t == "qr":
        return '<div style="{0}"><img src="{1}get_qr({2}){3}" style="width:100%;height:100%;object-fit:contain"></div>'.format(
            st, JO, expr(p.get("source"), p.get("field"), fmt=False), JC)
    if t == "barcode":
        return '<div style="{0}"><img src="{1}get_barcode({2}, "{3}", {4}){5}" style="width:100%;height:100%;object-fit:contain"></div>'.format(
            st, JO, expr(p.get("source"), p.get("field"), fmt=False), p.get("format", "CODE128"),
            "True" if p.get("showValue", True) else "False", JC)
    if t == "image":
        return '<div style="{0}"><img src="{1}" style="width:100%;height:100%;object-fit:{2}"></div>'.format(
            st, (p.get("src", "") or "").replace(" ", "%20"), p.get("fit", "contain"))
    if t == "rect":
        bd = "border:{0}mm solid {1};".format(p.get("borderW", 0.3), p.get("borderColor", "#333")) if p.get("border") == "all" else ""
        return '<div style="{0}{1}background:{2}"></div>'.format(st, bd, p.get("bg") or "transparent")
    if t == "hline":
        return '<div style="{0}background:{1};height:{2}mm"></div>'.format(st, p.get("color", "#000"), p.get("thick", 0.4))
    if t == "vline":
        return '<div style="{0}background:{1};width:{2}mm"></div>'.format(st, p.get("color", "#000"), p.get("thick", 0.4))
    if t == "html":
        return '<div style="{0}">{1}</div>'.format(st, p.get("html", ""))
    if t == "table":
        return _gen_table(el, st)
    return ""


def _gen_table(el, st):
    p = el["props"]
    cols = p.get("columns", [])
    src = p.get("source", "items")
    fs = p.get("fontSize", 8)
    row_mm = p.get("rowH", 6)
    show_h = p.get("showHeader", True)
    sb = p.get("showBorders", True)
    bd = "border:0.2mm solid #bbb;" if sb else ""
    bd_h = "border:0.2mm solid #999;" if sb else ""
    out = ['<div style="{0}"><table style="width:100%;height:100%;border-collapse:collapse;font-size:{1}pt;table-layout:fixed">'.format(st, fs)]
    if show_h:
        out.append("<thead><tr>")
        for c in cols:
            out.append('<th style="width:{w}%;{bd}background:{bg};text-align:{al};padding:0.3mm 0.5mm">{lb}</th>'.format(
                w=c.get("w", 10), bd=bd_h, bg=p.get("headerBg", "#eee") if sb else "transparent",
                al=c.get("align", "left"), lb=_esc(c.get("label", ""))))
        out.append("</tr></thead>")
    else:
        out.append("<thead><tr>")
        for c in cols:
            out.append('<th style="width:{0}%;height:0;padding:0;border:0"></th>'.format(c.get("w", 10)))
        out.append("</tr></thead>")
    out.append("<tbody>")
    out.append(TO + 'set _rows = doc.get("{0}") or []'.format(src) + TC)
    out.append(TO + "for row in _rows" + TC + '<tr style="height:{0}mm">'.format(row_mm))
    for c in cols:
        out.append('<td style="{bd}text-align:{al};padding:0.3mm 0.5mm">{o}row.get("{f}"){c}</td>'.format(
            bd=bd, al=c.get("align", "left"), o=JO, f=c.get("field", ""), c=JC))
    out.append("</tr>" + TO + "endfor" + TC)
    if p.get("heightMode") == "fixed":
        total = max(0, int((el.get("h", 24) - row_mm) / row_mm)) if row_mm else 0
        empty_bd = bd if (sb and p.get("emptyRows", "lines") != "blank") else ""
        out.append(TO + "set _fill = {0} - (_rows|length)".format(total) + TC)
        out.append(TO + "if _fill > 0" + TC + TO + "for _i in range(_fill)" + TC + '<tr style="height:{0}mm">'.format(row_mm))
        for c in cols:
            out.append('<td style="{0}">&nbsp;</td>'.format(empty_bd))
        out.append("</tr>" + TO + "endfor" + TC + TO + "endif" + TC)
    out.append("</tbody></table></div>")
    return "".join(out)


def _gen_code(layout):
    parts = ['<div class="ps-root" style="position:relative;width:100%">']
    for band in layout.get("bands", []):
        bt = band.get("type")
        if bt in ("page_header", "page_footer"):
            continue
        h = band.get("height", 10)
        parts.append('<div style="position:relative;height:{0}mm">'.format(h))
        has_table = any(e.get("type") == "table" for e in band.get("elements", []))
        if bt == "detail" and band.get("dataSource") and not has_table:
            parts.append(TO + 'for row in doc.get("{0}") or []'.format(band["dataSource"]) + TC)
            for e in band.get("elements", []):
                parts.append(_gen_el(e, band, True))
            parts.append(TO + "endfor" + TC)
        else:
            for e in band.get("elements", []):
                parts.append(_gen_el(e, band, False))
        parts.append("</div>")
    parts.append("</div>")
    page = layout.get("page", {}) or {}
    orient = page.get("orientation", "portrait")
    size = "297mm 210mm" if orient == "landscape" else "210mm 297mm"
    return "<style>@page{{size:{0};margin:0}}</style>\n".format(size) + "\n".join(parts)


@frappe.whitelist()
def export_code(layout_json=None, name=None):
    if not layout_json and name:
        layout_json = frappe.db.get_value("Print Studio Layout", name, "config_json")
    try:
        return _gen_code(json.loads(layout_json))
    except Exception:
        return "<!-- Print Studio code export failed -->\n" + frappe.get_traceback()


@frappe.whitelist()
def create_code_format(title, ref_doctype, layout_json):
    """Bake a standalone Jinja Print Format (independent of the layout record)."""
    html = _gen_code(json.loads(layout_json))
    name = "PSC \u00b7 {0}".format(title)
    if frappe.db.exists("Print Format", name):
        pf = frappe.get_doc("Print Format", name)
    else:
        pf = frappe.new_doc("Print Format")
        pf.name = name
    pf.doc_type = ref_doctype
    pf.print_format_type = "Jinja"
    pf.custom_format = 1
    pf.standard = "No"
    pf.html = html
    pf.save(ignore_permissions=True)
    frappe.db.commit()
    return {"name": name}

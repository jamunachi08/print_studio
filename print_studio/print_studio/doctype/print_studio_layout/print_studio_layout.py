# Copyright (c) 2026, Neotec Integrated Solution
import frappe
from frappe.model.document import Document
from frappe.utils import slug


class PrintStudioLayout(Document):
    def before_insert(self):
        if not self.slug:
            self.slug = slug(self.title)

    def validate(self):
        if not self.slug:
            self.slug = slug(self.title)

    def on_update(self):
        # Keep a matching Print Format in sync so the design is printable
        # straight from the standard ERPNext print dropdown.
        sync_print_format(self)

    def on_trash(self):
        pf = print_format_name(self)
        if frappe.db.exists("Print Format", pf):
            frappe.delete_doc("Print Format", pf, ignore_permissions=True, force=True)


def print_format_name(layout):
    return "PS · {0}".format(layout.title)


def sync_print_format(layout):
    """Create or update the Custom-HTML Print Format that renders this layout."""
    name = print_format_name(layout)
    html = '{{{{ render_layout(doc, "{0}") }}}}'.format(layout.name)
    try:
        if frappe.db.exists("Print Format", name):
            pf = frappe.get_doc("Print Format", name)
        else:
            pf = frappe.new_doc("Print Format")
            pf.name = name
        pf.doc_type = layout.ref_doctype
        pf.print_format_type = "Jinja"
        pf.custom_format = 1
        pf.standard = "No"
        pf.disabled = 0
        pf.html = html
        if getattr(layout, "is_default", 0):
            pf.default_print_language = pf.default_print_language or ""
        pf.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="Print Studio sync", message=frappe.get_traceback())

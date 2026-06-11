# Free the /app/print-studio route: the designer Page must own it, not a Workspace.
import frappe


def execute():
    for ws in ("Print Studio",):
        if frappe.db.exists("Workspace", ws):
            try:
                frappe.delete_doc("Workspace", ws, ignore_permissions=True, force=True)
            except Exception:
                try:
                    frappe.db.delete("Workspace", {"name": ws})
                except Exception:
                    pass
    frappe.db.commit()

app_name = "print_studio"
app_title = "Print Studio"
app_publisher = "Neotec Integrated Solution"
app_description = "Easy drag-and-drop print format designer for Frappe / ERPNext"
app_email = "support@neotec.ai"
app_license = "MIT"

# Expose the renderer + QR/barcode helpers to every Print Format's Jinja context.
jinja = {
    "methods": [
        "print_studio.api.render_layout",
        "print_studio.api.get_qr",
        "print_studio.api.get_barcode",
        "print_studio.api.ps_address",
        "print_studio.api.ps_field",
        "print_studio.api.ps_formula",
    ]
}

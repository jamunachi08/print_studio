// Makes the visual designer the obvious way to edit a layout.
frappe.ui.form.on("Print Studio Layout", {
	refresh(frm) {
		// Raw JSON is machine-generated — don't invite hand-editing.
		frm.set_df_property("config_json", "read_only", 1);

		if (!frm.is_new()) {
			frm.page.set_primary_action(__("🎨 Open in Print Studio"), () => {
				frappe.set_route("print-studio", { layout: frm.doc.name });
			});

			if (frm.doc.title) {
				frm.dashboard.add_comment(
					__("Designs are edited visually. This layout prints via <b>PS · {0}</b> in the document print menu.", [
						frm.doc.title,
					]),
					"blue",
					true
				);
			}
		}
	},
});

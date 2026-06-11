frappe.pages['print-studio'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Print Studio',
		single_column: true,
	});
	page.main.css({ padding: 0, margin: 0 });

	const BUILD = '0.5.6';
	const srcFor = (name) =>
		'/assets/print_studio/designer.html?v=' + BUILD + '&_=' + Date.now() +
		(name ? '&layout=' + encodeURIComponent(name) : '');
	const layoutFromRoute = () => (frappe.route_options && frappe.route_options.layout) || '';

	const iframe = document.createElement('iframe');
	iframe.id = 'ps-designer-frame';
	iframe.src = srcFor(layoutFromRoute());
	iframe.style.cssText =
		'width:100%;height:calc(100vh - 110px);min-height:560px;border:0;display:block;background:#eef0f3';
	page.main.append(iframe);
	frappe.route_options = null;

	const handlers = {
		listDoctypes: (a) =>
			frappe.call('print_studio.api.list_doctypes', { search: a.search }).then((r) => r.message || []),
		getFields: (a) =>
			frappe.call('print_studio.api.get_print_fields', { doctype: a.doctype }).then((r) => r.message || {}),
		getPreview: (a) =>
			frappe.call('print_studio.api.get_preview_doc', { doctype: a.doctype }).then((r) => r.message || {}),
		listLayouts: (a) =>
			frappe.call('print_studio.api.list_layouts', { ref_doctype: a.ref_doctype }).then((r) => r.message || []),
		loadLayout: (a) =>
			frappe.call('print_studio.api.load_layout', { name: a.name }).then((r) => r.message),
		saveLayout: (a) =>
			frappe.call('print_studio.api.save_layout', {
				title: a.title, ref_doctype: a.ref_doctype, config_json: a.config_json, name: a.name,
			}).then((r) => r.message),
		serverPreview: (a) =>
			frappe.call('print_studio.api.render_preview', { doctype: a.doctype, layout_json: a.layout_json }).then((r) => r.message),
		importFile: (a) =>
			frappe.call('print_studio.api.import_format', { filename: a.filename, content_b64: a.content_b64, doctype: a.doctype, mode: a.mode || 'text' }).then((r) => r.message),
		exportCode: (a) =>
			frappe.call('print_studio.api.export_code', { layout_json: a.layout_json }).then((r) => r.message),
		makeCodeFormat: (a) =>
			frappe.call('print_studio.api.create_code_format', { title: a.title, ref_doctype: a.ref_doctype, layout_json: a.layout_json }).then((r) => r.message),
		pickImage: () =>
			new Promise((resolve) => {
				new frappe.ui.FileUploader({
					allow_multiple: false,
					restrictions: { allowed_file_types: ['image/*'] },
					on_success(file_doc) {
						resolve(file_doc && file_doc.file_url ? file_doc.file_url : null);
					},
				});
			}),
		notify: (a) => { frappe.show_alert({ message: a.msg, indicator: 'green' }); return true; },
		print: (a) => {
			frappe.show_alert({
				message: __('Open any {0} \u2192 Print \u2192 pick <b>PS \u00b7 {1}</b>', [a.doctype, a.title]),
				indicator: 'blue',
			}, 7);
			return true;
		},
	};

	window.addEventListener('message', async (e) => {
		const m = e.data;
		if (!m || m.ns !== 'ps' || m.type === 'reply') return;
		if (e.source !== iframe.contentWindow) return;
		let data = null;
		try {
			if (handlers[m.type]) data = await handlers[m.type](m.args || {});
		} catch (err) {
			console.error('Print Studio bridge error', err);
		}
		iframe.contentWindow.postMessage({ ns: 'ps', type: 'reply', reqId: m.reqId, data }, '*');
	});
};

frappe.pages['print-studio'].on_page_show = function () {
	const name = (frappe.route_options && frappe.route_options.layout) || '';
	if (!name) return;
	const iframe = document.getElementById('ps-designer-frame');
	if (iframe && iframe.src.indexOf('layout=' + encodeURIComponent(name)) < 0) {
		iframe.src = '/assets/print_studio/designer.html?v=0.5.6&_=' + Date.now() + '&layout=' + encodeURIComponent(name);
	}
	frappe.route_options = null;
};

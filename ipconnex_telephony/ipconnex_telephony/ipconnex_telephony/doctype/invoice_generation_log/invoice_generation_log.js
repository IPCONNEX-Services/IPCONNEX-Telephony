frappe.ui.form.on("Invoice Generation Log", {
    refresh(frm) {
        if (frm.doc.status === "Failed") {
            frm.add_custom_button(__("Retry"), () => {
                frm.call("retry").then(() => frm.reload_doc());
            }, __("Actions"));
        }
    },
});

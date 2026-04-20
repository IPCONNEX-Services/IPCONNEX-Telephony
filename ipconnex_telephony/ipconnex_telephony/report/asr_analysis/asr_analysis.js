frappe.query_reports["ASR Analysis"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "Link",
            options: "Supplier",
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer",
        },
        {
            fieldname: "destination_country",
            label: __("Destination"),
            fieldtype: "Data",
        },
        {
            fieldname: "asr_status",
            label: __("ASR Status"),
            fieldtype: "Select",
            options: "\nOK\nWarning\nCritical",
        },
    ],
};

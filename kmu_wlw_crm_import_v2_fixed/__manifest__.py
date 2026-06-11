{
    "name": "KMU WLW CRM Import",
    "summary": "Importiert WLW-Besucher als CRM-Leads mit Dublettenprüfung",
    "version": "19.0.1.0.0",
    "category": "Sales/CRM",
    "author": "KMU DataSuite",
    "license": "LGPL-3",
    "depends": ["crm", "utm"],
    "data": [
        "views/crm_lead_views.xml",
        "wizard/wlw_crm_import_wizard_views.xml"
    ],
    "installable": True,
    "application": False
}

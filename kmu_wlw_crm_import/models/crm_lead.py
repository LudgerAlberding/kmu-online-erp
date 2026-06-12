from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    x_wlw_import_key = fields.Char(string="WLW Import Key", index=True, copy=False)
    x_wlw_first_visit = fields.Date(string="WLW erster Besuch", copy=False)
    x_wlw_last_visit = fields.Date(string="WLW letzter Besuch", copy=False)
    x_wlw_visit_count = fields.Integer(string="WLW Besuche", default=0, copy=False)
    x_wlw_products = fields.Text(string="WLW Produkte", copy=False)
    x_wlw_keywords = fields.Text(string="WLW Suchbegriffe", copy=False)
    x_wlw_activity_level = fields.Char(string="WLW Aktivitätslevel", copy=False)
    x_wlw_linkedin = fields.Char(string="WLW LinkedIn", copy=False)
    x_wlw_industry = fields.Char(string="WLW Haupttätigkeit / Branche", copy=False)
    x_wlw_employee_count = fields.Char(string="WLW Mitarbeiterzahl", copy=False)
    x_wlw_visit_history = fields.Text(string="WLW Besuchshistorie", copy=False)

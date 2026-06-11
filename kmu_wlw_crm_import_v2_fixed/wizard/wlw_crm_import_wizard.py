import base64
import csv
import io
import re
from datetime import datetime
from urllib.parse import urlparse

from odoo import _, fields, models
from odoo.exceptions import UserError


class WlwCrmImportWizard(models.TransientModel):
    _name = "kmu.wlw.crm.import.wizard"
    _description = "WLW Besucher in CRM Leads importieren"

    file = fields.Binary(string="WLW CSV/TSV Datei", required=True)
    filename = fields.Char(string="Dateiname")
    dry_run = fields.Boolean(string="Nur prüfen, nicht importieren", default=True)
    create_leads = fields.Boolean(string="Neue Leads anlegen", default=True)
    update_existing = fields.Boolean(string="Bestehende Leads aktualisieren", default=True)
    assign_to_me = fields.Boolean(string="Mir als Vertriebsmitarbeiter zuweisen", default=True)
    result_text = fields.Text(string="Ergebnis", readonly=True)

    def action_import(self):
        self.ensure_one()
        rows = self._read_rows()
        created = updated = skipped = 0
        notes = []
        source = self._get_or_create("utm.source", "WLW")
        medium = self._get_or_create("utm.medium", "WLW-Webseite")
        campaign = self._get_or_create("utm.campaign", str(datetime.today().year))
        tag_wlw = self._get_or_create_tag("WLW")

        for line_no, row in enumerate(rows, start=2):
            try:
                v = self._values(row)
                if not v["company"]:
                    skipped += 1
                    notes.append("Zeile %s: kein Firmenname" % line_no)
                    continue
                lead = self._find_lead(v)
                signature = self._signature(v)
                if lead:
                    if not self.update_existing:
                        skipped += 1
                        continue
                    if not self.dry_run:
                        vals = self._update_vals(lead, v, signature)
                        if vals:
                            lead.write(vals)
                        if tag_wlw and tag_wlw not in lead.tag_ids:
                            lead.write({"tag_ids": [(4, tag_wlw.id)]})
                    updated += 1
                else:
                    if not self.create_leads:
                        skipped += 1
                        continue
                    if not self.dry_run:
                        self.env["crm.lead"].create(self._create_vals(v, source, medium, campaign, tag_wlw, signature))
                    created += 1
            except Exception as exc:
                skipped += 1
                notes.append("Zeile %s: %s" % (line_no, exc))

        self.result_text = "WLW Import abgeschlossen.\nNeue Leads: %s\nAktualisierte Leads: %s\nÜbersprungen/Fehler: %s" % (created, updated, skipped)
        if notes:
            self.result_text += "\n\nHinweise:\n" + "\n".join(notes[:40])
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "res_id": self.id, "target": "new"}

    def _read_rows(self):
        raw = base64.b64decode(self.file or b"")
        text = None
        for enc in ("utf-8-sig", "utf-16", "cp1252", "latin1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                pass
        if text is None:
            raise UserError(_("Datei konnte nicht gelesen werden."))
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";\t,")
        except Exception:
            dialect = csv.excel_tab if "\t" in sample else csv.excel
        return [{self._clean(k): self._clean(v) for k, v in row.items()} for row in csv.DictReader(io.StringIO(text), dialect=dialect)]

    def _clean(self, value):
        if value is None:
            return ""
        value = str(value).replace("\ufeff", "").replace("\r", " ").replace("\n", " ")
        value = value.strip().strip('"').strip()
        return re.sub(r"\s+", " ", value)

    def _get(self, row, *keys):
        for key in keys:
            if key in row and row[key]:
                return row[key]
        return ""

    def _values(self, row):
        website = self._get(row, "Webseite", "Website")
        domain = self._domain(website)
        company = self._get(row, "Name", "Firmenname")
        zip_code = re.sub(r"[^0-9]", "", self._get(row, "Postleitzahl", "PLZ"))
        import_key = domain or self._company_key(company, zip_code)
        return {
            "company": company,
            "phone": self._get(row, "Telefonnummer", "Telefon"),
            "email": self._get(row, "E-Mail-Adresse", "E-Mail", "Email"),
            "street": self._get(row, "Straße, Hausnummer", "Strasse", "Straße"),
            "zip": zip_code,
            "city": self._get(row, "Stadt", "Ort"),
            "country": self._get(row, "Land"),
            "website": website,
            "domain": domain,
            "industry": self._get(row, "Haupttätigkeit"),
            "employee_count": self._get(row, "Mitarbeiterzahl"),
            "linkedin": self._get(row, "LinkedIn"),
            "profile_visit": self._get(row, "Profilbesuch"),
            "product_visit": self._get(row, "Produktbesuch"),
            "seen_in_search": self._get(row, "In der Suche gesehen"),
            "products": self._get(row, "Besuchte oder angesehene Produkte", "Produkt"),
            "keywords": self._get(row, "Besucher interessierten sich für", "Suchbegriff"),
            "activity": self._get(row, "Aktivitätsniveau", "Aktivität"),
            "date": self._date(self._get(row, "Letzter Besuch", "Datum")),
            "import_key": import_key,
        }

    def _create_vals(self, v, source, medium, campaign, tag, signature):
        vals = {
            "type": "lead",
            "name": v["keywords"] or v["products"] or v["company"],
            "partner_name": v["company"],
            "email_from": v["email"],
            "phone": v["phone"],
            "street": v["street"],
            "zip": v["zip"],
            "city": v["city"],
            "website": v["website"],
            "source_id": source.id,
            "medium_id": medium.id,
            "campaign_id": campaign.id,
            "description": self._description(v),
            "x_wlw_import_key": v["import_key"],
            "x_wlw_first_visit": v["date"],
            "x_wlw_last_visit": v["date"],
            "x_wlw_visit_count": 1 if signature else 0,
            "x_wlw_products": v["products"],
            "x_wlw_keywords": v["keywords"],
            "x_wlw_activity_level": v["activity"],
            "x_wlw_linkedin": v["linkedin"],
            "x_wlw_industry": v["industry"],
            "x_wlw_employee_count": v["employee_count"],
            "x_wlw_visit_history": self._history(v, signature),
        }
        country = self._country(v["country"])
        if country:
            vals["country_id"] = country.id
        if self.assign_to_me:
            vals["user_id"] = self.env.user.id
        if tag:
            vals["tag_ids"] = [(4, tag.id)]
        vals.update(self._priority(v["activity"]))
        return vals

    def _update_vals(self, lead, v, signature):
        history = lead.x_wlw_visit_history or ""
        new_visit = bool(signature and signature not in history)
        vals = {}
        for field, value in {"partner_name": v["company"], "email_from": v["email"], "phone": v["phone"], "street": v["street"], "zip": v["zip"], "city": v["city"], "website": v["website"], "x_wlw_import_key": v["import_key"], "x_wlw_linkedin": v["linkedin"], "x_wlw_industry": v["industry"], "x_wlw_employee_count": v["employee_count"]}.items():
            if value and not lead[field]:
                vals[field] = value
        country = self._country(v["country"])
        if country and not lead.country_id:
            vals["country_id"] = country.id
        if v["date"]:
            if not lead.x_wlw_first_visit or v["date"] < lead.x_wlw_first_visit:
                vals["x_wlw_first_visit"] = v["date"]
            if not lead.x_wlw_last_visit or v["date"] > lead.x_wlw_last_visit:
                vals["x_wlw_last_visit"] = v["date"]
        vals["x_wlw_products"] = self._append_unique(lead.x_wlw_products, v["products"])
        vals["x_wlw_keywords"] = self._append_unique(lead.x_wlw_keywords, v["keywords"])
        if v["activity"]:
            vals["x_wlw_activity_level"] = v["activity"]
            vals.update(self._priority(v["activity"]))
        if new_visit:
            vals["x_wlw_visit_count"] = (lead.x_wlw_visit_count or 0) + 1
            vals["x_wlw_visit_history"] = (history + "\n" + self._history(v, signature)).strip()
        return vals

    def _find_lead(self, v):
        Lead = self.env["crm.lead"]
        if v["import_key"]:
            lead = Lead.search([("x_wlw_import_key", "=", v["import_key"])], limit=1)
            if lead:
                return lead
        if v["domain"]:
            lead = Lead.search(["|", ("x_wlw_import_key", "=", v["domain"]), ("website", "ilike", v["domain"])], limit=1)
            if lead:
                return lead
        if v["email"]:
            lead = Lead.search([("email_from", "=", v["email"])], limit=1)
            if lead:
                return lead
        if v["company"] and v["zip"]:
            return Lead.search([("partner_name", "ilike", v["company"]), ("zip", "=", v["zip"])], limit=1)
        return Lead.browse()

    def _description(self, v):
        lines = ["WLW Besucher"]
        if v["industry"]: lines.append("Branche: %s" % v["industry"])
        if v["employee_count"]: lines.append("Mitarbeiterzahl: %s" % v["employee_count"])
        if v["linkedin"]: lines.append("LinkedIn: %s" % v["linkedin"])
        if v["products"]: lines.append("\nBesuchte Produkte:\n- %s" % v["products"].replace(" | ", "\n- "))
        if v["keywords"]: lines.append("\nSuchbegriffe / Interesse:\n- %s" % v["keywords"].replace(" | ", "\n- "))
        return "\n".join(lines)

    def _signature(self, v):
        date = v["date"].strftime("%Y-%m-%d") if v["date"] else ""
        return "%s|%s|%s" % (date, v["keywords"].lower(), v["products"].lower())

    def _history(self, v, signature):
        if not signature:
            return ""
        date = v["date"].strftime("%d.%m.%Y") if v["date"] else ""
        return "%s | %s | Suchbegriff: %s | Produkt: %s | Aktivität: %s" % (signature, date, v["keywords"], v["products"], v["activity"])

    def _domain(self, url):
        url = self._clean(url)
        if not url:
            return ""
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = (parsed.netloc or parsed.path).lower().strip()
        return host[4:] if host.startswith("www.") else host.split("/")[0]

    def _company_key(self, company, zip_code):
        s = (company or "").upper().replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "SS")
        for legal in ["GMBH & CO KG", "GMBH", "KG", "AG", "E.K.", "EK"]:
            s = s.replace(legal, "")
        return "%s|%s" % (re.sub(r"[^A-Z0-9]", "", s), zip_code or "")

    def _date(self, value):
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except Exception:
                pass
        return False

    def _append_unique(self, old, new):
        parts = [p.strip() for p in re.split(r"\n|\|", old or "") if p.strip()]
        seen = {p.lower() for p in parts}
        for p in [p.strip() for p in re.split(r"\|", new or "") if p.strip()]:
            if p.lower() not in seen:
                parts.append(p); seen.add(p.lower())
        return "\n".join(parts)

    def _country(self, name):
        name = self._clean(name)
        if not name: return False
        c = self.env["res.country"].search([("name", "ilike", name)], limit=1)
        if c: return c
        code = {"deutschland":"DE", "germany":"DE", "österreich":"AT", "austria":"AT", "schweiz":"CH", "switzerland":"CH"}.get(name.lower())
        return self.env["res.country"].search([("code", "=", code)], limit=1) if code else False

    def _get_or_create(self, model, name):
        rec = self.env[model].search([("name", "=", name)], limit=1)
        return rec or self.env[model].create({"name": name})

    def _get_or_create_tag(self, name):
        rec = self.env["crm.tag"].search([("name", "=", name)], limit=1)
        return rec or self.env["crm.tag"].create({"name": name})

    def _priority(self, activity):
        a = (activity or "").lower()
        if "hoch" in a: return {"priority": "3"}
        if "mittel" in a: return {"priority": "2"}
        if "niedrig" in a: return {"priority": "1"}
        return {}

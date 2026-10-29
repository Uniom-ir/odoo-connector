# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Message templates rendered with the standard mail engine (``${object...}``
placeholders, same syntax as mail/sms templates)."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class UniomTemplate(models.Model):
    _name = "uniom.template"
    _inherit = "mail.render.mixin"
    _description = "Uniom Message Template"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        "ir.model",
        string="Applies to",
        required=True,
        domain=[("transient", "=", False)],
        ondelete="cascade",
    )
    model = fields.Char(related="model_id.model", store=True)
    body = fields.Text(
        required=True,
        translate=False,
        help="Message text with placeholders, e.g.:\n"
        "Hello ${object.partner_id.name}, your order ${object.name} is confirmed.\n"
        "The same syntax as Odoo mail templates is used.",
    )
    lang_id = fields.Many2one(
        "res.lang",
        string="Language",
        help="Optional: this template is picked when the customer speaks this "
        "language. Leave empty for the fallback template.",
    )
    company_id = fields.Many2one("res.company", string="Company")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render_for(self, records):
        """Render the template body for *records* and return
        ``{record_id: text}``."""
        self.ensure_one()
        if records._name != self.model:
            raise UserError(
                _(
                    "Template '%(template)s' applies to %(model)s but got a %(other)s record.",
                    template=self.name,
                    model=self.model,
                    other=records._name,
                )
            )
        rendered = self._render_template(
            self.body,
            self.model,
            records.ids,
            engine="jinja",
        )
        return rendered

    def action_preview(self):
        self.ensure_one()
        records = self.env[self.model].search([], limit=1)
        if not records:
            raise UserError(_("Create at least one record of %s first.", self.model_id.name))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Uniom template preview"),
                "message": self._render_for(records)[records.id][:350],
                "sticky": True,
            },
        }

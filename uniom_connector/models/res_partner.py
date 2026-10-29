# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from odoo import fields, models

from .uniom_tools import canonicalize_chat_id


class ResPartner(models.Model):
    _inherit = "res.partner"

    uniom_chat_id = fields.Char(
        string="Uniom Chat ID",
        help="Messenger destination for this contact: phone (+989123456789), "
        "@username or numeric chat id. Leave empty to use the mobile/phone "
        "number.",
        copy=False,
    )
    uniom_opt_out = fields.Boolean(
        string="No Uniom Messages",
        help="Exclude this contact from automated Uniom notifications.",
        copy=False,
    )
    uniom_message_ids = fields.One2many("uniom.message", "partner_id", string="Uniom Messages")
    uniom_message_count = fields.Integer(compute="_compute_uniom_message_count")
    uniom_chat_ids = fields.One2many("uniom.chat", "partner_id", string="Uniom Conversations")
    uniom_chat_count = fields.Integer(compute="_compute_uniom_chat_count")

    def _compute_uniom_message_count(self):
        groups = self.env["uniom.message"]._read_group(
            [("partner_id", "in", self.ids)], ["partner_id"], ["__count"]
        )
        counts = {partner.id: count for partner, count in groups}
        for partner in self:
            partner.uniom_message_count = counts.get(partner.id, 0)

    def _compute_uniom_chat_count(self):
        groups = self.env["uniom.chat"]._read_group(
            [("partner_id", "in", self.ids)], ["partner_id"], ["__count"]
        )
        counts = {partner.id: count for partner, count in groups}
        for partner in self:
            partner.uniom_chat_count = counts.get(partner.id, 0)

    def _uniom_default_chat_id(self):
        """Best messenger destination for this partner (explicit chat id,
        else canonicalized mobile, else phone)."""
        self.ensure_one()
        return (
            self.uniom_chat_id
            or canonicalize_chat_id(self.mobile)
            or canonicalize_chat_id(self.phone)
        )

    def action_uniom_send(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Send via Uniom",
            "res_model": "uniom.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_active_model": self._name,
                "default_active_id": self.id,
            },
        }

    def action_view_uniom_messages(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Uniom Conversations",
            "res_model": "uniom.chat",
            "view_mode": "kanban,form",
            "domain": [("partner_id", "child_of", self.id)],
        }

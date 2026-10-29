# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""One-click "Send via Uniom" composer, reachable from partners, sale
orders, invoices and deliveries."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.uniom_tools import canonicalize_chat_id

# model -> default report worth attaching
REPORT_BY_MODEL = {
    "sale.order": "sale.action_report_saleorder",
    "account.move": "account.account_invoices",
    "account.payment": "account.action_report_payment_receipt",
    "stock.picking": "stock.action_report_delivery",
}


class UniomSendWizard(models.TransientModel):
    _name = "uniom.send.wizard"
    _description = "Send via Uniom"

    active_model = fields.Char(default=lambda self: self.env.context.get("default_active_model"))
    active_id = fields.Integer(default=lambda self: self.env.context.get("default_active_id"))
    connection_id = fields.Many2one(
        "uniom.connection",
        required=True,
        default=lambda self: self.env["uniom.connection"]._get_default_connection(),
        domain="[('active', '=', True)]",
    )
    body = fields.Text(required=True)
    attach_document = fields.Boolean(
        string="Attach PDF",
        help="Send the document's standard PDF report with the message.",
        compute="_compute_attach_document",
        store=True,
        readonly=False,
    )
    recipient_ids = fields.One2many("uniom.send.recipient", "wizard_id", string="Recipients")

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    @api.depends("active_model")
    def _compute_attach_document(self):
        for wizard in self:
            wizard.attach_document = wizard.active_model in REPORT_BY_MODEL

    @api.onchange("active_model", "active_id")
    def _onchange_record(self):
        if not (self.active_model and self.active_id):
            return
        record = self.env[self.active_model].browse(self.active_id).exists()
        if not record:
            return
        if not self.body:
            template = self.env["uniom.template"].search(
                [("model", "=", self.active_model), ("active", "=", True)], limit=1
            )
            self.body = (
                template._render_for(record).get(record.id)
                if template
                else _("Hello, here is an update about %s.", record.display_name)
            )
        partners = record.partner_id if "partner_id" in record._fields else self.env["res.partner"]
        if partners and not self.recipient_ids:
            self.recipient_ids = [
                (0, 0, {"partner_id": partner.id, "chat_id": partner._uniom_default_chat_id() or ""})
                for partner in partners
            ]

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------
    def action_send(self):
        self.ensure_one()
        messages = self.env["uniom.message"]
        record = (
            self.env[self.active_model].browse(self.active_id).exists()
            if self.active_model and self.active_id
            else self.env[self.active_model]
        )
        for recipient in self.recipient_ids:
            chat_id = canonicalize_chat_id(recipient.chat_id)
            if not chat_id:
                raise UserError(
                    _("Invalid destination '%s'. Use +989123456789, @channel or a numeric id."),
                    recipient.chat_id,
                )
            messages |= self.env["uniom.message"].create(
                {
                    "connection_id": self.connection_id.id,
                    "direction": "out",
                    "state": "outgoing",
                    "chat_id": chat_id,
                    "partner_id": recipient.partner_id.id,
                    "body": self.body,
                    "report_ref": self.attach_document and REPORT_BY_MODEL.get(self.active_model) or False,
                    "record_res_model": self.active_model or False,
                    "record_res_id": self.active_id or False,
                    "record_name": record.display_name if record else False,
                }
            )
        messages._send_message()
        sent = len(messages.filtered(lambda m: m.state == "sent"))
        failed = len(messages) - sent
        notification = _("%s message(s) sent.") % sent
        if failed:
            notification += _(" %s failed and were queued or marked failed (see the log).") % failed
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Uniom"), "message": notification, "type": "info"},
        }


class UniomSendRecipient(models.TransientModel):
    _name = "uniom.send.recipient"
    _description = "Uniom Send Wizard Recipient"

    wizard_id = fields.Many2one("uniom.send.wizard", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner")
    chat_id = fields.Char(
        required=True,
        help="Phone number (+989123456789), @channel or numeric chat id.",
    )

    @api.onchange("partner_id")
    def _onchange_partner(self):
        if self.partner_id:
            self.chat_id = self.partner_id._uniom_default_chat_id() or ""

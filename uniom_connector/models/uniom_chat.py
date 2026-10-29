# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Conversations: one session per (connection, chat id), grouping every
incoming and outgoing message into a messenger-like thread with a quick
reply box — the WhatsApp-connector style UI, on top of the same queue."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .uniom_tools import canonicalize_chat_id


class UniomChat(models.Model):
    _name = "uniom.chat"
    _description = "Uniom Conversation"
    _order = "last_message_date desc, id desc"

    connection_id = fields.Many2one(
        "uniom.connection", required=True, index=True, ondelete="restrict"
    )
    chat_id = fields.Char(required=True, index=True)
    partner_id = fields.Many2one("res.partner", index=True, ondelete="set null")
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, index=True
    )
    display_name = fields.Char(compute="_compute_display_name")
    message_ids = fields.One2many("uniom.message", "chat_session_id", string="Thread")
    message_count = fields.Integer(compute="_compute_message_count")
    last_message_date = fields.Datetime(readonly=True)
    last_message_preview = fields.Char(readonly=True)
    reply_body = fields.Text(
        string="Draft reply",
        help="Write a reply here and press Send Reply; it goes out through "
        "the connection of this conversation.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("partner_id.name", "chat_id")
    def _compute_display_name(self):
        for chat in self:
            chat.display_name = chat.partner_id.name or chat.chat_id

    @api.depends("message_ids")
    def _compute_message_count(self):
        for chat in self:
            chat.message_count = len(chat.message_ids)

    # ------------------------------------------------------------------
    # Session maintenance (called from uniom.message create)
    # ------------------------------------------------------------------
    @api.model
    def _get_or_create_for(self, message):
        chat = self.search(
            [
                ("connection_id", "=", message.connection_id.id),
                ("chat_id", "=", message.chat_id),
            ],
            limit=1,
        )
        if not chat:
            chat = self.create(
                {
                    "connection_id": message.connection_id.id,
                    "chat_id": message.chat_id,
                    "partner_id": message.partner_id.id,
                    "company_id": message.company_id.id,
                }
            )
        elif message.partner_id and not chat.partner_id:
            chat.partner_id = message.partner_id
        return chat

    def _touch_from(self, message):
        self.ensure_one()
        self.write(
            {
                "last_message_date": message.date_sent or fields.Datetime.now(),
                "last_message_preview": (message.body or "")[:64],
            }
        )

    # ------------------------------------------------------------------
    # Reply from the thread view
    # ------------------------------------------------------------------
    def action_send_reply(self):
        for chat in self:
            body = (chat.reply_body or "").strip()
            if not body:
                raise UserError(_("Write a reply first."))
            chat_id = canonicalize_chat_id(chat.chat_id)
            if not chat_id:
                raise UserError(
                    _("This conversation has an invalid destination: %s"), chat.chat_id
                )
            message = self.env["uniom.message"].create(
                {
                    "connection_id": chat.connection_id.id,
                    "chat_session_id": chat.id,
                    "direction": "out",
                    "state": "outgoing",
                    "chat_id": chat_id,
                    "partner_id": chat.partner_id.id,
                    "body": body,
                    "record_res_model": "res.partner",
                    "record_res_id": chat.partner_id.id,
                    "record_name": chat.partner_id.name,
                }
            )
            message._send_message()
        self.write({"reply_body": False})
        return True

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_partner(self):
        self.ensure_one()
        if not self.partner_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "res_id": self.partner_id.id,
            "view_mode": "form",
        }

# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Outbound message queue + full in/out message log.

Every message the module sends (or receives) is a ``uniom.message`` row:
it is attempted immediately, and any failure the Uniom API classifies as
transient (429 flood, 5xx) is re-queued with backoff by the cron. HTTP 504
means "dispatched, outcome unknown" and is deliberately *not* retried, per
the Uniom Bot API documentation.
"""

import logging

from odoo import _, api, fields, models

from .uniom_tools import UniomAPIError

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
# minutes: 5, 20, 80, 320 ... capped
BACKOFF_MINUTES = [5, 15, 60, 240, 720]


class UniomMessage(models.Model):
    _name = "uniom.message"
    _description = "Uniom Message"
    _order = "id desc"
    _rec_name = "display_label"

    display_label = fields.Char(compute="_compute_display_label")
    connection_id = fields.Many2one(
        "uniom.connection", required=True, index=True, ondelete="restrict"
    )
    direction = fields.Selection(
        [("out", "Outgoing"), ("in", "Incoming")], default="out", required=True, index=True
    )
    state = fields.Selection(
        [
            ("outgoing", "Queued"),
            ("sent", "Sent"),
            ("error", "Failed"),
            ("canceled", "Canceled"),
        ],
        default="outgoing",
        required=True,
        index=True,
        copy=False,
    )
    chat_id = fields.Char(
        required=True, index=True, help="Destination: phone (+98912...), @channel or numeric id."
    )
    partner_id = fields.Many2one("res.partner", index=True, ondelete="set null")
    body = fields.Text()
    record_res_model = fields.Char(index=True)
    record_res_id = fields.Integer(index=True)
    record_name = fields.Char()
    record_ref = fields.Reference(
        compute="_compute_record_ref",
        selection=lambda self: self._selection_record_ref(),
    )
    rule_id = fields.Many2one("uniom.rule", ondelete="set null", index=True)
    template_id = fields.Many2one("uniom.template", ondelete="set null")
    uniom_message_id = fields.Integer(
        copy=False, help="Message id assigned by the messenger, needed to edit later."
    )
    date_sent = fields.Datetime(copy=False)
    date_edited = fields.Datetime(copy=False)
    edit_count = fields.Integer(default=0, copy=False)
    error_message = fields.Text(copy=False)
    retry_count = fields.Integer(default=0, copy=False)
    next_attempt = fields.Datetime(
        default=fields.Datetime.now,
        help="Earliest moment the queue cron may retry this message.",
    )
    report_ref = fields.Char(
        help="Technical reference of the QWeb report to attach as a document, "
        "e.g. account.account_invoices.",
    )
    attachment_id = fields.Many2one("ir.attachment", ondelete="set null")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.model
    def _selection_record_ref(self):
        models = self.env["ir.model"].sudo().search([])
        return [(model.model, model.name) for model in models]

    @api.depends("record_res_model", "record_res_id")
    def _compute_record_ref(self):
        for message in self:
            if message.record_res_model and message.record_res_id:
                try:
                    message.record_ref = "%s,%s" % (message.record_res_model, message.record_res_id)
                except ValueError:
                    message.record_ref = False
            else:
                message.record_ref = False

    def _compute_display_label(self):
        for message in self:
            label = (message.body or "").strip().replace("\n", " ")[:80]
            message.display_label = label or _("Uniom message to %s", message.chat_id)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _send_message(self):
        """Attempt delivery now; queue for retry on transient failures."""
        for message in self:
            if message.direction != "out" or message.state not in ("outgoing",):
                continue
            connection = message.connection_id.sudo()
            attachment = message._ensure_document()
            try:
                if attachment:
                    result = connection._call(
                        "sendDocument",
                        payload={
                            "chat_id": message.chat_id,
                            "caption": (message.body or "")[:1024] or None,
                        },
                        files={
                            "document": (
                                attachment.name or "document",
                                attachment.raw,
                                attachment.mimetype or "application/octet-stream",
                            )
                        },
                    )
                else:
                    result = connection._call(
                        "sendMessage",
                        payload={"chat_id": message.chat_id, "text": message.body or ""},
                    )
            except UniomAPIError as error:
                message._handle_failure(error)
                continue
            message.write(
                {
                    "state": "sent",
                    "uniom_message_id": (result or {}).get("message_id"),
                    "date_sent": fields.Datetime.now(),
                    "error_message": False,
                    "next_attempt": False,
                }
            )
            message._post_chatter(_("Message sent via Uniom (%s).", connection.name))
        return True

    def _handle_failure(self, error):
        self.ensure_one()
        if error.error_code == 504:
            # "Dispatched, outcome unknown": the gateway explicitly forbids
            # auto-retry. Record the doubt instead of risking a duplicate.
            self.write(
                {
                    "state": "sent",
                    "date_sent": fields.Datetime.now(),
                    "error_message": _(
                        "Delivery outcome unknown (gateway timeout). Not retried "
                        "to avoid duplicates, please verify on the messenger."
                    ),
                }
            )
            return
        if error.transient:
            attempts = self.retry_count + 1
            if attempts > MAX_ATTEMPTS:
                self.write(
                    {
                        "state": "error",
                        "error_message": str(error.args[0]) if error.args else str(error),
                    }
                )
                self._post_chatter(_("Uniom message failed permanently: %s", self.error_message))
                return
            if error.retry_after:
                delay_minutes = max(int(error.retry_after) // 60, 1)
            else:
                delay_minutes = BACKOFF_MINUTES[min(attempts - 1, len(BACKOFF_MINUTES) - 1)]
            self.write(
                {
                    "state": "outgoing",
                    "retry_count": attempts,
                    "next_attempt": fields.Datetime.add(
                        fields.Datetime.now(), minutes=delay_minutes
                    ),
                    "error_message": _("Retry %(n)s/%(max)s scheduled in %(mins)s min: %(err)s",
                                       n=attempts, max=MAX_ATTEMPTS, mins=delay_minutes,
                                       err=str(error.args[0]) if error.args else str(error)),
                }
            )
            return
        # 4xx (except 429): malformed request, unknown chat, auth or billing
        # problem — retrying the identical request cannot succeed.
        self.write(
            {"state": "error", "error_message": str(error.args[0]) if error.args else str(error)}
        )

    def _ensure_document(self):
        """Lazily render the linked report into an attachment at send time,
        so the queued PDF is always the final version of the document."""
        self.ensure_one()
        if self.attachment_id:
            return self.attachment_id
        if not (self.report_ref and self.record_res_model and self.record_res_id):
            return self.env["ir.attachment"]
        report = self.env["ir.actions.report"]._get_report(self.report_ref)
        if report.report_type != "qweb-pdf":
            return self.env["ir.attachment"]
        pdf_content, _doc_type = self.env["ir.actions.report"]._render_qweb_pdf(
            self.report_ref, [self.record_res_id]
        )
        attachment = self.env["ir.attachment"].create(
            {
                "name": "%s.pdf" % (self.record_name or report.name),
                "res_model": self._name,
                "res_id": self.id,
                "raw": pdf_content,
                "mimetype": "application/pdf",
            }
        )
        self.attachment_id = attachment
        return attachment

    def _post_chatter(self, text):
        self.ensure_one()
        if not (self.record_res_model and self.record_res_id and self.body):
            return False
        model = self.env.get(self.record_res_model)
        if model is None or not hasattr(model, "message_post"):
            return False
        record = model.browse(self.record_res_id).exists()
        if not record.exists():
            return False
        record.message_post(body=text)
        return True

    # ------------------------------------------------------------------
    # Editing sent messages (channel price updates, ...)
    # ------------------------------------------------------------------
    def _edit_message(self, new_body):
        """Edit an already-sent message in place; fall back to a fresh send
        when the messenger refuses the edit (too old, deleted, ...)."""
        self.ensure_one()
        if self.state != "sent" or not self.uniom_message_id:
            return self._send_fresh_copy(new_body)
        try:
            self.connection_id.sudo()._call(
                "editMessageText",
                payload={
                    "chat_id": self.chat_id,
                    "message_id": self.uniom_message_id,
                    "text": new_body,
                },
            )
        except UniomAPIError as error:
            if error.transient:
                raise
            return self._send_fresh_copy(new_body)
        self.write(
            {
                "body": new_body,
                "edit_count": self.edit_count + 1,
                "date_edited": fields.Datetime.now(),
            }
        )
        return True

    def _send_fresh_copy(self, new_body):
        copy = self.copy(
            {"body": new_body, "state": "outgoing", "retry_count": 0,
             "edit_count": 0, "uniom_message_id": False, "error_message": False,
             "next_attempt": fields.Datetime.now(), "attachment_id": False}
        )
        copy._send_message()
        return True

    # ------------------------------------------------------------------
    # Queue cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_process_queue(self):
        batch = self.search(
            [
                ("state", "=", "outgoing"),
                ("direction", "=", "out"),
                ("next_attempt", "<=", fields.Datetime.now()),
            ],
            limit=100,
        )
        _logger.info("Uniom queue cron processing %s messages", len(batch))
        batch._send_message()
        return True

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------
    def action_send_now(self):
        self.filtered(lambda m: m.state in ("outgoing", "error")).write(
            {"state": "outgoing", "retry_count": 0, "next_attempt": fields.Datetime.now()}
        )
        self._send_message()
        return True

    def action_cancel(self):
        self.filtered(lambda m: m.state == "outgoing").write({"state": "canceled"})
        return True

    def action_view_record(self):
        self.ensure_one()
        if not self.record_ref:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": self.record_res_model,
            "res_id": self.record_res_id,
            "view_mode": "form",
        }

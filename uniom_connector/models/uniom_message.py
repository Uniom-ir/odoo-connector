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

from .uniom_tools import MAX_RETRY_DELAY_MINUTES, REPORT_BY_MODEL, UniomAPIError

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
    chat_session_id = fields.Many2one(
        "uniom.chat",
        index=True,
        ondelete="set null",
        help="Conversation this message belongs to (kept for history).",
    )
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
        # only the models this module writes about — avoids querying all
        # ir.model records on every fields_get
        return [
            ("res.partner", _("Contact")),
            ("sale.order", _("Sale Order")),
            ("account.move", _("Invoice")),
            ("account.payment", _("Payment")),
            ("stock.picking", _("Transfer")),
            ("product.template", _("Product")),
        ]

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
    # Conversation grouping
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        for message in messages:
            # trust an explicit link (reply box, copies); only derive when
            # absent so a differently-spelled chat id never splits a thread
            chat = message.chat_session_id or self.env["uniom.chat"]._get_or_create_for(message)
            if message.chat_session_id != chat:
                message.chat_session_id = chat.id
            chat._touch_from(message)
        return messages

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _send_message(self):
        """Attempt delivery now; queue for retry on transient failures."""
        for message in self:
            if message.direction != "out" or message.state not in ("outgoing",):
                continue
            try:
                message._send_one()
            except UniomAPIError as error:
                message._handle_failure(error)
            except Exception as error:  # noqa: BLE001 - one bad message must not block the queue
                _logger.exception("Uniom: unexpected failure sending message %s", message.id)
                message.write(
                    {
                        "state": "error",
                        "error_message": _("Unexpected error: %s", error),
                        "next_attempt": False,
                    }
                )
        return True

    def _send_one(self):
        self.ensure_one()
        # fresh attempt: clear stale notes, then let _ensure_document set a
        # new "document skipped" note that must survive a successful send
        self.error_message = False
        connection = self.connection_id.sudo()
        attachment = self._ensure_document()
        if attachment:
            result = connection._call(
                "sendDocument",
                payload={
                    "chat_id": self.chat_id,
                    "caption": (self.body or "")[:1024] or None,
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
                payload={"chat_id": self.chat_id, "text": self.body or ""},
            )
        self.write(
            {
                "state": "sent",
                "uniom_message_id": (result or {}).get("message_id"),
                "date_sent": fields.Datetime.now(),
                # keep a possible "PDF not attached" note from _ensure_document
                "error_message": self.error_message or False,
                "next_attempt": False,
            }
        )
        self._post_chatter(_("Message sent via Uniom (%s).", self.connection_id.name))
        return True

    def _handle_failure(self, error):
        self.ensure_one()
        error_text = str(error.args[0]) if error.args else str(error)
        if error.error_code == 504:
            # "Dispatched, outcome unknown": the gateway explicitly forbids
            # auto-retry. Record the doubt instead of risking a duplicate.
            self.write(
                {
                    "state": "sent",
                    "date_sent": fields.Datetime.now(),
                    "next_attempt": False,
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
                        "next_attempt": False,
                        "error_message": error_text,
                    }
                )
                self._post_chatter(_("Uniom message failed permanently: %s", error_text))
                return
            if error.retry_after:
                delay_minutes = min(max(int(error.retry_after) // 60, 1), MAX_RETRY_DELAY_MINUTES)
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
                                       err=error_text),
                }
            )
            return
        # 4xx (except 429): malformed request, unknown chat, auth or billing
        # problem — retrying the identical request cannot succeed.
        self.write(
            {"state": "error", "next_attempt": False, "error_message": error_text}
        )

    def _ensure_document(self):
        """Lazily render the linked report into an attachment at send time,
        so the queued PDF is always the final version of the document.

        Security: rendering runs under sudo, so the message creator must be
        able to read the target record, and only the record's own standard
        report (allowlisted per model) is ever rendered.
        """
        self.ensure_one()
        if self.attachment_id:
            return self.attachment_id
        if not (self.report_ref and self.record_res_model and self.record_res_id):
            return self.env["ir.attachment"]
        if REPORT_BY_MODEL.get(self.record_res_model) != self.report_ref:
            _logger.warning(
                "Uniom: report %s is not the allowed report for %s, skipped",
                self.report_ref, self.record_res_model,
            )
            self.error_message = _("Report %s is not allowed for this document.", self.report_ref)
            return self.env["ir.attachment"]
        model = self.env.get(self.record_res_model)
        if model is None:
            return self.env["ir.attachment"]
        try:
            model.with_user(self.create_uid).browse(self.record_res_id).check_access("read")
        except Exception as error:  # noqa: BLE001 - AccessError expected
            _logger.warning(
                "Uniom: user %s cannot read %s,%s, document not attached",
                self.create_uid.id, self.record_res_model, self.record_res_id,
            )
            self.error_message = _("Document not attached: %s", error)
            return self.env["ir.attachment"]
        try:
            pdf_content, _doc_type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
                self.report_ref, [self.record_res_id]
            )
        except Exception as error:  # noqa: BLE001 - report problems must not lose the message
            _logger.exception(
                "Uniom: could not render report %s for %s,%s",
                self.report_ref, self.record_res_model, self.record_res_id,
            )
            self.error_message = _("Could not render the PDF report: %s", error)
            return self.env["ir.attachment"]
        attachment = self.env["ir.attachment"].create(
            {
                "name": "%s.pdf" % (self.record_name or _("document")),
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
        duplicate = self.copy(
            {"body": new_body, "state": "outgoing", "retry_count": 0,
             "edit_count": 0, "uniom_message_id": False, "error_message": False,
             "next_attempt": fields.Datetime.now(), "attachment_id": False}
        )
        duplicate._send_message()
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

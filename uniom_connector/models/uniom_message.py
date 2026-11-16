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
    _sql_constraints = [
        (
            "connection_update_uniq",
            "unique(connection_id, uniom_update_id)",
            "This gateway update was already stored for this connection.",
        )
    ]

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
    uniom_message_id = fields.Char(
        copy=False,
        index=True,
        help="Message id assigned by the messenger, needed to edit later. "
        "Stored as text: gateway ids exceed the 32-bit integer range.",
    )
    uniom_update_id = fields.Char(
        copy=False, index=True, help="Gateway update id, used to ignore re-deliveries."
    )
    message_kind = fields.Selection(
        [
            ("text", "Text"),
            ("photo", "Photo"),
            ("document", "Document"),
            ("video", "Video"),
            ("audio", "Audio"),
            ("voice", "Voice message"),
            ("sticker", "Sticker"),
            ("location", "Location"),
            ("contact", "Contact"),
            ("poll", "Poll"),
            ("unknown", "Unsupported"),
        ],
        default="text",
        required=True,
        help="Kind of content carried by this message.",
    )
    is_read = fields.Boolean(
        default=True,
        required=True,
        index=True,
        help="Incoming messages start unread and are marked read when the "
        "conversation is opened or the messenger confirms the read receipt.",
    )
    attachment_ids = fields.One2many(
        "ir.attachment",
        "res_id",
        domain=[("res_model", "=", "uniom.message")],
        string="Attachments",
        copy=False,
    )
    date_sent = fields.Datetime(copy=False)
    date_edited = fields.Datetime(copy=False)
    edit_count = fields.Integer(default=0, copy=False)
    seen_state = fields.Selection(
        [
            ("unknown", "Unknown"),
            ("delivered", "Delivered"),
            ("seen", "Seen"),
            ("read", "Read"),
        ],
        default="unknown",
        copy=False,
        help="Read/delivery state reported by getMessageStates.",
    )
    seen_count = fields.Integer(copy=False, help="Seen count from getMessageStates.")
    views_count = fields.Integer(copy=False, help="View count from getMessageStates.")
    state_updated_at = fields.Datetime(readonly=True, copy=False)
    deleted_on_messenger = fields.Boolean(
        copy=False, help="The message was deleted on the messenger side."
    )
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
        backfill = bool(self.env.context.get("uniom_backfill"))
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if "is_read" not in vals:
                # outgoing messages are ours (already read); incoming webhook
                # messages start unread, except during history backfill where
                # the whole page is historical and must not badge the inbox
                vals["is_read"] = (
                    True if vals.get("direction", "out") != "in" else backfill
                )
            prepared.append(vals)
        messages = super().create(prepared)
        for message in messages:
            # trust an explicit link (reply box, copies); only derive when
            # absent so a differently-spelled chat id never splits a thread
            chat = message.chat_session_id or self.env["uniom.chat"]._get_or_create_for(message)
            if message.chat_session_id != chat:
                message.chat_session_id = chat.id
            chat._touch_from(message)
        for message in messages:
            message._notify_bus()
        ctx = self.env.context
        skip_mirror = (
            backfill
            or ctx.get("uniom_no_discuss_mirror")
            or ctx.get("uniom_mirror_origin")
        )
        if not skip_mirror:
            for message in messages:
                if message.chat_session_id:
                    message.chat_session_id._mirror_to_discuss(message)
        return messages

    def write(self, vals):
        old_states = {message.id: message.state for message in self} if "state" in vals else {}
        result = super().write(vals)
        if "state" in vals:
            for message in self:
                if old_states.get(message.id) == message.state:
                    continue
                if message.direction == "out":
                    message._notify_bus()
                chat = message.chat_session_id
                if not chat:
                    continue
                newest = chat.message_ids.sorted(key=lambda m: (m.date_sent or m.create_date or "", m.id))
                if newest and newest[-1].id == message.id:
                    # keep the sidebar tick describing the newest bubble
                    chat.write({"last_message_state": message.state or "sent"})
        return result

    def _notify_bus(self):
        """Tell open dashboards that a thread changed.

        Only ids and routing metadata travel on the bus: bus channels are
        not company-scoped, so message bodies must never be broadcast there
        (a multi-company leak). Clients re-read the record through the ORM,
        which applies the usual access/record rules.
        """
        self.ensure_one()
        try:
            self.env["bus.bus"]._sendone(
                self.env.ref("uniom_connector.group_uniom_user"),
                "uniom.message/new",
                {
                    "chat_id": self.chat_session_id.id,
                    "message_id": self.id,
                    "direction": self.direction or "",
                    "state": self.state or "",
                },
            )
        except Exception:  # noqa: BLE001 - a bus hiccup must not lose a message
            _logger.warning("Uniom: could not notify bus for message %s", self.id, exc_info=True)

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
        message_kind = "text"
        if attachment:
            is_image = (attachment.mimetype or "").startswith("image/")
            message_kind = "photo" if is_image else "document"
            method = "sendPhoto" if is_image else "sendDocument"
            file_field = "photo" if is_image else "document"
            result = connection._call(
                method,
                payload={
                    "chat_id": self.chat_id,
                    "caption": (self.body or "")[:1024] or None,
                },
                files={
                    file_field: (
                        attachment.name or "file",
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
        gateway_message_id = (result or {}).get("message_id")
        self.write(
            {
                "state": "sent",
                "uniom_message_id": str(gateway_message_id) if gateway_message_id else False,
                "message_kind": message_kind,
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
                self._create_failure_activity(error_text)
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
        self._create_failure_activity(error_text)

    def _create_failure_activity(self, error_text):
        """Leave a to-do on the business record so a human sees the failure.

        Best effort: activities need a mail.activity.mixin record and the
        activity type may be removed on stripped-down databases, neither of
        which may turn a failed send into an exception.
        """
        self.ensure_one()
        if not (self.record_res_model and self.record_res_id):
            return False
        try:
            record = self.env[self.record_res_model].browse(self.record_res_id).exists()
            if not record or not hasattr(record, "activity_ids"):
                return False
            activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
            if not activity_type:
                return False
            assignee = record.user_id if "user_id" in record._fields else False
            assignee = assignee or self.create_uid or self.env.user
            summary = _(
                "Uniom delivery failed: %(name)s",
                name=self.record_name or record.display_name or self.chat_id,
            )
            self.env["mail.activity"].create(
                {
                    "activity_type_id": activity_type.id,
                    "summary": summary[:255],
                    "note": error_text,
                    "res_model_id": self.env["ir.model"]._get_id(record._name),
                    "res_id": record.id,
                    "user_id": assignee.id,
                }
            )
        except Exception:  # noqa: BLE001 - activity is a courtesy, not the fix
            _logger.warning(
                "Uniom: could not create a failure activity for message %s", self.id, exc_info=True
            )
        return True

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
            # check_access covers ir.model.access AND ir.rule (verified in
            # odoo/models.py::_check_access) — the sudo render below is safe
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
             "edit_count": 0, "uniom_message_id": False, "uniom_update_id": False,
             "message_kind": "text", "error_message": False,
             "next_attempt": fields.Datetime.now(), "attachment_id": False}
        )
        duplicate._send_message()
        return True

    def action_edit_body(self, new_body):
        """Edit one outgoing text message from the dashboard (client RPC)."""
        self.ensure_one()
        new_body = (new_body or "").strip()
        if not new_body:
            raise UserError(_("Write the edited text first."))
        if self.direction != "out" or self.message_kind != "text":
            raise UserError(_("Only outgoing text messages can be edited."))
        self._edit_message(new_body)
        return self.read(["state", "body", "edit_count"])[0]

    def action_delete_message(self):
        """Delete one message from the messenger (client RPC)."""
        self.ensure_one()
        if self.direction != "out":
            raise UserError(_("Only outgoing messages can be deleted."))
        self.action_delete_from_messenger()
        return True

    # ------------------------------------------------------------------
    # Queue cron
    # ------------------------------------------------------------------
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

    @api.model
    def _cron_sync_states(self):
        """Refresh read/delivery ticks for recent outbound messages."""
        since = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        batch = self.search(
            [
                ("direction", "=", "out"),
                ("state", "=", "sent"),
                ("uniom_message_id", "!=", False),
                ("date_sent", ">=", since),
            ],
            limit=100,
            order="date_sent desc",
        )
        batch.action_sync_states()
        return True

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------
    @api.model
    def get_failed_chat_ids(self, limit=200):
        """Distinct conversation ids having failed outbound messages.

        Served from the backend (via _read_group, record rules applied)
        instead of orm.readGroup so the dashboard works unchanged on
        every Odoo version (19.0 renamed the JS grouping API).
        """
        try:
            limit = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            limit = 200
        rows = self._read_group(
            [
                ("state", "=", "error"),
                ("direction", "=", "out"),
                ("chat_session_id", "!=", False),
            ],
            ["chat_session_id"],
            ["__count"],
        )
        return [chat.id for chat, _count in rows if chat][:limit]

    def action_send_now(self):
        self.filtered(lambda m: m.state in ("outgoing", "error")).write(
            {"state": "outgoing", "retry_count": 0, "next_attempt": fields.Datetime.now()}
        )
        self._send_message()
        return True

    def action_cancel(self):
        """Cancel queued rows; a failed row is dismissable from the dashboard
        too (the JS calls this for both states, not an ad-hoc write)."""
        self.filtered(lambda m: m.state in ("outgoing", "error")).write(
            {"state": "canceled"}
        )
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
            "views": [[False, "form"]],
            "target": "current",
        }

    def action_sync_states(self):
        """Refresh seen/edited/deleted state from getMessageStates (≤100)."""
        targets = self.filtered(
            lambda m: m.direction == "out" and m.uniom_message_id and m.state == "sent"
        )
        if not targets:
            return True
        for connection in targets.mapped("connection_id"):
            batch = targets.filtered(lambda m: m.connection_id == connection)[:100]
            try:
                states = connection.sudo()._call(
                    "getMessageStates",
                    {
                        "messages": [
                            "%s/%s" % (m.chat_id, m.uniom_message_id) for m in batch
                        ]
                    },
                ) or []
            except Exception:  # noqa: BLE001 - state sync is best effort
                _logger.info(
                    "Uniom: getMessageStates failed for connection %s",
                    connection.id, exc_info=True,
                )
                continue
            by_index = {}
            # the gateway answers {"items": [...], "total", "success_count",
            # "partial_failure"}; keep the bare-list shape for older bridges
            items = states.get("items") if isinstance(states, dict) else states
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "request_index" in item:
                        by_index[item["request_index"]] = item
            now = fields.Datetime.now()
            for index, message in enumerate(batch):
                item = by_index.get(index) or {}
                values = {"state_updated_at": now}
                seen = (item.get("seen_state") or "").lower()
                if seen in ("read", "seen", "delivered", "unknown"):
                    values["seen_state"] = seen
                elif item.get("status") == "ok":
                    values["seen_state"] = "delivered"
                for key, field in (("seen_count", "seen_count"), ("views", "views_count")):
                    if isinstance(item.get(key), int):
                        values[field] = item[key]
                if item.get("edited") and not message.date_edited:
                    values["date_edited"] = now
                    values["edit_count"] = message.edit_count + 1
                if item.get("deleted") or item.get("status") == "deleted":
                    values["deleted_on_messenger"] = True
                message.write(values)
        return True

    def action_delete_from_messenger(self):
        """Delete sent messages via deleteMessage (best effort each)."""
        # direction guard: inbound rows carry gateway ids too, but only our
        # own messages may ever be deleted from the messenger
        targets = self.filtered(
            lambda m: m.direction == "out" and m.uniom_message_id and m.state == "sent"
        )
        for message in targets:
            try:
                message.connection_id.sudo()._call(
                    "deleteMessage",
                    {"chat_id": message.chat_id, "message_id": message.uniom_message_id},
                )
                message.write({"deleted_on_messenger": True})
            except Exception:  # noqa: BLE001 - per-message best effort
                _logger.info(
                    "Uniom: deleteMessage failed for %s", message.id, exc_info=True
                )
        return True

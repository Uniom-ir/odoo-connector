# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Conversations: one session per (connection, chat id), grouping every
incoming and outgoing message into a messenger-like thread with a quick
reply box — the WhatsApp-connector style UI, on top of the same queue."""

import logging

from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

from .uniom_connection import _datetime_from_timestamp, _parse_iso_datetime
from .uniom_tools import canonicalize_chat_id

_logger = logging.getLogger(__name__)


class UniomChat(models.Model):
    _name = "uniom.chat"
    _description = "Uniom Conversation"
    _order = "last_message_date desc nulls last, id desc"
    _rec_names_search = ("partner_id.name", "messenger_title", "chat_id")
    _connection_chat_uniq = models.Constraint(
        "unique(connection_id, chat_id)",
        "One conversation per connection and chat id.",
    )

    connection_id = fields.Many2one(
        "uniom.connection", required=True, index=True, ondelete="restrict"
    )
    platform = fields.Selection(
        related="connection_id.platform",
        string="Platform",
        store=False,
        readonly=True,
        help="Messenger of the connection, exposed so kanban cards can show "
        "the platform badge without an extra read.",
    )
    chat_id = fields.Char(required=True, index=True)
    partner_id = fields.Many2one("res.partner", index=True, ondelete="set null")
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, index=True
    )
    display_name = fields.Char(
        compute="_compute_display_name", search="_search_display_name"
    )
    chat_type = fields.Selection(
        [
            ("private", "Private"),
            ("group", "Group"),
            ("supergroup", "Supergroup"),
            ("channel", "Channel"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
        help="Chat kind reported by the messenger.",
    )
    messenger_title = fields.Char(help="Title (or full name) reported by the messenger.")
    messenger_username = fields.Char()
    messenger_photo_url = fields.Char()
    messenger_photo = fields.Binary(
        string="Messenger Photo",
        attachment=True,
        copy=False,
        help="Cached profile photo from getUserProfilePhotos.",
    )
    messenger_photo_updated_at = fields.Datetime(readonly=True, copy=False)
    avatar_url = fields.Char(compute="_compute_avatar_url")
    unread_count = fields.Integer(compute="_compute_unread_count", store=True)
    last_message_kind = fields.Char()
    last_message_direction = fields.Char(readonly=True)
    last_message_state = fields.Char(readonly=True)
    last_seen_label = fields.Char(help="Verbatim last-activity label from the gateway.")
    last_seen_at = fields.Datetime()
    last_seen_is_exact = fields.Boolean(default=False)
    presence_updated_at = fields.Datetime(readonly=True, copy=False)
    message_ids = fields.One2many("uniom.message", "chat_session_id", string="Thread")
    message_count = fields.Integer(compute="_compute_message_count")
    last_message_date = fields.Datetime(readonly=True)
    last_message_preview = fields.Char(readonly=True)
    discuss_channel_id = fields.Many2one(
        "discuss.channel",
        string="Discuss Channel",
        ondelete="set null",
        copy=False,
        help="Native Discuss thread mirroring this conversation: inbound "
        "messages are posted here so they appear under Discuss.",
    )
    reply_body = fields.Text(
        string="Draft reply",
        help="Write a reply here and press Send Reply; it goes out through "
        "the connection of this conversation.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("partner_id.name", "messenger_title", "chat_id")
    def _compute_display_name(self):
        for chat in self:
            chat.display_name = chat.partner_id.name or chat.messenger_title or chat.chat_id

    # searching display_name uses the inherited _search_display_name, which
    # ORs the fields below for positive operators and ANDs them for negative
    # ones (see _rec_names_search on the class).

    @api.depends("messenger_photo", "messenger_photo_url", "partner_id", "partner_id.image_1920")
    def _compute_avatar_url(self):
        for chat in self:
            if chat.messenger_photo:
                chat.avatar_url = "/web/image/uniom.chat/%s/messenger_photo" % chat.id
            elif chat.messenger_photo_url:
                chat.avatar_url = chat.messenger_photo_url
            elif chat.partner_id and chat.partner_id.image_1920:
                chat.avatar_url = "/web/image/res.partner/%s/image_128" % chat.partner_id.id
            else:
                # no photo anywhere: client renders the initial-letter
                # avatar instead of a broken-image icon
                chat.avatar_url = ""

    @api.depends("message_ids.is_read", "message_ids.direction")
    def _compute_unread_count(self):
        counts = {}
        if self.ids:
            groups = self.env["uniom.message"]._read_group(
                [
                    ("chat_session_id", "in", self.ids),
                    ("direction", "=", "in"),
                    ("is_read", "=", False),
                ],
                groupby=["chat_session_id"],
                aggregates=["__count"],
            )
            for chat, count in groups:
                counts[chat.id] = count
        for chat in self:
            chat.unread_count = counts.get(chat.id, 0)

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
            values = {
                "connection_id": message.connection_id.id,
                "chat_id": message.chat_id,
                "partner_id": message.partner_id.id,
                "company_id": message.company_id.id,
            }
            try:
                # unique(connection_id, chat_id): concurrent creators race to
                # the same row; the loser rolls back to this savepoint only
                # and re-searches
                with self.env.cr.savepoint():
                    chat = self.create(values)
            except IntegrityError:
                chat = self.search(
                    [
                        ("connection_id", "=", message.connection_id.id),
                        ("chat_id", "=", message.chat_id),
                    ],
                    limit=1,
                )
        if message.partner_id and not chat.partner_id:
            chat.partner_id = message.partner_id
        return chat

    def _touch_from(self, message):
        self.ensure_one()
        message_date = message.date_sent or fields.Datetime.now()
        if self.last_message_date and self.last_message_date > message_date:
            # out-of-order arrival (history backfill, delayed webhook): keep
            # the preview describing the newest message of the thread
            return
        self.write(
            {
                "last_message_date": message_date,
                "last_message_preview": (message.body or "")[:64],
                "last_message_kind": message.message_kind or "text",
                "last_message_direction": message.direction or "out",
                "last_message_state": message.state or "sent",
            }
        )

    # ------------------------------------------------------------------
    # Reply from the thread view / chat dashboard
    # ------------------------------------------------------------------
    def _queue_outbound(self, body, attachment=None):
        """Queue one outbound message through this conversation and attempt
        immediate delivery. Returns the uniom.message record."""
        self.ensure_one()
        chat_id = canonicalize_chat_id(self.chat_id)
        if not chat_id:
            raise UserError(
                _("This conversation has an invalid destination: %s", self.chat_id)
            )
        values = {
            "connection_id": self.connection_id.id,
            "chat_session_id": self.id,
            "direction": "out",
            "state": "outgoing",
            "chat_id": chat_id,
            "partner_id": self.partner_id.id,
            "body": body,
            "record_res_model": "res.partner",
            "record_res_id": self.partner_id.id,
            "record_name": self.partner_id.name,
        }
        if attachment:
            is_image = (attachment.mimetype or "").startswith("image/")
            values.update(
                {
                    "attachment_id": attachment.id,
                    "message_kind": "photo" if is_image else "document",
                }
            )
        message = self.env["uniom.message"].create(values)
        if attachment:
            # re-link the picked file to the message row, so permissions and
            # cleanup follow the message log instead of the source record.
            # No sudo: the caller validated ownership, and the user owns the
            # message row just created.
            attachment.write({"res_model": "uniom.message", "res_id": message.id})
        message._send_message()
        return message

    @api.model
    def get_outgoing_side(self):
        """Dashboard bubble side for the current user's conversations.

        ``ir.config_parameter`` reads need settings rights, which Uniom
        users don't have — so the dashboard calls this instead.
        Returns "left" or "right" (default "right").
        """
        side = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_str("uniom_connector.outgoing_side", "right")
        )
        return "left" if side == "left" else "right"

    def action_send_dashboard_reply(self, body):
        """Send one reply from the OWL chat dashboard (client action)."""
        self.ensure_one()
        body = (body or "").strip()
        if not body:
            raise UserError(_("Write a reply first."))
        message = self._queue_outbound(body)
        return message.read(["state", "error_message"])[0]

    def action_send_dashboard_attachment(self, attachment_id, caption=""):
        """Send a file from the OWL chat dashboard (client action)."""
        self.ensure_one()
        try:
            attachment_id = int(attachment_id)
        except (TypeError, ValueError):
            raise UserError(_("Invalid attachment."))
        attachment = self.env["ir.attachment"].browse(attachment_id).exists()
        if not attachment:
            raise UserError(_("Attachment not found."))
        if not attachment.raw:
            raise UserError(_("The attachment has no content."))
        # the dashboard uploads to this chat (res_model uniom.chat) or
        # unlinked; anything else (an invoice PDF the user can merely read)
        # must not be detachable onto a message via a forged id
        if attachment.res_model not in (False, "uniom.chat", "uniom.message"):
            raise UserError(_("Invalid attachment."))
        if attachment.res_model == "uniom.chat" and attachment.res_id != self.id:
            raise UserError(_("Invalid attachment."))
        if attachment.create_uid != self.env.user:
            raise UserError(_("Invalid attachment."))
        message = self._queue_outbound(
            (caption or "").strip()[:1024], attachment=attachment
        )
        return message.read(["state", "error_message"])[0]

    def action_send_reply(self):
        # validate every draft first: a mid-loop error must not roll back
        # replies the gateway already received
        for chat in self:
            if not (chat.reply_body or "").strip():
                raise UserError(_("Write a reply first."))
            if not canonicalize_chat_id(chat.chat_id):
                raise UserError(
                    _("This conversation has an invalid destination: %s"), chat.chat_id
                )
        sent = failed = 0
        for chat in self:
            message = chat._queue_outbound((chat.reply_body or "").strip())
            if message.state == "sent" and not message.error_message:
                sent += 1
                chat.reply_body = False
            else:
                failed += 1
        if failed:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "warning",
                    "sticky": True,
                    "message": _(
                        "%(sent)s reply(ies) sent, %(failed)s failed — see the "
                        "message log for the reason; failed replies stay queued "
                        "in the thread.",
                        sent=sent,
                        failed=failed,
                    ),
                },
            }
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
            "views": [[False, "form"]],
            "target": "current",
        }

    def action_open_discuss(self):
        """Open the mirrored Discuss thread (creating it on first use)."""
        self.ensure_one()
        channel = self._ensure_discuss_channel()
        # the Discuss client action restores a thread from active_id
        # formatted as 'model_id' (a bare tag or channel_id opens the inbox)
        return {
            "type": "ir.actions.client",
            "tag": "mail.action_discuss",
            "params": {"active_id": "discuss.channel_%s" % channel.id},
        }

    def _ensure_discuss_channel(self):
        """Get-or-create the native Discuss channel mirroring this chat.

        One `group`-type channel per conversation: the contact's name as
        the channel name (like a native DM), the contact's photo as the
        channel avatar when present, otherwise the platform brand icon.
        Members are the contact (when linked) plus the Uniom users allowed
        in this chat's company — Discuss membership alone grants read
        access, so company scoping mirrors the uniom.* record rules.
        """
        self.ensure_one()
        channel = self.discuss_channel_id.exists()
        if channel:
            self._sync_discuss_channel(channel)
            return channel
        # has_group (not a groups_id domain): resolves implied groups and
        # survives the 19.0 groups_id field rename
        users = self.env["res.users"].search([]).filtered(
            lambda u: u.has_group("uniom_connector.group_uniom_user")
        )
        if self.company_id:
            users = users.filtered(
                lambda u: not u.company_ids or self.company_id in u.company_ids
            )
        members = users.mapped("partner_id")
        if self.partner_id:
            members |= self.partner_id
        channel = self.env["discuss.channel"].create(
            {
                "name": self._discuss_channel_name(),
                "channel_type": "group",
                "image_128": self._discuss_channel_avatar(),
                "channel_member_ids": [(0, 0, {"partner_id": p.id}) for p in members],
                "description": "%s chat %s — replies here are sent via %s"
                % (
                    self._platform_label(),
                    "@%s" % self.messenger_username
                    if self.messenger_username
                    else self.chat_id,
                    self.connection_id.name,
                ),
            }
        )
        self.write({"discuss_channel_id": channel.id})
        return channel

    def _platform_label(self):
        """Human label for the connection platform (related field has no
        local selection list to read from)."""
        self.ensure_one()
        return {
            "bale": "Bale",
            "rubika": "Rubika",
            "eitaa": "Eitaa",
            "soroushplus": "Soroush+",
            "telegram": "Telegram",
        }.get(self.platform or "", "Uniom")

    def _discuss_channel_name(self):
        """Native-style name: the contact/thread name, no vendor prefix."""
        self.ensure_one()
        return self.display_name or self.chat_id

    def _discuss_channel_avatar(self):
        """Channel avatar: contact photo, else the platform brand icon."""
        self.ensure_one()
        if self.partner_id and self.partner_id.image_1920:
            return self.partner_id.image_1920
        return self._platform_icon_bytes()

    def _platform_icon_bytes(self):
        """BinaryValue of the bundled platform brand icon, or False.

        Binary fields no longer accept base64 bytes nor bare bytes on write
        (Odoo 20): callers get a ``BinaryBytes`` ready for image_128.
        """
        self.ensure_one()
        platform = self.platform or ""
        files = {
            "bale": "bale.png",
            "rubika": "rubika.png",
            "eitaa": "eitaa.svg",
            "soroushplus": "soroushplus.svg",
            "telegram": "telegram.svg",
        }
        filename = files.get(platform)
        if not filename:
            return False
        try:
            import os

            path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "static",
                "img",
                "platforms",
                filename,
            )
            with open(path, "rb") as handle:
                return BinaryBytes(handle.read())
        except OSError:
            return False

    def _sync_discuss_channel(self, channel):
        """Refresh name/description/avatar on an existing mirror (contact
        linked later, platform set after creation, ...). Cheap writes
        only on change; also migrates the old vendor-prefixed naming."""
        self.ensure_one()
        values = {}
        name = self._discuss_channel_name()
        if channel.name != name:
            values["name"] = name
        if (channel.description or "").startswith("Mirrored Uniom conversation"):
            values["description"] = "%s chat %s — replies here are sent via %s" % (
                self._platform_label(),
                "@%s" % self.messenger_username if self.messenger_username else self.chat_id,
                self.connection_id.name,
            )
        if not channel.image_128:
            avatar = self._discuss_channel_avatar()
            if avatar:
                values["image_128"] = avatar
        if values:
            channel.write(values)
        return True

    def _mirror_to_discuss(self, message):
        """Post one uniom.message into the mirrored Discuss thread.

        Best effort by contract: Discuss must never break inbound
        processing. Outbound mirrors carry the sender; inbound mirrors
        carry the contact as author. ``uniom_mirror_origin`` marks the
        post so the reverse bridge ignores it (no echo loop).
        """
        self.ensure_one()
        try:
            channel = self._ensure_discuss_channel()
            if message.direction == "in" and message.partner_id:
                author = message.partner_id.id
            elif message.create_uid and not message.create_uid._is_public():
                author = message.create_uid.partner_id.id
            else:
                author = self.env.user.partner_id.id
            channel.with_context(uniom_mirror_origin=True).message_post(
                body=message.body or "",
                author_id=author,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        except Exception:  # noqa: BLE001 - mirror is a courtesy
            _logger.warning(
                "Uniom: could not mirror message %s to Discuss", message.id, exc_info=True
            )
        return True

    def _forward_from_discuss(self, discuss_message):
        """Send one Discuss post out through this conversation's queue.

        Only human internal-user comments are forwarded; bot posts
        (OdooBot answers), portal shares and anything else are ignored
        silently. Failures are logged, never raised into the Discuss
        composer (the queue retry + failure to-do still apply).
        """
        self.ensure_one()
        try:
            author = discuss_message.author_id
            root = self.env.ref("base.partner_root", raise_if_not_found=False)
            if root and author.id == root.id:
                # OdooBot is internal but must never talk to contacts
                return False
            user = self.env["res.users"].search(
                [("partner_id", "=", author.id)], limit=1
            )
            if not user or not user._is_internal():
                return False
            from .discuss_channel import _html_to_text

            body = _html_to_text(discuss_message.body)
            if not body:
                return False
            self.with_context(uniom_mirror_origin=True)._queue_outbound(body)
        except Exception:  # noqa: BLE001 - never break the Discuss composer
            _logger.warning(
                "Uniom: could not forward Discuss message %s", discuss_message.id,
                exc_info=True,
            )
            return False
        return True

    def action_mark_read(self):
        """Clear the unread badge and send the messenger read receipt."""
        self.ensure_one()
        self.message_ids.filtered(
            lambda message: message.direction == "in" and not message.is_read
        ).write({"is_read": True})
        try:
            self.connection_id.sudo()._call("markChatRead", {"chat_id": self.chat_id})
        except Exception:  # noqa: BLE001 - read receipts are best effort
            # Bale self-chats (and some platforms) answer 404 here even
            # though the local badge is already cleared — never surface it.
            _logger.debug("Uniom: markChatRead failed for chat %s", self.id, exc_info=True)
        return True

    def action_sync_presence(self):
        """Refresh last-seen/last-activity from the gateway (best effort)."""
        self.ensure_one()
        try:
            activity = (
                self.connection_id.sudo()._call(
                    "getChatActivity", {"chat_id": self.chat_id}
                )
                or {}
            )
        except Exception:  # noqa: BLE001 - presence must never break the UI
            _logger.info("Uniom: presence sync failed for chat %s", self.id, exc_info=True)
            return True
        if not isinstance(activity, dict):
            activity = {}
        values = {"presence_updated_at": fields.Datetime.now()}
        if "last_activity_label" in activity:
            # stored verbatim: the gateway already localizes it for us
            values["last_seen_label"] = activity.get("last_activity_label") or ""
        if "last_activity_is_exact" in activity:
            values["last_seen_is_exact"] = bool(activity.get("last_activity_is_exact"))
        last_seen_at = _parse_iso_datetime(activity.get("last_activity_at"))
        if last_seen_at:
            values["last_seen_at"] = last_seen_at
        self.write(values)
        # profile photos change rarely: refresh weekly (or on first sync)
        # whenever presence is refreshed (chat open + 6h cron)
        photo_stale = (
            not self.messenger_photo_updated_at
            or self.messenger_photo_updated_at
            < fields.Datetime.subtract(fields.Datetime.now(), days=7)
        )
        if photo_stale:
            self.action_sync_photo()
        return True

    def action_sync_photo(self):
        """Cache the contact's profile photo via getUserProfilePhotos."""
        self.ensure_one()
        try:
            photos = (
                self.connection_id.sudo()._call(
                    "getUserProfilePhotos", {"user_id": self.chat_id, "limit": 1}
                )
                or {}
            )
        except Exception:  # noqa: BLE001 - photo sync is best effort
            _logger.info("Uniom: photo sync failed for chat %s", self.id, exc_info=True)
            return True
        sizes = (photos.get("photos") or [[]])[0] if isinstance(photos, dict) else []
        best = max(sizes, key=lambda s: (s.get("file_size") or 0), default=None) or {}
        file_id = best.get("file_id")
        if not file_id:
            return True
        try:
            content = self.connection_id.sudo()._download_file_bytes(file_id)
        except Exception:  # noqa: BLE001 - download failures just skip
            _logger.info("Uniom: photo download failed for chat %s", self.id, exc_info=True)
            return True
        if content:
            self.write(
                {
                    "messenger_photo": BinaryBytes(content),
                    "messenger_photo_updated_at": fields.Datetime.now(),
                }
            )
        return True

    def action_load_history(self, limit=30, before_uniom_id=None):
        """Backfill older messages from getChatHistory into this thread."""
        self.ensure_one()
        try:
            page_size = int(limit)
        except (TypeError, ValueError):
            page_size = 30
        # the gateway page bounds are 200 (500 on Rubika); the dashboard
        # pages 30 at a time, so a small hard cap keeps backfill snappy
        page_size = max(1, min(page_size, 50))
        payload = {"chat_id": self.chat_id, "limit": page_size}
        if before_uniom_id:
            payload["offset_id"] = str(before_uniom_id)
        connection = self.connection_id.sudo()
        history = connection._call("getChatHistory", payload) or []
        if not isinstance(history, list):
            history = []
        # gateway pages are newest-first; create oldest-first so the thread
        # and its last-message preview end on the newest row
        history = list(reversed(history))
        message_ids = [
            str(item.get("message_id"))
            for item in history
            if isinstance(item, dict) and item.get("message_id") is not None
        ]
        existing_rows = self.env["uniom.message"].search(
            [
                ("connection_id", "=", connection.id),
                # gateway message ids restart per chat: never dedupe or
                # reconcile against another conversation's rows
                ("chat_session_id", "=", self.id),
                ("uniom_message_id", "in", message_ids),
            ]
        )
        existing = set(existing_rows.mapped("uniom_message_id"))
        by_gateway_id = {m.uniom_message_id: m for m in existing_rows}
        company = connection.company_id or self.company_id or self.env.company
        # without a cached own id every direction reads "in": reconciling
        # then would flip correct outbound rows to the incoming side
        own_known = bool(connection._own_user_id())
        loaded = 0
        fixed = 0
        for item in history:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("message_id")
            if raw_id is None:
                continue
            message_key = str(raw_id)
            direction = connection._direction_for_sender(item)
            if message_key in existing:
                # reconcile rows stored before direction detection existed:
                # the raw sender is not kept, so the fresh history payload
                # is the only source of truth. is_read untouched — old
                # history must not re-badge the inbox.
                row = by_gateway_id.get(message_key)
                if own_known and row and row.direction != direction:
                    row.direction = direction
                    fixed += 1
                continue
            kind = connection._detect_message_kind(item)
            body = connection._compose_message_body(item, kind)
            # uniom_backfill tells create() the whole page is historical and
            # must not repopulate the unread badge
            self.env["uniom.message"].with_context(uniom_backfill=True).create(
                {
                    "connection_id": connection.id,
                    "chat_session_id": self.id,
                    "direction": direction,
                    "state": "sent",
                    "chat_id": self.chat_id,
                    "partner_id": self.partner_id.id,
                    "body": body,
                    "message_kind": kind,
                    "uniom_message_id": message_key,
                    "is_read": True,
                    "date_sent": _datetime_from_timestamp(item.get("date"))
                    or fields.Datetime.now(),
                    "company_id": company.id,
                    "record_res_model": "res.partner" if self.partner_id else False,
                    "record_res_id": self.partner_id.id or False,
                    "record_name": self.partner_id.name or False,
                }
            )
            existing.add(message_key)
            loaded += 1
        return {"loaded": loaded, "fixed": fixed}

    def action_load_history_button(self):
        """Form-view wrapper: same backfill, UI-safe return value."""
        self.ensure_one()
        result = self.action_load_history()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Uniom"),
                "message": _("%s message(s) loaded.", result.get("loaded", 0)),
                "type": "success",
                "sticky": False,
            },
        }

    def action_send_chat_action(self, action="typing"):
        """Broadcast a typing/uploading hint; never raises to the client."""
        self.ensure_one()
        try:
            self.connection_id.sudo()._call(
                "sendChatAction",
                {"chat_id": self.chat_id, "action": action or "typing"},
            )
            return True
        except Exception:  # noqa: BLE001 - purely cosmetic
            return False

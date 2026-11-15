# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Two-way Discuss bridge: replies typed in a mirrored channel go to Uniom.

Every ``uniom.chat`` mirrors into one ``discuss.channel`` (see
``uniom.chat._ensure_discuss_channel``). This override forwards messages an
internal user posts there back through the conversation's queue, so the
Discuss composer is a working reply box instead of a silent dead end.

Loop guards:
- only ``message_type == 'comment'`` from internal users is forwarded;
  notifications, bot posts and portal shares are ignored;
- the mirror itself (``uniom.chat._mirror_to_discuss``) and history
  backfills set ``uniom_mirror_origin`` in context and are skipped;
- channels without a linked ``uniom.chat`` behave exactly as before.
"""
import logging
import re

from odoo import models

_logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")


def _html_to_text(body):
    """Best-effort HTML → messenger plaintext (Discuss stores HTML)."""
    import html as _html

    if not body:
        return ""
    # Discuss escapes the posted markup once (body arrives as Markup with
    # &lt;p&gt; entities); unescape first so tags strip in one pass
    text = _html.unescape(str(body))
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return _WS_RE.sub(" ", _html.unescape(text)).strip()


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def message_post(self, **kwargs):
        messages = super().message_post(**kwargs)
        if self.env.context.get("uniom_mirror_origin"):
            return messages
        for channel in self:
            chat = self.env["uniom.chat"].search(
                [("discuss_channel_id", "=", channel.id)], limit=1
            )
            if not chat:
                continue
            for message in messages.filtered(
                lambda m: m.model == "discuss.channel"
                and m.res_id == channel.id
                and m.message_type == "comment"
            ):
                chat._forward_from_discuss(message)
        return messages

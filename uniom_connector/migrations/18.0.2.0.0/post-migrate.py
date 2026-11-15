# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Backfill columns added by the 18.0.2.0.0 messenger rework.

New nullable columns land NULL on pre-existing rows (ORM defaults apply to
new records only). NULL ``is_read`` would read as falsy and flood the inbox
with ancient unread badges, so backfill everything to its default here.
(``uniom_message_id`` Integer→Char needs no explicit ALTER: PostgreSQL casts
int→varchar implicitly and Odoo's auto-migrate applies it.)
"""


def migrate(cr, version):
    cr.execute(
        "UPDATE uniom_message SET is_read = TRUE WHERE is_read IS NULL"
    )
    cr.execute(
        "UPDATE uniom_message SET message_kind = 'text' "
        "WHERE message_kind IS NULL"
    )
    cr.execute(
        "UPDATE uniom_message SET seen_state = 'unknown' "
        "WHERE seen_state IS NULL"
    )

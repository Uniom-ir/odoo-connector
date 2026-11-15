# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Event-driven automation: rules listen to business events (order confirmed,
invoice posted, ...) and send the linked template to the customer phone
and/or manual destinations (channels, groups).

Business hooks stay one-liners (see sale.order / account.move / ...): they
only call :meth:`_apply_trigger`, and this engine guarantees that no
messaging problem can ever break the business flow.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

from .uniom_tools import canonicalize_chat_id, parse_manual_chat_ids

_logger = logging.getLogger(__name__)

# trigger -> (model, partner field, default report to attach, editable)
TRIGGER_MODELS = {
    "quotation_sent": ("sale.order", "partner_id", False, False),
    "sale_order_confirmed": ("sale.order", "partner_id", "sale.action_report_saleorder", True),
    "invoice_posted": ("account.move", "partner_id", "account.account_invoices", True),
    "payment_received": ("account.payment", "partner_id", "account.action_report_payment_receipt", False),
    "picking_done": ("stock.picking", "partner_id", False, True),
    "product_created": ("product.template", False, False, False),
    "product_price_changed": ("product.template", False, False, False),
}


def _trigger_selection(self):
    return [
        ("quotation_sent", _("Quotation Sent")),
        ("sale_order_confirmed", _("Sale Order Confirmed")),
        ("invoice_posted", _("Invoice Posted")),
        ("payment_received", _("Payment Received")),
        ("picking_done", _("Delivery Done")),
        ("product_created", _("Product Published")),
        ("product_price_changed", _("Product Price Changed")),
    ]


class UniomRule(models.Model):
    _name = "uniom.rule"
    _description = "Uniom Automation Rule"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        index=True,
        help="Leave empty to apply in every company.",
    )
    connection_id = fields.Many2one(
        "uniom.connection",
        string="Connection",
        help="Optional: use a specific Uniom connection (messenger). "
        "Empty = first active connection of the company.",
    )
    trigger = fields.Selection(
        selection=_trigger_selection, required=True, index=True
    )
    trigger_model = fields.Char(compute="_compute_trigger_model", store=True)
    domain = fields.Char(
        string="Apply on",
        default="[]",
        help="Optional Odoo domain restricting which records trigger this rule, "
        "e.g. [('amount_total', '>', 1000000)]",
    )
    partner_field = fields.Char(
        compute="_compute_partner_field",
        store=True,
        readonly=False,
        help="Relational field holding the customer to notify "
        "(partner_id for orders and invoices).",
    )
    template_id = fields.Many2one(
        "uniom.template",
        required=True,
        string="Fallback Template",
        domain="[('model_id.model', '=', trigger_model)]",
    )
    template_ids = fields.Many2many(
        "uniom.template",
        "uniom_rule_template_rel",
        "rule_id",
        "template_id",
        string="Translated Templates",
        domain="[('model_id.model', '=', trigger_model)]",
        help="Optional per-language templates: picked when they match the "
        "customer's language, otherwise the fallback template is used.",
    )
    manual_chat_ids = fields.Text(
        string="Also Send To",
        help="Extra destinations, one per line: @channel, +989123456789, "
        "09123456789 or numeric chat id. Useful to keep your own channel "
        "informed about new orders.",
    )
    include_document = fields.Boolean(
        string="Attach PDF Report",
        help="Send the record's standard PDF report as a document with the message.",
    )
    report_ref = fields.Char(
        help="Technical reference of the QWeb report to attach "
        "(auto-filled from the event, editable).",
    )
    edit_previous = fields.Boolean(
        string="Edit Previous Message",
        help="Instead of sending a new message, edit the one this rule sent "
        "earlier for the same record (ideal for price updates in a channel).",
    )
    send_immediately = fields.Boolean(
        string="Send Immediately",
        default=True,
        help="Send the moment the event happens. Unchecked: only queue for "
        "the periodic cron. Failures are always re-queued either way.",
    )

    # ------------------------------------------------------------------
    # Computed plumbing
    # ------------------------------------------------------------------
    @api.depends("trigger")
    def _compute_trigger_model(self):
        for rule in self:
            rule.trigger_model = TRIGGER_MODELS.get(rule.trigger, ("",))[0]

    @api.depends("trigger")
    def _compute_partner_field(self):
        for rule in self:
            rule.partner_field = TRIGGER_MODELS.get(rule.trigger, ("", False))[1] or False

    @api.onchange("trigger")
    def _onchange_trigger(self):
        if self.trigger:
            _model, _partner, report, _editable = TRIGGER_MODELS[self.trigger]
            self.report_ref = report
            self.include_document = False
            self.edit_previous = self.trigger == "product_price_changed"

    # ------------------------------------------------------------------
    # Entry point used by business hooks
    # ------------------------------------------------------------------
    @api.model
    def _apply_trigger(self, trigger, records):
        """Fire all active rules for *trigger* on *records*.

        Never raises into the caller: a messaging failure must not block an
        order confirmation or an invoice posting.
        """
        enabled = self.env["ir.config_parameter"].sudo().get_param("uniom_connector.enabled", "True")
        if str(enabled).strip().lower() in ("false", "0", "no", "off") or not records:
            return False
        try:
            rules = self.search([("trigger", "=", trigger), ("active", "=", True)])
            for rule in rules:
                rule._process(records)
        except Exception:  # noqa: BLE001 - deliberate business-flow guard
            _logger.exception("Uniom: applying trigger %s failed", trigger)
        return True

    def _process(self, records):
        self.ensure_one()
        model_name = TRIGGER_MODELS[self.trigger][0]
        records = records.filtered(lambda r: r._name == model_name)
        if not records:
            return False
        records = self._filter_domain(records)
        records = self._filter_company(records)
        if not records:
            return False
        connection = self.connection_id or self.env["uniom.connection"]._get_default_connection(
            records[:1].company_id
        )
        if not connection:
            _logger.warning(
                "Uniom rule %s skipped: no active connection for company %s",
                self.name,
                records[:1].company_id.name,
            )
            return False
        for record in records:
            self._process_record(record, connection)
        return True

    def _filter_domain(self, records):
        self.ensure_one()
        if self.domain and self.domain != "[]":
            try:
                domain = safe_eval(self.domain)
            except Exception:
                _logger.exception("Uniom rule %s has an invalid domain: %s", self.name, self.domain)
                return records.browse()
            try:
                return records.filtered_domain(domain)
            except Exception:
                _logger.exception("Uniom rule %s domain failed", self.name)
                return records.browse()
        return records

    def _filter_company(self, records):
        self.ensure_one()
        if not self.company_id:
            return records
        return records.filtered(
            lambda r: not getattr(r, "company_id", None) or r.company_id == self.company_id
        )

    # ------------------------------------------------------------------
    # One record
    # ------------------------------------------------------------------
    def _process_record(self, record, connection):
        self.ensure_one()
        lang = self._get_lang(record)
        template = self._get_template_for(record, lang)
        render_record = record.with_context(lang=lang) if lang else record
        rendered = template._render_for(render_record)
        body = rendered.get(record.id)
        if not body:
            _logger.info("Uniom rule %s: empty body for %s, skipped", self.name, record)
            return False

        if self.edit_previous:
            previous = self.env["uniom.message"].search(
                [
                    ("rule_id", "=", self.id),
                    ("record_res_model", "=", record._name),
                    ("record_res_id", "=", record.id),
                    ("state", "=", "sent"),
                    ("direction", "=", "out"),
                ],
                order="id desc",
                limit=1,
            )
            if previous:
                previous._edit_message(body)
                return True

        values_base = {
            "connection_id": connection.id,
            "direction": "out",
            "state": "outgoing",
            "rule_id": self.id,
            "template_id": template.id,
            "record_res_model": record._name,
            "record_res_id": record.id,
            "record_name": record.display_name,
            "body": body,
            "report_ref": self.include_document and self.report_ref or False,
            "company_id": (getattr(record, "company_id", False) or self.env.company).id,
        }
        messages = self.env["uniom.message"]
        for chat_id, partner in self._resolve_recipients(record):
            messages |= self.env["uniom.message"].create(
                dict(values_base, chat_id=chat_id, partner_id=partner.id if partner else False)
            )
        if self.send_immediately:
            messages._send_message()
        return True

    def _get_lang(self, record):
        partner = self._get_partner(record)
        return (
            (partner.lang if partner else False)
            or self.env.context.get("lang")
            or self.env.user.lang
        )

    def _get_template_for(self, record, lang=False):
        self.ensure_one()
        lang = lang or self._get_lang(record)
        if lang:
            code = lang.split("_")[0]
            for template in self.template_ids:
                if template.lang_id and template.lang_id.code.startswith(code):
                    return template
        return self.template_id

    def _get_partner(self, record):
        self.ensure_one()
        if self.partner_field:
            partner = getattr(record, self.partner_field, None)
            return partner if partner and partner._name == "res.partner" else None
        return None

    def _resolve_recipients(self, record):
        """Return a list of ``(chat_id, partner)`` tuples for one record."""
        self.ensure_one()
        recipients = []
        seen = set()
        partner = self._get_partner(record)
        if partner and not partner.uniom_opt_out:
            chat_id = partner.uniom_chat_id or canonicalize_chat_id(partner.phone)
            if chat_id:
                recipients.append((chat_id, partner))
                seen.add(chat_id)
        for chat_id in parse_manual_chat_ids(self.manual_chat_ids):
            if chat_id not in seen:
                recipients.append((chat_id, None))
                seen.add(chat_id)
        if partner and partner.uniom_opt_out:
            # The customer opted out: only manual/channel destinations remain.
            return [r for r in recipients if r[1] is None]
        return recipients

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def action_test_rule(self):
        """Queue one message for the most recent record of the trigger model
        so the user can verify the rendering without waiting for an event."""
        self.ensure_one()
        model_name = TRIGGER_MODELS[self.trigger][0]
        record = self.env[model_name].search([], limit=1)
        if not record:
            raise UserError(
                _("No record of type %(model)s exists yet to test this rule.", model=model_name)
            )
        self._process(record)
        return {
            "type": "ir.actions.act_window",
            "name": _("Uniom Messages"),
            "res_model": "uniom.message",
            "view_mode": "list,form",
            "domain": [("rule_id", "=", self.id)],
        }

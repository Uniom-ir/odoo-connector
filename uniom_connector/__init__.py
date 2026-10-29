# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from . import controllers
from . import models
from . import wizards


def post_init_hook(env):
    """Link shipped fa/ar templates to their language records.

    Language records only exist once a language has been activated in the
    instance, so the XML data uses code-based searches that silently stay
    empty otherwise; this hook re-links after install and is also safe to
    re-run (e.g. from an upgrade) once languages appear.
    """
    lang_pool = env["res.lang"].with_context(active_test=False)
    links = {
        "fa_IR": [
            "template_sale_confirmed_fa",
            "template_invoice_posted_fa",
            "template_picking_done_fa",
            "template_payment_received_fa",
            "template_price_changed_fa",
        ],
        "ar_001": [
            "template_sale_confirmed_ar",
            "template_invoice_posted_ar",
            "template_picking_done_ar",
            "template_price_changed_ar",
        ],
    }
    for code, xmlids in links.items():
        lang = lang_pool.search([("code", "=", code)], limit=1)
        if not lang:
            lang = lang_pool.search([("code", "=like", code.split("_")[0] + "_%")], limit=1)
        if not lang:
            continue
        for xmlid in xmlids:
            template = env.ref("uniom_connector." + xmlid, raise_if_not_found=False)
            if template and not template.lang_id:
                template.lang_id = lang

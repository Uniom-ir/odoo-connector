# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
{
    "name": "Uniom Messaging Gateway",
    "summary": "Send order, invoice, payment and delivery notifications to "
    "customers and channels on Bale, Rubika, Eitaa, Soroush+ and Telegram "
    "through the Uniom gateway.",
    "description": """
Uniom Messaging Gateway for Odoo
================================

Connect Odoo to the Uniom messaging gateway (https://uniom.ir) and notify
your customers on the messengers they actually use — Bale, Rubika, Eitaa,
Soroush+ and Telegram — straight from sale orders, invoices, payments,
deliveries and product price changes.

Highlights
----------
* One API key, full messenger coverage (Telegram Bot API compatible gateway)
* Event automation: quotation sent, sale confirmed, invoice posted (with PDF),
  payment received, delivery done, product published, price change with
  message *editing* in your channel
* Ready-to-use templates in English, Persian and Arabic (RTL friendly)
* Every message is queued, retried with backoff and fully logged per record
* Webhook endpoint for inbound messages, matched to the customer contact
* Multi-company connections, user/manager groups, works out of the box
    """,
    "author": "Uniom",
    "website": "https://uniom.ir",
    "category": "Discuss",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "development_status": "Production/Stable",
    "depends": [
        "base_setup",
        "mail",
        "sale_management",
        "account",
        "stock",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/uniom_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "data/uniom_template_data.xml",
        "data/uniom_rule_data.xml",
        "wizards/uniom_send_wizard_views.xml",
        "views/uniom_connection_views.xml",
        "views/uniom_message_views.xml",
        "views/uniom_rule_views.xml",
        "views/uniom_template_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/stock_picking_views.xml",
        "views/uniom_menus.xml",
    ],
    "demo": [
        "demo/uniom_demo.xml",
    ],
    # add real screenshots here (static/description/screenshot_01.png ...)
    # after running .github/workflows/screenshots.yml
    "images": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}

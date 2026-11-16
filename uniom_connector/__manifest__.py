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

Connect Odoo to the Uniom messaging gateway (https://uniom.ir) and reach
your customers on the messengers they actually use -- Bale, Rubika, Eitaa,
Soroush+ and Telegram -- straight from sale orders, invoices, payments,
deliveries and product price changes. Chat with them in a built-in
WhatsApp-style messenger: threads, unread badges, last-seen presence,
photos and files, history backfill and live updates.

Highlights
----------

* Login-style setup: Connect Uniom Account -- one API key, one click,
  webhook or polling inbound, conversations seeded automatically

* Conversations: messenger UI with unread counters, presence, media
  bubbles, day dividers, history backfill and a composer that sends
  text, photos and documents through Uniom

* Inbound that works everywhere: webhook for public servers, getUpdates
  polling behind NAT -- photos, files, voice, locations and polls
  all arrive with contact matching

* Event automation: quotation sent, sale confirmed, invoice posted (with
  PDF), payment received, delivery done, product published, price change
  with message *editing* in your channel

* Ready-to-use templates in English, Persian and Arabic (RTL friendly)

* Every message is queued, retried with backoff and fully logged per record

* Multi-company connections, user/manager groups, works out of the box
    """,
    "author": "Uniom",
    "website": "https://uniom.ir",
    "category": "Discuss",
    "version": "18.0.2.0.3",
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
    "assets": {
        "web.assets_backend": [
            "uniom_connector/static/src/uniom_chat_dashboard.xml",
            "uniom_connector/static/src/uniom_chat_dashboard.js",
            "uniom_connector/static/src/uniom_chat_dashboard.scss",
            "uniom_connector/static/src/uniom_platform_picker.xml",
            "uniom_connector/static/src/uniom_platform_picker.js",
            "uniom_connector/static/src/uniom_platform_picker.scss",
        ],
    },
    "data": [
        "security/uniom_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "data/uniom_template_data.xml",
        "data/uniom_rule_data.xml",
        "wizards/uniom_send_wizard_views.xml",
        "wizards/uniom_setup_wizard_views.xml",
        "wizards/uniom_link_wizard_views.xml",
        "views/uniom_connection_views.xml",
        "views/uniom_message_views.xml",
        "views/uniom_chat_views.xml",
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
    "images": [
        "static/description/uniom_chat_dashboard_screenshot.png",
        "static/description/uniom_chat_thread_screenshot.png",
        "static/description/uniom_link_wizard_screenshot.png",
        "static/description/uniom_connect_wizard_screenshot.png",
        "static/description/uniom_discuss_screenshot.png",
        "static/description/uniom_messages_screenshot.png",
        "static/description/uniom_messages_rtl_screenshot.png",
        "static/description/uniom_message_form_screenshot.png",
        "static/description/uniom_rules_screenshot.png",
        "static/description/uniom_connections_screenshot.png",
        "static/description/uniom_templates_screenshot.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}

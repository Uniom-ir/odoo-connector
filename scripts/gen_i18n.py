#!/usr/bin/env python3
# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Regenerate i18n/uniom_connector.pot, i18n/fa_IR.po and i18n/ar_001.po.

Preferred flow (structure identical to what Odoo exports):
  1. install the module in an Odoo db with the languages activated
  2. Settings > Translations > Export: po, language fa_IR, module
     uniom_connector  (or via base.language.export wizard)
  3. python3 scripts/gen_i18n.py /path/to/exported.po

Without a skeleton argument, entries are emitted with synthetic
"code:"-occurrences only (fallback; UI model_terms entries will be
missing).
"""
import datetime
import os
import re
import sys

import polib
from pathlib import Path

# reproducible: honor SOURCE_DATE_EPOCH (defaults to a fixed stamp) so a
# regeneration never rewrites headers and every i18n diff is content-only
_stamp = datetime.datetime.fromtimestamp(
    int(os.environ.get("SOURCE_DATE_EPOCH", "1763200000"))
)  # 2025-11-15T00:00:00Z
NOW = _stamp.strftime("%Y-%m-%d %H:%M") + "+0000"
MODULE = "uniom_connector"
# manifest series, so a 19/20 checkout stamps its own version
SERIES = __import__("os").environ.get("ODOO_SERIES") or "18.0"
HERE = Path(__file__).resolve().parent
I18N = HERE.parent / MODULE / "i18n"
I18N.mkdir(exist_ok=True)

# Extra UI strings that only live inside view archs / action help blocks.
T_EXTRA = {
    "Customers are notified on their phone number (or Uniom Chat ID) unless they opted out. Extra destinations above receive every message too — one per line.": (
        "مشتریان در شماره موبایل (یا شناسه چت یونیوم) خود پیام دریافت می‌کنند مگر آنکه انصراف داده باشند. مقصدهای اضافه بالا هم هر پیام را دریافت می‌کنند — هر خط یک مقصد.",
        "يستلم العملاء الإشعارات على رقم هاتفهم (أو معرف محادثة Uniom) ما لم يلغوا الاشتراك. الوجهات الإضافية أعلاه تستلم كل رسالة أيضاً — وجهة واحدة في كل سطر.",
    ),
    "Placeholders use the standard Odoo syntax: {{ object.field }}, {{ object.partner_id.name }}, ...": (
        "جای‌نگه‌دارها از نگارش استاندارد اودو استفاده می‌کنند: {{ object.field }}، {{ object.partner_id.name }} و ...",
        "تستخدم العناصر النائبة الصيغة القياسية لأودو: {{ object.field }}، {{ object.partner_id.name }}، ...",
    ),
    "Create your first Uniom connection": ("اولین اتصال یونیوم را بسازید", "أنشئ أول اتصال Uniom لك"),
    "Paste an API key from your Uniom dashboard — one key per messenger account (Bale, Rubika, Eitaa, Soroush+, Telegram).": (
        "کلید API را از داشبورد یونیوم کپی کنید — یک کلید برای هر حساب پیام‌رسان (بله، روبیکا، ایتا، سروش‌پلاس، تلگرام).",
        "الصق مفتاح API من لوحة تحكم Uniom — مفتاح واحد لكل حساب مراسلة (بله، روبيكا، إيتا، سروش+، تيليجرام).",
    ),
    "Create an automation rule": ("یک قانون خودکار بسازید", "أنشئ قاعدة أتمتة"),
    "Pick a business event (order confirmed, invoice posted, price changed...), a message template and the destinations — Uniom does the rest.": (
        "یک رویداد کسب‌وکار (تأیید سفارش، ثبت فاکتور، تغییر قیمت و ...)، یک قالب پیام و مقصدها را انتخاب کنید — بقیه را یونیوم انجام می‌دهد.",
        "اختر حدثاً تجارياً (تأكيد الطلب، ترحيل الفاتورة، تغيير السعر...)، وقالب رسالة والوجهات — ويتولى Uniom الباقي.",
    ),
}

# msgid -> (persian, arabic); None keeps the msgid untranslated.
T = {
    # ---- menus / actions / buttons -----------------------------------
    "Messages": ("پیام‌ها", "الرسائل"),
    "Automation Rules": ("قوانین خودکار", "قواعد الأتمتة"),
    "Templates": ("قالب‌ها", "القوالب"),
    "Connections": ("اتصال‌ها", "الاتصالات"),
    "Connection": ("اتصال", "الاتصال"),
    "Send via Uniom": ("ارسال با یونیوم", "إرسال عبر Uniom"),
    "Send": ("ارسال", "إرسال"),
    "Cancel": ("انصراف", "إلغاء"),
    "Send / Retry": ("ارسال / تلاش مجدد", "إرسال / إعادة المحاولة"),
    "Test Connection": ("تست اتصال", "اختبار الاتصال"),
    "Register Webhook": ("ثبت وب‌هوک", "تسجيل Webhook"),
    "Remove Webhook": ("حذف وب‌هوک", "إزالة Webhook"),
    "New Secret": ("رمز جدید", "رمز جديد"),
    "Test with Last Record": ("آزمایش با آخرین رکورد", "اختبار مع آخر سجل"),
    "Open Record": ("باز کردن رکورد", "فتح السجل"),
    "Open Connections": ("باز کردن اتصال‌ها", "فتح الاتصالات"),
    "Preview": ("پیش‌نمایش", "معاينة"),
    "Archived": ("بایگانی شده", "مؤرشف"),
    "Notes": ("یادداشت‌ها", "ملاحظات"),
    "Uniom Messaging": ("پیام‌رسانی یونیوم", "مراسلات Uniom"),
    "Uniom Messages": ("پیام‌های یونیوم", "رسائل Uniom"),
    "Uniom Messaging Gateway": ("دروازه پیام‌رسانی یونیوم", "بوابة مراسلات Uniom"),
    "Uniom Notifications": ("اطلاع‌رسانی یونیوم", "إشعارات Uniom"),
    "Inbound Messages (Webhook)": ("پیام‌های ورودی (وب‌هوک)", "الرسائل الواردة (Webhook)"),
    "Connected Account": ("حساب متصل", "الحساب المتصل"),
    "Gateway": ("دروازه", "البوابة"),
    "Gateway URL": ("نشانی دروازه پیام", "عنوان البوابة"),
    "Uniom Gateway URL": ("نشانی دروازه یونیوم", "عنوان بوابة Uniom"),
    "Last Error": ("آخرین خطا", "آخر خطأ"),
    "Advanced": ("پیشرفته", "متقدم"),
    "Recipients": ("گیرندگان", "المستلمون"),
    "Message": ("پیام", "الرسالة"),
    "Customer": ("مشتری", "العميل"),
    "Direction": ("جهت", "الاتجاه"),
    "Status": ("وضعیت", "الحالة"),
    "Event": ("رویداد", "الحدث"),
    "Group By": ("گروه‌بندی بر اساس", "تجميع حسب"),
    "With Errors": ("دارای خطا", "مع أخطاء"),
    # ---- states / selections ------------------------------------------
    "Queued": ("در صف", "في الانتظار"),
    "Sent": ("ارسال شد", "تم الإرسال"),
    "Failed": ("ناموفق", "فشل"),
    "Canceled": ("لغو شد", "ملغى"),
    "Outgoing": ("خروجی", "صادر"),
    "Incoming": ("ورودی", "وارد"),
    # ---- triggers ------------------------------------------------------
    "Quotation Sent": ("ارسال پیش‌فاکتور", "إرسال عرض السعر"),
    "Sale Order Confirmed": ("تأیید سفارش فروش", "تأكيد أمر البيع"),
    "Invoice Posted": ("ثبت فاکتور", "ترحيل الفاتورة"),
    "Payment Received": ("دریافت پرداخت", "استلام الدفعة"),
    "Delivery Done": ("انجام تحویل", "إتمام التسليم"),
    "Product Published": ("انتشار محصول", "نشر المنتج"),
    "Product Price Changed": ("تغییر قیمت محصول", "تغيير سعر المنتج"),
    # ---- model descriptions -------------------------------------------
    "Uniom Connection": ("اتصال یونیوم", "اتصال Uniom"),
    "Uniom Message": ("پیام یونیوم", "رسالة Uniom"),
    "Uniom Message Template": ("قالب پیام یونیوم", "قالب رسالة Uniom"),
    "Uniom Automation Rule": ("قانون خودکار یونیوم", "قاعدة أتمتة Uniom"),
    "Uniom Send Wizard Recipient": ("گیرنده ویزارد ارسال یونیوم", "مستلم معالج إرسال Uniom"),
    # ---- fields --------------------------------------------------------
    "Uniom Chat ID": ("شناسه چت یونیوم", "معرف محادثة Uniom"),
    "No Uniom Messages": ("بدون پیام یونیوم", "بدون رسائل Uniom"),
    "API Key": ("کلید API", "مفتاح API"),
    "Company": ("شرکت", "الشركة"),
    "Language": ("زبان", "اللغة"),
    "Template Language": ("زبان قالب", "لغة القالب"),
    # ---- field labels surfaced by Odoo's automatic export ----------------
    "Account Details": ("جزئیات حساب", "تفاصيل الحساب"),
    "Administrator": ("مدیر", "مدير"),
    "Attachment": ("پیوست", "مرفق"),
    "Body": ("متن پیام", "نص الرسالة"),
    "Chat": ("گفتگو", "محادثة"),
    "Date Edited": ("تاریخ ویرایش", "تاريخ التعديل"),
    "Date Sent": ("تاریخ ارسال", "تاريخ الإرسال"),
    "document": ("سند", "مستند"),
    "Edit Count": ("تعداد ویرایش", "عدد التعديلات"),
    "Error Message": ("پیام خطا", "رسالة الخطأ"),
    "Next Attempt": ("تلاش بعدی", "المحاولة التالية"),
    "Partner": ("همکار", "الشريك"),
    "Partner Field": ("فیلد همکار", "حقل الشريك"),
    "Record Name": ("نام رکورد", "اسم السجل"),
    "Report Ref": ("ارجاع گزارش", "مرجع التقرير"),
    "Retry Count": ("تعداد تلاش مجدد", "عدد المحاولات"),
    "Rule": ("قانون", "قاعدة"),
    "Sequence": ("ترتیب", "التسلسل"),
    "State": ("وضعیت", "الحالة"),
    "Template": ("قالب", "قالب"),
    "Trigger": ("رویداد", "الحدث"),
    "Uniom Message Count": ("تعداد پیام یونیوم", "عدد رسائل Uniom"),
    "Uniom: process message queue": ("یونیوم: پردازش صف پیام", "Uniom: معالجة قائمة الرسائل"),
    "User": ("کاربر", "مستخدم"),
    "Webhook Registered": ("وب‌هوک ثبت شده", "Webhook مسجل"),
    "Webhook Secret": ("رمز وب‌هوک", "رمز Webhook"),
    "Webhook Url": ("نشانی وب‌هوک", "عنوان Webhook"),
    # ---- shorter field helps ---------------------------------------------
    "Account identity reported by the gateway (getMe).": (
        "هویت حساب گزارش‌شده توسط دروازه (getMe).",
        "هوية الحساب كما أبلغت عنها البوابة (getMe).",
    ),
    "Can send Uniom messages and read the message log.": (
        "ارسال پیام یونیوم و خواندن لاگ پیام‌ها.",
        "إرسال رسائل Uniom وقراءة سجل الرسائل.",
    ),
    "Destination: phone (+98912...), @channel or numeric id.": (
        "مقصد: شماره موبایل (+98912...)، @کانال یا شناسه عددی.",
        "الوجهة: هاتف (+98912...) أو @قناة أو معرف رقمي.",
    ),
    "Earliest moment the queue cron may retry this message.": (
        "اولین زمانی که کرون صف می‌تواند این پیام را دوباره ارسال کند.",
        "أقرب وقت يمكن فيه لكرون قائمة الانتظار إعادة إرسال هذه الرسالة.",
    ),
    "Exclude this contact from automated Uniom notifications.": (
        "این مخاطب از اطلاع‌رسانی خودکار یونیوم حذف شود.",
        "استبعاد جهة الاتصال هذه من إشعارات Uniom التلقائية.",
    ),
    "Leave empty to apply in every company.": (
        "خالی بگذارید تا در همه شرکت‌ها اعمال شود.",
        "اتركه فارغاً ليطبق في كل الشركات.",
    ),
    "Message id assigned by the messenger, needed to edit later.": (
        "شناسه پیام که پیام‌رسان تعیین می‌کند؛ برای ویرایش بعدی لازم است.",
        "معرف الرسالة الذي حدده تطبيق المراسلة، ويلزم للتعديل لاحقاً.",
    ),
    "Phone number (+989123456789), @channel or numeric chat id.": (
        "شماره موبایل (+989123456789)، @کانال یا شناسه چت عددی.",
        "رقم الهاتف (+989123456789) أو @قناة أو معرف محادثة رقمي.",
    ),
    "Send the document's standard PDF report with the message.": (
        "گزارش PDF استاندارد سند همراه پیام ارسال شود.",
        "إرسال تقرير PDF القياسي للمستند مع الرسالة.",
    ),
    # ---- demo data names ----------------------------------------------------
    "Bale — Sales Notifications (Demo)": ("بله — اطلاع‌رسانی فروش (نمایشی)", "بله — إشعارات المبيعات (تجريبي)"),
    "Rubika — Shop Channel (Demo)": ("روبیکا — کانال فروشگاه (نمایشی)", "روبيكا — قناة المتجر (تجريبي)"),
    # ---- conversations (messenger UI) ---------------------------------------
    "Conversations": ("گفتگوها", "المحادثات"),
    "Uniom Conversations": ("گفتگوهای یونیوم", "محادثات Uniom"),
    "Uniom Conversation": ("گفتگوی یونیوم", "محادثة Uniom"),
    "Thread": ("گفتگو", "سلسلة الرسائل"),
    "Reply": ("پاسخ", "الرد"),
    "Send Reply": ("ارسال پاسخ", "إرسال الرد"),
    "Draft reply": ("پاسخ پیش‌نویس", "مسودة الرد"),
    "Write a reply first.": ("ابتدا پاسخ بنویسید.", "اكتب رداً أولاً."),
    "Write a reply and press Send Reply...": ("پاسخ را بنویسید و دکمه ارسال پاسخ را بزنید...", "اكتب الرد ثم اضغط زر إرسال الرد..."),
    "Write a reply here and press Send Reply; it goes out through the connection of this conversation.": (
        "پاسخ را اینجا بنویسید و دکمه «ارسال پاسخ» را بزنید؛ از طریق اتصال همین گفتگو ارسال می‌شود.",
        "اكتب الرد هنا واضغط «إرسال الرد»؛ سيُرسل عبر اتصال هذه المحادثة.",
    ),
    "This conversation has an invalid destination: %s": (
        "مقصد این گفتگو نامعتبر است: %s",
        "وجهة هذه المحادثة غير صالحة: %s",
    ),
    "Conversation this message belongs to (kept for history).": (
        "گفتگویی که این پیام به آن تعلق دارد (برای تاریخچه).",
        "المحادثة التي تنتمي إليها هذه الرسالة (للأرشيف).",
    ),
    "Open Contact": ("باز کردن مخاطب", "فتح جهة الاتصال"),
    # ---- chat dashboard (OWL) ---------------------------------------------
    "Search conversations...": ("جستجوی گفتگوها...", "البحث في المحادثات..."),
    "No conversations yet.": ("هنوز گفتگویی وجود ندارد.", "لا توجد محادثات بعد."),
    "Select a conversation to start chatting": (
        "برای شروع گفتگو، یک گفتگو را انتخاب کنید",
        "اختر محادثة لبدء الدردشة",
    ),
    "Type a message": ("پیامی بنویسید", "اكتب رسالة"),
    "Manage": ("مدیریت", "إدارة"),
    "Last Message Date": ("تاریخ آخرین پیام", "تاريخ آخر رسالة"),
    "Last Message Preview": ("پیش‌نمایش آخرین پیام", "معاينة آخر رسالة"),
    "Message Count": ("تعداد پیام", "عدد الرسائل"),
    "Chat Session": ("گفتگو", "المحادثة"),
    "One conversation per connection and chat id.": (
        "یک گفتگو برای هر اتصال و شناسه چت.",
        "محادثة واحدة لكل اتصال ومعرف محادثة.",
    ),
    "%(sent)s reply(ies) sent, %(failed)s failed — see the message log for the reason; failed replies stay queued in the thread.": (
        "%(sent)s پاسخ ارسال شد، %(failed)s ناموفق — علت در لاگ پیام‌ها؛ پاسخ‌های ناموفق در گفتگو در صف می‌مانند.",
        "أُرسلت %(sent)s ردود وفشل %(failed)s — السبب في سجل الرسائل؛ الردود الفاشلة تبقى في قائمة الانتظار ضمن المحادثة.",
    ),
    "Create one in your Uniom dashboard: Account → API Keys (uniom_... — one key per messenger account).": (
        "در داشبورد یونیوم بسازید: حساب ← کلیدهای API (uniom_... — یک کلید برای هر حساب پیام‌رسان).",
        "أنشئه في لوحة تحكم Uniom: الحساب ← مفاتيح API ‏(uniom_... — مفتاح واحد لكل حساب مراسلة).",
    ),
    "Thread": ("گفتگو", "سلسلة الرسائل"),
    "No conversations yet": ("هنوز گفتگویی وجود ندارد", "لا محادثات بعد"),
    "Every incoming and outgoing message opens a thread here — reply straight from Odoo via Uniom. Connect your account to start.": (
        "هر پیام ورودی و خروجی اینجا یک گفتگو باز می‌کند — مستقیم از اودو از طریق یونیوم پاسخ دهید. برای شروع حساب خود را متصل کنید.",
        "كل رسالة واردة أو صادرة تفتح محادثة هنا — رُدّ مباشرةً من أودو عبر Uniom. اربط حسابك للبدء.",
    ),
    # ---- connect wizard -------------------------------------------------------
    "Connect Uniom Account": ("اتصال حساب یونیوم", "ربط حساب Uniom"),
    "Connect Account": ("اتصال حساب", "ربط الحساب"),
    "Connect": ("اتصال", "ربط"),
    "Connect your Uniom account": ("حساب یونیوم خود را متصل کنید", "اربط حساب Uniom الخاص بك"),
    "Add a messenger account with one API key — like logging in.": (
        "افزودن حساب پیام‌رسان فقط با یک کلید API — مثل ورود.",
        "إضافة حساب مراسلة بمفتاح API واحد — مثل تسجيل الدخول.",
    ),
    "Uniom Account": ("حساب یونیوم", "حساب Uniom"),
    "Label (optional)": ("برچسب (اختیاری)", "تسمية (اختياري)"),
    "How this connection should be listed in Odoo. Leave empty to use the account name reported by the gateway.": (
        "نام این اتصال در اودو. خالی بگذارید تا نام حساب گزارش‌شده توسط دروازه استفاده شود.",
        "اسم هذا الاتصال في أودو. اتركه فارغاً لاستخدام اسم الحساب الذي تبلغ عنه البوابة.",
    ),
    "Create an API key in your Uniom dashboard (Account → API Keys) and paste it below — one key per messenger account (Bale, Rubika, Eitaa, Soroush+, Telegram).": (
        "در داشبورد یونیوم یک کلید API بسازید (حساب ← کلیدهای API) و آن را در پایین بچسبانید — یک کلید برای هر حساب پیام‌رسان (بله، روبیکا، ایتا، سروش‌پلاس، تلگرام).",
        "أنشئ مفتاح API في لوحة تحكم Uniom ‏(الحساب ← مفاتيح API) والصقه أدناه — مفتاح واحد لكل حساب مراسلة (بله، روبيكا، إيتا، سروش+، تيليجرام).",
    ),
    "Could not connect to Uniom: %s\nCheck the API key and try again.": (
        "اتصال به یونیوم ممکن نشد: %s\nکلید API را بررسی کنید و دوباره تلاش کنید.",
        "تعذّر الاتصال بـ Uniom: %s\nتحقق من مفتاح API وحاول مجدداً.",
    ),
    "Applies to": ("برای", "ينطبق على"),
    "Fallback Template": ("قالب پیش‌فرض", "القالب الافتراضي"),
    "Translated Templates": ("قالب‌های ترجمه‌شده", "القوالب المترجمة"),
    "Also Send To": ("ارسال به‌علاوه به", "إرسال أيضاً إلى"),
    "Attach PDF Report": ("پیوست گزارش PDF", "إرفاق تقرير PDF"),
    "Attach PDF": ("پیوست PDF", "إرفاق PDF"),
    "Send Immediately": ("ارسال فوری", "إرسال فوري"),
    "Edit Previous Message": ("ویرایش پیام قبلی", "تعديل الرسالة السابقة"),
    "Apply on": ("اعمال روی", "التطبيق على"),
    "Create Contacts from Inbound Messages": (
        "ایجاد مخاطب از پیام‌های ورودی",
        "إنشاء جهات اتصال من الرسائل الواردة",
    ),
    "Uniom Notifications Enabled": ("اطلاع‌رسانی یونیوم فعال است", "إشعارات Uniom مفعّلة"),
    # ---- user messages --------------------------------------------------
    "%s message(s) sent.": ("‏%s پیام ارسال شد.", "تم إرسال %s رسالة."),
    "%s message(s) loaded.": ("‏%s پیام بارگذاری شد.", "تم تحميل %s رسالة."),
    "Messenger": ("پیام‌رسان", "المراسلة"),
    "Which messenger this API key belongs to.": (
        "این کلید API متعلق به کدام پیام‌رسان است.",
        "إلى أي مراسلة ينتمي هذا المفتاح.",
    ),
    "Which messenger this API key belongs to (pick it when you connect: the gateway does not report it via getMe).": (
        "این کلید API متعلق به کدام پیام‌رسان است (هنگام اتصال انتخاب کنید: دروازه آن را از طریق getMe گزارش نمی‌دهد).",
        "إلى أي مراسلة ينتمي هذا المفتاح (اختره عند الاتصال: لا تبلغ عنه البوابة عبر getMe).",
    ),
    " %s failed and were queued or marked failed (see the log).": (
        "‏%s ناموفق بود و در صف قرار گرفت یا ناموفق علامت خورد (لاگ را ببینید).",
        " فشل %s وأُضيف إلى قائمة الانتظار أو عُلّم كفاشل (راجع السجل).",
    ),
    "Hello, here is an update about %s.": ("سلام، این یک به‌روزرسانی درباره %s است.", "مرحباً، إليك تحديثاً بشأن %s."),
    "Invalid destination '%s'. Use +989123456789, @channel or a numeric id.": (
        "مقصد نامعتبر «%s». از +989123456789، @کانال یا شناسه عددی استفاده کنید.",
        "وجهة غير صالحة «%s». استخدم +989123456789 أو @قناة أو معرّفاً رقمياً.",
    ),
    "Message sent via Uniom (%s).": ("پیام از طریق یونیوم ارسال شد (%s).", "تم إرسال الرسالة عبر Uniom ‏(%s)."),
    "Delivery outcome unknown (gateway timeout). Not retried to avoid duplicates, please verify on the messenger.": (
        "نتیجه تحویل نامشخص است (تایم‌اوت دروازه). برای جلوگیری از تکرار، دوباره ارسال نشد؛ لطفاً در پیام‌رسان بررسی کنید.",
        "نتيجة التسليم غير معروفة (انتهاء مهلة البوابة). لم تُكرَّر المحاولة تجنباً للتكرار؛ يرجى التحقق في تطبيق المراسلة.",
    ),
    "Retry %(n)s/%(max)s scheduled in %(mins)s min: %(err)s": (
        "تلاش مجدد %(n)s/%(max)s تا %(mins)s دقیقه دیگر: %(err)s",
        "إعادة المحاولة %(n)s/%(max)s بعد %(mins)s دقيقة: %(err)s",
    ),
    "Uniom message failed permanently: %s": ("پیام یونیوم برای همیشه ناموفق شد: %s", "فشلت رسالة Uniom نهائياً: %s"),
    "Uniom message to %s": ("پیام یونیوم به %s", "رسالة Uniom إلى %s"),
    "Uniom error %(code)s: %(description)s": ("خطای یونیوم %(code)s: %(description)s", "خطأ Uniom ‏%(code)s: %(description)s"),
    "Network error while contacting Uniom: %s": ("خطای شبکه در تماس با یونیوم: %s", "خطأ في الشبكة أثناء الاتصال بـ Uniom: %s"),
    "Connected as %(account)s via %(url)s": ("به‌عنوان %(account)s از طریق %(url)s متصل شد", "تم الاتصال باسم %(account)s عبر %(url)s"),
    "Account #%s": ("حساب #%s", "حساب #%s"),
    "Webhook registered.": ("وب‌هوک ثبت شد.", "تم تسجيل Webhook."),
    "Invalid gateway URL": ("نشانی دروازه نامعتبر", "عنوان البوابة غير صالح"),
    "The connection '%s' has no API key.": ("اتصال «%s» کلید API ندارد.", "الاتصال «%s» لا يحتوي على مفتاح API."),
    "The Uniom API key must start with '%(prefix)s' — copy it exactly as shown in your Uniom dashboard.": (
        "کلید API یونیوم باید با «%(prefix)s» شروع شود — آن را دقیقاً مطابق داشبورد یونیوم کپی کنید.",
        "يجب أن يبدأ مفتاح Uniom API بـ «%(prefix)s» — انسخه تماماً كما يظهر في لوحة تحكم Uniom.",
    ),
    "Uniom contact %s": ("مخاطب یونیوم %s", "جهة اتصال Uniom ‏%s"),
    "Uniom answered with a redirect (HTTP %s) which is refused.": (
        "یونیوم پاسخ تغییر مسیر (HTTP %s) داد که رد شد.",
        "ردّ Uniom بإعادة توجيه (HTTP %s) وقد رُفضت.",
    ),
    "Uniom answered with invalid JSON (HTTP %s).": ("یونیوم JSON نامعتبر (HTTP %s) پاسخ داد.", "ردّ Uniom بـ JSON غير صالح (HTTP %s)."),
    "Set the 'web.base.url' system parameter to your Odoo base URL first.": (
        "ابتدا پارامتر سیستم web.base.url را روی نشانی اصلی اودو تنظیم کنید.",
        "عيّن أولاً معامل النظام web.base.url على العنوان الأساسي لأودو.",
    ),
    "Create at least one record of %s first.": ("ابتدا حداقل یک رکورد از %s ایجاد کنید.", "أنشئ أولاً سجلاً واحداً على الأقل من %s."),
    "No record of type %(model)s exists yet to test this rule.": (
        "هنوز رکوردی از نوع %(model)s برای آزمایش این قانون وجود ندارد.",
        "لا يوجد بعد سجل من نوع %(model)s لاختبار هذه القاعدة.",
    ),
    "Template '%(template)s' applies to %(model)s but got a %(other)s record.": (
        "قالب «%(template)s» برای %(model)s است اما رکورد %(other)s داده شد.",
        "القالب «%(template)s» مخصص لـ %(model)s لكنه استقبل سجلاً من %(other)s.",
    ),
    "Uniom template preview": ("پیش‌نمایش قالب یونیوم", "معاينة قالب Uniom"),
    "Unknown error": ("خطای ناشناخته", "خطأ غير معروف"),
    # ---- URL validator ---------------------------------------------------
    "Only http:// and https:// URLs are allowed, got: %s": (
        "فقط نشانی‌های http:// و https:// مجاز هستند؛ دریافت شد: %s",
        "يُسمح فقط بعناوين http:// و https://؛ تم استلام: %s",
    ),
    "The URL %s has no host.": ("نشانی %s میزبان ندارد.", "العنوان %s بلا مضيف."),
    "Host %s is not allowed: private or local hosts are refused.": (
        "میزبان %s مجاز نیست: میزبان‌های محلی و خصوصی رد می‌شوند.",
        "المضيف %s غير مسموح: تُرفض المضيفات المحلية والخاصة.",
    ),
    "IP address %s is not allowed: only public addresses are accepted.": (
        "نشانی IP %s مجاز نیست: فقط نشانی‌های عمومی پذیرفته می‌شوند.",
        "عنوان IP ‏%s غير مسموح: تُقبل العناوين العامة فقط.",
    ),
    "Host %s resolves to a private or reserved address and is refused.": (
        "میزبان %s به نشانی خصوصی یا رزروشده اشاره می‌کند و رد می‌شود.",
        "المضيف %s يشير إلى عنوان خاص أو محجوز وقد رُفض.",
    ),
    "empty": ("خالی", "فارغ"),
    # ---- default rule names (data) ---------------------------------------
    "Notify customer: quotation sent": ("اطلاع به مشتری: ارسال پیش‌فاکتور", "إشعار العميل: إرسال عرض السعر"),
    "Notify customer: order confirmed": ("اطلاع به مشتری: تأیید سفارش", "إشعار العميل: تأكيد أمر البيع"),
    "Notify customer: invoice posted (with PDF)": ("اطلاع به مشتری: ثبت فاکتور (با PDF)", "إشعار العميل: ترحيل الفاتورة (مع PDF)"),
    "Notify customer: payment received": ("اطلاع به مشتری: دریافت پرداخت", "إشعار العميل: استلام الدفعة"),
    "Notify customer: delivery done": ("اطلاع به مشتری: انجام تحویل", "إشعار العميل: إتمام التسليم"),
    "Announce new product in channel": ("اعلام محصول جدید در کانال", "الإعلان عن منتج جديد في القناة"),
    "Update price post in channel": ("به‌روزرسانی پست قیمت در کانال", "تحديث منشور السعر في القناة"),
    # ---- default template names (data) ------------------------------------
    "Quotation Sent (English)": ("ارسال پیش‌فاکتور (انگلیسی)", "إرسال عرض السعر (الإنجليزية)"),
    "Order Confirmed (English)": ("تأیید سفارش (انگلیسی)", "تأكيد الطلب (الإنجليزية)"),
    "Invoice Posted (English)": ("ثبت فاکتور (انگلیسی)", "ترحيل الفاتورة (الإنجليزية)"),
    "Payment Received (English)": ("دریافت پرداخت (انگلیسی)", "استلام الدفعة (الإنجليزية)"),
    "Delivery Done (English)": ("انجام تحویل (انگلیسی)", "إتمام التسليم (الإنجليزية)"),
    "Product Published (English)": ("انتشار محصول (انگلیسی)", "نشر المنتج (الإنجليزية)"),
    "Price Updated (English)": ("به‌روزرسانی قیمت (انگلیسی)", "تحديث السعر (الإنجليزية)"),
    "Order Confirmed (Persian)": ("تأیید سفارش (فارسی)", "تأكيد الطلب (الفارسية)"),
    "Invoice Posted (Persian)": ("ثبت فاکتور (فارسی)", "ترحيل الفاتورة (الفارسية)"),
    "Delivery Done (Persian)": ("انجام تحویل (فارسی)", "إتمام التسليم (الفارسية)"),
    "Payment Received (Persian)": ("دریافت پرداخت (فارسی)", "استلام الدفعة (الفارسية)"),
    "Price Updated (Persian)": ("به‌روزرسانی قیمت (فارسی)", "تحديث السعر (الفارسية)"),
    "Order Confirmed (Arabic)": ("تأیید سفارش (عربی)", "تأكيد الطلب (العربية)"),
    "Invoice Posted (Arabic)": ("ثبت فاکتور (عربی)", "ترحيل الفاتورة (العربية)"),
    "Delivery Done (Arabic)": ("انجام تحویل (عربی)", "إتمام التسليم (العربية)"),
    "Price Updated (Arabic)": ("به‌روزرسانی قیمت (عربی)", "تحديث السعر (العربية)"),
    # ---- record reference selection -------------------------------------
    "Contact": ("مخاطب", "جهة الاتصال"),
    "Sale Order": ("سفارش فروش", "أمر البيع"),
    "Invoice": ("فاکتور", "الفاتورة"),
    "Payment": ("پرداخت", "الدفعة"),
    "Transfer": ("حواله انبار", "التحويل"),
    "Product": ("محصول", "المنتج"),
    # ---- messenger dashboard (OWL client action) -----------------------
    "All connections": ("همه اتصال‌ها", "كل الاتصالات"),
    "Refresh": ("تازه‌سازی", "تحديث"),
    "New conversation": ("گفتگوی جدید", "محادثة جديدة"),
    "Manage connections": ("مدیریت اتصال‌ها", "إدارة الاتصالات"),
    "Connect your messenger account and the conversations will show up here.": (
        "حساب پیام‌رسان خود را متصل کنید تا گفتگوها اینجا نمایش داده شوند.",
        "اربط حساب المراسلة وستظهر المحادثات هنا.",
    ),
    "No conversations match your search or filters.": (
        "گفتگویی با جستجو یا فیلترهای شما مطابقت ندارد.",
        "لا توجد محادثات تطابق بحثك أو عوامل التصفية.",
    ),
    "Loading conversations...": ("در حال بارگذاری گفتگوها...", "جارٍ تحميل المحادثات..."),
    "Some messages could not be sent": ("برخی پیام‌ها ارسال نشدند", "تعذّر إرسال بعض الرسائل"),
    "Select a conversation to start chatting.": (
        "برای شروع گفتگو یک مکالمه را انتخاب کنید.",
        "اختر محادثة لبدء الدردشة.",
    ),
    "No messages yet. Say hello!": ("هنوز پیامی نیست. سلام کنید!", "لا رسائل بعد. قل مرحباً!"),
    "Load older messages": ("بارگذاری پیام‌های قدیمی‌تر", "تحميل الرسائل الأقدم"),
    "Open contact": ("باز کردن مخاطب", "فتح جهة الاتصال"),
    "Sync presence": ("همگام‌سازی وضعیت حضور", "مزامنة الحضور"),
    "Sync": ("همگام‌سازی", "مزامنة"),
    "Type a message": ("پیام بنویسید", "اكتب رسالة"),
    "Sending...": ("در حال ارسال...", "جارٍ الإرسال..."),
    "Attach a file": ("پیوست فایل", "إرفاق ملف"),
    "Uploading...": ("در حال بارگذاری...", "جارٍ الرفع..."),
    "Retry": ("تلاش مجدد", "إعادة المحاولة"),
    "Queued": ("در صف", "في الانتظار"),
    "Failed": ("ناموفق", "فشل"),
    "Canceled": ("لغو شده", "ملغى"),
    "Today": ("امروز", "اليوم"),
    "Yesterday": ("دیروز", "أمس"),
    "Online": ("آنلاین", "متصل"),
    "Offline": ("آفلاین", "غير متصل"),
    "Presence unavailable": ("وضعیت حضور در دسترس نیست", "الحضور غير متاح"),
    "Last seen recently": ("آخرین بازدید اخیراً", "شوهد مؤخراً"),
    "Last seen within a week": ("آخرین بازدید در هفته گذشته", "شوهد خلال أسبوع"),
    "Last seen within a month": ("آخرین بازدید در ماه گذشته", "شوهد خلال شهر"),
    "Last seen a long time ago": ("آخرین بازدید خیلی وقت پیش", "شوهد منذ زمن طويل"),
    "Last seen %s": ("آخرین بازدید %s", "شوهد %s"),
    "Presence updated %s": ("حضور به‌روزرسانی شد %s", "حُدّث الحضور %s"),
    "Photo": ("عکس", "صورة"),
    "Document": ("سند", "مستند"),
    "Video": ("ویدئو", "فيديو"),
    "Audio": ("صوت", "صوت"),
    "Voice message": ("پیام صوتی", "رسالة صوتية"),
    "Sticker": ("استیکر", "ملصق"),
    "Location": ("موقعیت", "الموقع"),
    "Contact": ("مخاطب", "جهة اتصال"),
    "Poll": ("نظرسنجی", "استطلاع"),
    "Text message": ("پیام متنی", "رسالة نصية"),
    "Message": ("پیام", "رسالة"),
    "Message not sent": ("پیام ارسال نشد", "تعذّر إرسال الرسالة"),
    "Attachment not sent": ("پیوست ارسال نشد", "تعذّر إرسال المرفق"),
    "The message could not be sent.": ("پیام ارسال نشد.", "تعذّر إرسال الرسالة."),
    "The attachment could not be sent.": ("پیوست ارسال نشد.", "تعذّر إرسال المرفق."),
    "The file could not be uploaded.": ("فایل بارگذاری نشد.", "تعذّر رفع الملف."),
    "The message is queued and will be retried automatically.": (
        "پیام در صف قرار گرفت و به‌صورت خودکار تلاش مجدد می‌شود.",
        "الرسالة في الانتظار وستُعاد تلقائياً.",
    ),
    "The requested conversation could not be found.": (
        "گفتگوی درخواستی پیدا نشد.",
        "تعذّر العثور على المحادثة المطلوبة.",
    ),
    "This conversation is not linked to a contact yet.": (
        "این گفتگو هنوز به مخاطبی پیوند نشده است.",
        "هذه المحادثة غير مرتبطة بجهة اتصال بعد.",
    ),
    "Something went wrong. Please try again.": (
        "مشکلی پیش آمد. لطفاً دوباره تلاش کنید.",
        "حدث خطأ. حاول مرة أخرى.",
    ),
    "Private": ("خصوصی", "خاص"),
    "Group": ("گروه", "مجموعة"),
    "Supergroup": ("سوپرگروه", "مجموعة خارقة"),
    "Channel": ("کانال", "قناة"),
    "Chat": ("گفتگو", "محادثة"),
    "Attachment": ("پیوست", "مرفق"),
    "Upload failed (HTTP %s).": ("بارگذاری ناموفق بود (HTTP %s).", "فشل الرفع (HTTP %s)."),
    "%(size)s %(unit)s": ("%(size)s %(unit)s", "%(size)s %(unit)s"),
    "Bale": ("بله", "بله"),
    "Rubika": ("روبیکا", "روبيكا"),
    "Eitaa": ("ایتا", "إيتا"),
    "Soroush+": ("سروش‌پلاس", "سروش+"),
    "Telegram": ("تلگرام", "تيليجرام"),
    "Other": ("سایر", "أخرى"),
    # ---- connection / polling / presence ------------------------------
    "Sync Conversations": ("همگام‌سازی گفتگوها", "مزامنة المحادثات"),
    "Webhook Status": ("وضعیت وب‌هوک", "حالة Webhook"),
    "Start Polling": ("شروع دریافت دوره‌ای", "بدء الاستطلاع"),
    "Stop Polling": ("توقف دریافت دوره‌ای", "إيقاف الاستطلاع"),
    "Mark Read": ("علامت خوانده‌شده", "تعليم كمقروء"),
    "Sync Presence": ("همگام‌سازی حضور", "مزامنة الحضور"),
    "Load History": ("بارگذاری سابقه", "تحميل السجل"),
    "Polling enabled: incoming updates are fetched by the cron.": (
        "دریافت دوره‌ای فعال شد: به‌روزرسانی‌های ورودی توسط کرون دریافت می‌شوند.",
        "تم تفعيل الاستطلاع: تُجلب التحديثات الواردة عبر المهمة المجدولة.",
    ),
    "Polling stopped. Register the webhook when your Odoo URL is reachable.": (
        "دریافت دوره‌ای متوقف شد. وقتی نشانی اودو شما در دسترس بود وب‌هوک را ثبت کنید.",
        "توقف الاستطلاع. سجّل الـ Webhook عندما يصبح عنوان Odoo متاحاً.",
    ),
    "Webhook status refreshed.": ("وضعیت وب‌هوک تازه‌سازی شد.", "حُدّثت حالة الـ Webhook."),
    "%s conversations synchronized.": ("%s گفتگو همگام‌سازی شد.", "زُامنت %s محادثة."),
    "Receive Messages Via": ("دریافت پیام‌ها از طریق", "استلام الرسائل عبر"),
    "Webhook (instant)": ("وب‌هوک (فوری)", "Webhook (فوري)"),
    "Polling (works everywhere)": ("دریافت دوره‌ای (همه‌جا کار می‌کند)", "الاستطلاع (يعمل في كل مكان)"),
    "Your Odoo URL is not publicly reachable, so the gateway cannot push messages to it. Polling is recommended here.": (
        "نشانی اودوی شما عمومی نیست، پس دروازه نمی‌تواند پیام‌ها را به آن ارسال کند. دریافت دوره‌ای اینجا توصیه می‌شود.",
        "عنوان Odoo ليس عاماً، فلا تستطيع البوابة دفع الرسائل إليه. يُنصح بالاستطلاع هنا.",
    ),
    "Webhook registration failed (%s); polling was started instead.": (
        "ثبت وب‌هوک ناموفق بود (%s)؛ در عوض دریافت دوره‌ای شروع شد.",
        "فشل تسجيل الـ Webhook ‏(%s)؛ وبدأ الاستطلاع بدلاً منه.",
    ),
    "Polling could not be started: %s": ("دریافت دوره‌ای شروع نشد: %s", "تعذّر بدء الاستطلاع: %s"),
    "Conversations could not be synchronized yet: %s": (
        "گفتگوها هنوز همگام‌سازی نشدند: %s",
        "تعذّرت مزامنة المحادثات بعد: %s",
    ),
    "Document: %(name)s": ("سند: %(name)s", "مستند: %(name)s"),
    "Audio: %(name)s": ("صوت: %(name)s", "صوت: %(name)s"),
    "Location: %(lat)s, %(lon)s": ("موقعیت: %(lat)s، %(lon)s", "الموقع: %(lat)s، %(lon)s"),
    "Contact: %(name)s %(phone)s": ("مخاطب: %(name)s %(phone)s", "جهة الاتصال: %(name)s %(phone)s"),
    "Poll: %(question)s": ("نظرسنجی: %(question)s", "استطلاع: %(question)s"),
    "Unsupported message": ("پیام پشتیبانی‌نشده", "رسالة غير مدعومة"),
    "File is larger than the %(mb)s MB limit.": (
        "فایل از سقف %(mb)s مگابایت بزرگ‌تر است.",
        "الملف أكبر من حد %(mb)s م.ب.",
    ),
    "Network error while downloading a file: %s": (
        "خطای شبکه هنگام دانلود فایل: %s",
        "خطأ شبكة أثناء تنزيل ملف: %s",
    ),
    "File download failed (HTTP %s).": ("دانلود فایل ناموفق بود (HTTP %s).", "فشل تنزيل الملف (HTTP %s)."),
    "Incoming %(kind)s message": ("پیام %(kind)s ورودی", "رسالة %(kind)s واردة"),
    "Open in Uniom Conversations": ("باز کردن در گفتگوهای یونیوم", "فتح في محادثات Uniom"),
    "Uniom delivery failed: %(name)s": (
        "تحویل یونیوم ناموفق بود: %(name)s",
        "فشل تسليم Uniom: %(name)s",
    ),
    "The attachment has no content.": ("پیوست محتوایی ندارد.", "المرفق بلا محتوى."),
    "Invalid attachment.": ("پیوست نامعتبر.", "مرفق غير صالح."),
    "Attachment not found.": ("پیوست پیدا نشد.", "تعذّر العثور على المرفق."),
    "Write a reply first.": ("اول پاسخی بنویسید.", "اكتب رداً أولاً."),
    "Inbound Messages": ("پیام‌های ورودی", "الرسائل الواردة"),
    "Webhook": ("وب‌هوک", "Webhook"),
    "Polling (getUpdates)": ("دریافت دوره‌ای (getUpdates)", "الاستطلاع (getUpdates)"),
    "Unread": ("خوانده‌نشده", "غير مقروء"),
    # ---- auto field labels / helps (new fields) ------------------------
    "Active": ("فعال", "نشط"),
    "Active Model": ("مدل فعال", "النموذج النشط"),
    "Api Key": ("کلید API", "مفتاح API"),
    "Attachments": ("پیوست‌ها", "المرفقات"),
    "Avatar Url": ("نشانی آواتار", "رابط الصورة"),
    "Base Url Is Public": ("نشانی پایه عمومی است", "العنوان الأساسي عام"),
    "Chat Type": ("نوع گفتگو", "نوع المحادثة"),
    "Chat kind reported by the messenger.": (
        "نوع گفتگو طبق گزارش پیام‌رسان.",
        "نوع المحادثة كما أبلغت عنه المراسلة.",
    ),
    "Connected as %s": ("متصل به‌عنوان %s", "متصل باسم %s"),
    "Created by": ("ایجادکننده", "أنشأه"),
    "Created on": ("تاریخ ایجاد", "تاريخ الإنشاء"),
    "Last Updated by": ("آخرین به‌روزرسان", "آخر تحديث بواسطة"),
    "Last Updated on": ("آخرین به‌روزرسانی", "آخر تحديث في"),
    "ID": ("شناسه", "المعرف"),
    "Display Label": ("برچسب نمایشی", "التسمية المعروضة"),
    "Display Name": ("نام نمایشی", "الاسم المعروض"),
    "Gateway update id, used to ignore re-deliveries.": (
        "شناسه به‌روزرسانی دروازه؛ برای نادیده گرفتن ارسال‌های تکراری.",
        "معرف تحديث البوابة، لتجاهل إعادة التسليم.",
    ),
    "Inbound Mode": ("حالت ورودی", "وضع الاستلام"),
    "Incoming messages start unread and are marked read when the conversation is opened or the messenger confirms the read receipt.": (
        "پیام‌های ورودی خوانده‌نشده شروع می‌شوند و با باز شدن گفتگو یا تأیید رسید خواندن علامت خوانده می‌گیرند.",
        "تبدأ الرسائل الواردة غير مقروءة وتُعلَّم مقروءة عند فتح المحادثة أو تأكيد إيصال القراءة.",
    ),
    "Instead of sending a new message, edit the one this rule sent earlier for the same record (ideal for price updates in a channel).": (
        "به‌جای ارسال پیام جدید، پیامی را که این قانون قبلاً برای همان رکورد فرستاده ویرایش کن (مناسب به‌روزرسانی قیمت در کانال).",
        "بدل إرسال رسالة جديدة، حرّر الرسالة التي أرسلتها هذه القاعدة سابقاً للسجل نفسه (مثالي لتحديث الأسعار في قناة).",
    ),
    "Is Read": ("خوانده شده", "مقروء"),
    "JSON list of update types the polling cron subscribes to.": (
        "فهرست JSON انواع به‌روزرسانی که کرون دریافت مشترک آن‌هاست.",
        "قائمة JSON بأنواع التحديثات التي تشترك فيها مهمة الاستطلاع.",
    ),
    "Kind of content carried by this message.": (
        "نوع محتوای این پیام.",
        "نوع المحتوى الذي تحمله هذه الرسالة.",
    ),
    "Last Dialog Sync At": ("آخرین همگام‌سازی گفتگوها", "آخر مزامنة للمحادثات"),
    "Last Message Direction": ("جهت آخرین پیام", "اتجاه آخر رسالة"),
    "Last Message Kind": ("نوع آخرین پیام", "نوع آخر رسالة"),
    "Last Message State": ("وضعیت آخرین پیام", "حالة آخر رسالة"),
    "Last Poll At": ("آخرین دریافت", "آخر استطلاع"),
    "Last Poll Error": ("خطای آخرین دریافت", "خطأ آخر استطلاع"),
    "Last Seen At": ("آخرین بازدید در", "آخر مشاهدة في"),
    "Last Seen Is Exact": ("آخرین بازدید دقیق است", "آخر مشاهدة دقيقة"),
    "Last Seen Label": ("برچسب آخرین بازدید", "تسمية آخر مشاهدة"),
    "Last Webhook At": ("آخرین وب‌هوک در", "آخر Webhook في"),
    "Message Kind": ("نوع پیام", "نوع الرسالة"),
    "Messenger Photo Url": ("نشانی عکس پیام‌رسان", "رابط صورة المراسلة"),
    "Messenger Title": ("عنوان پیام‌رسان", "عنوان المراسلة"),
    "Messenger Username": ("نام کاربری پیام‌رسان", "اسم مستخدم المراسلة"),
    "Messenger this API key belongs to, as reported by the gateway.": (
        "پیام‌رسانی که این کلید API به آن تعلق دارد، طبق گزارش دروازه.",
        "المراسلة التي ينتمي إليها هذا المفتاح كما أبلغت البوابة.",
    ),
    "Model": ("مدل", "النموذج"),
    "Name": ("نام", "الاسم"),
    "Next getUpdates offset: the first update id the gateway may return.": (
        "آفست بعدی getUpdates: اولین شناسه به‌روزرسانی که دروازه ممکن است برگرداند.",
        "إزاحة getUpdates التالية: أول معرف تحديث قد ترجعه البوابة.",
    ),
    "Platform": ("پلتفرم", "المنصة"),
    "Poll Allowed Updates": ("به‌روزرسانی‌های مجاز دریافت", "تحديثات الاستطلاع المسموحة"),
    "Poll Backoff Until": ("توقف دریافت تا", "إيقاف الاستطلاع حتى"),
    "Poll Offset": ("آفست دریافت", "إزاحة الاستطلاع"),
    "Polling": ("دریافت دوره‌ای", "الاستطلاع"),
    "Polling is paused until this moment (e.g. while a webhook is still registered on the gateway).": (
        "دریافت دوره‌ای تا این لحظه متوقف است (مثلاً تا وقتی وب‌هوکی روی دروازه ثبت است).",
        "الاستطلاع متوقف مؤقتاً حتى هذه اللحظة (مثلاً أثناء تسجيل Webhook على البوابة).",
    ),
    "Presence Updated At": ("به‌روزرسانی حضور در", "تحديث الحضور في"),
    "Record Ref": ("ارجاع رکورد", "مرجع السجل"),
    "Record Res": ("رکورد", "السجل"),
    "Record Res Model": ("مدل رکورد", "نموذج السجل"),
    "Rendering Model": ("مدل رندر", "نموذج العرض"),
    "This gateway update was already stored for this connection.": (
        "این به‌روزرسانی دروازه قبلاً برای این اتصال ذخیره شده است.",
        "حُفظ تحديث البوابة هذا سابقاً لهذا الاتصال.",
    ),
    "Title (or full name) reported by the messenger.": (
        "عنوان (یا نام کامل) طبق گزارش پیام‌رسان.",
        "العنوان (أو الاسم الكامل) كما أبلغت المراسلة.",
    ),
    "Trigger Model": ("مدل ماشه", "نموذج المشغّل"),
    "Uniom": ("یونیوم", "Uniom"),
    "Uniom Chat Count": ("تعداد گفتگوهای یونیوم", "عدد محادثات Uniom"),
    "Uniom Update": ("به‌روزرسانی یونیوم", "تحديث Uniom"),
    "Uniom: poll inbound updates": ("یونیوم: دریافت دوره‌ای به‌روزرسانی‌های ورودی", "Uniom: استطلاع التحديثات الواردة"),
    "Uniom: sync chat presence": ("یونیوم: همگام‌سازی حضور گفتگو", "Uniom: مزامنة حضور المحادثات"),
    "Unknown": ("ناشناخته", "غير معروف"),
    "Unread Count": ("تعداد خوانده‌نشده", "عدد غير المقروء"),
    "Unsupported": ("پشتیبانی‌نشده", "غير مدعوم"),
    "Verbatim last-activity label from the gateway.": (
        "برچسب آخرین فعالیت از دروازه، بدون تغییر.",
        "تسمية آخر نشاط من البوابة حرفياً.",
    ),
    "Webhook Last Error": ("آخرین خطای وب‌هوک", "آخر خطأ Webhook"),
    "Webhook Pending Count": ("تعداد در انتظار وب‌هوک", "عدد معلق Webhook"),
    "Webhook requires a publicly reachable Odoo; polling works behind NAT and is driven by the getUpdates cron.": (
        "وب‌هوک به اودوی عمومی نیاز دارد؛ دریافت دوره‌ای پشت NAT کار می‌کند و توسط کرون getUpdates اجرا می‌شود.",
        "يتطلب الـ Webhook عنوان Odoo عاماً؛ أما الاستطلاع فيعمل خلف NAT وتديره مهمة getUpdates.",
    ),
    "Wizard": ("جادوگر", "المعالج"),
    "Text": ("متن", "نص"),
    "contact": ("مخاطب", "جهة اتصال"),
    "file": ("فایل", "ملف"),
    "poll": ("نظرسنجی", "استطلاع"),
    # ---- link wizard + Discuss bridge (round 2) ------------------------
    "Link Messenger Account": ("پیوند حساب پیام‌رسان", "ربط حساب مراسلة"),
    "Sign In": ("ورود", "تسجيل الدخول"),
    "Verification": ("تأیید", "التحقق"),
    "Verification Code": ("کد تأیید", "رمز التحقق"),
    "Verification Mode": ("حالت تأیید", "وضع التحقق"),
    "Two-Step Password": ("رمز دومرحله‌ای", "كلمة مرور التحقق بخطوتين"),
    "Bot Token": ("توکن ربات", "رمز البوت"),
    "Step": ("مرحله", "الخطوة"),
    "Done": ("تمام شد", "تم"),
    "Uniom Phone": ("تلفن یونیوم", "هاتف Uniom"),
    "Messenger Phone": ("تلفن پیام‌رسان", "هاتف المراسلة"),
    "API Key Name": ("نام کلید API", "اسم مفتاح API"),
    "Link Credential": ("اعتبار پیوند", "بيانات الربط"),
    "Link Session": ("نشست پیوند", "جلسة الربط"),
    "Link Message": ("پیام پیوند", "رسالة الربط"),
    "Link Phone Display": ("نمایش تلفن پیوند", "عرض هاتف الربط"),
    "Created Connection": ("اتصال ایجادشده", "الاتصال المُنشأ"),
    "Credential": ("اعتبار", "بيانات الاعتماد"),
    "Credential Phone": ("تلفن اعتبار", "هاتف الاعتماد"),
    "Credential Status": ("وضعیت اعتبار", "حالة الاعتماد"),
    "Discuss Channel": ("کانال گفتگو", "قناة النقاش"),
    "Mgmt Cookies": ("کوکی‌های مدیریتی", "ملفات تعريف الإدارة"),
    "Mgmt Csrf": ("توکن CSRF مدیریتی", "رمز CSRF الإداري"),
    "Mgmt Signed In": ("وارد سیستم مدیریتی شده", "مسجّل في الإدارة"),
    "Otp Client": ("کلاینت OTP", "عميل OTP"),
    "Link contact": ("پیوند مخاطب", "ربط جهة الاتصال"),
    "Open in Discuss": ("باز کردن در Discuss", "فتح في Discuss"),
    "unknown error": ("خطای ناشناخته", "خطأ غير معروف"),
    "Uniom %(platform)s": ("یونیوم %(platform)s", "Uniom %(platform)s"),
    "Messenger account linked and API key created.": (
        "حساب پیام‌رسان پیوند شد و کلید API ساخته شد.",
        "تم ربط حساب المراسلة وإنشاء مفتاح API.",
    ),
    "Choose a messenger to link.": ("پیام‌رسانی برای پیوند انتخاب کنید.", "اختر مراسلة لربطها."),
    "Sign in to Uniom first.": ("اول وارد یونیوم شوید.", "سجّل الدخول إلى Uniom أولاً."),
    "You are already signed in to Uniom.": ("شما قبلاً وارد یونیوم شده‌اید.", "أنت مسجّل في Uniom مسبقاً."),
    "Signed in. Choose the messenger account to link.": (
        "وارد شدید. حساب پیام‌رسان برای پیوند را انتخاب کنید.",
        "تم تسجيل الدخول. اختر حساب المراسلة لربطه.",
    ),
    "There is no Uniom sign-in code to resend.": (
        "کد ورود یونیومی برای ارسال مجدد وجود ندارد.",
        "لا يوجد رمز دخول Uniom لإعادة إرساله.",
    ),
    "Start linking the messenger account first.": (
        "اول پیوند حساب پیام‌رسان را شروع کنید.",
        "ابدأ ربط حساب المراسلة أولاً.",
    ),
    "Link a messenger account first.": (
        "اول یک حساب پیام‌رسان پیوند کنید.",
        "اربط حساب مراسلة أولاً.",
    ),
    "Give the API key a name.": ("برای کلید API نامی بگذارید.", "أعطِ مفتاح API اسماً."),
    "Enter a valid phone number in international format, for example +989123456789.": (
        "شماره تلفن معتبر با قالب بین‌المللی وارد کنید، مثلاً +989123456789.",
        "أدخل رقم هاتف صالحاً بالصيغة الدولية، مثل +989123456789.",
    ),
    "Enter the 4 to 8 digit verification code.": (
        "کد تأیید ۴ تا ۸ رقمی را وارد کنید.",
        "أدخل رمز التحقق المكون من 4 إلى 8 أرقام.",
    ),
    "Enter the bot token.": ("توکن ربات را وارد کنید.", "أدخل رمز البوت."),
    "Enter your two-step password.": ("رمز دومرحله‌ای خود را وارد کنید.", "أدخل كلمة مرور التحقق بخطوتين."),
    "The password was not accepted. Please try again.": (
        "رمز پذیرفته نشد. لطفاً دوباره تلاش کنید.",
        "لم تُقبل كلمة المرور. حاول مرة أخرى.",
    ),
    "Paste the token issued by the messenger's bot father.": (
        "توکن صادرشده توسط بات‌فادر پیام‌رسان را بچسبانید.",
        "الصق الرمز الصادر عن BotFather الخاص بالمراسلة.",
    ),
    "The new key could not be verified yet: %s": (
        "کلید جدید هنوز تأیید نشد: %s",
        "تعذّر التحقق من المفتاح الجديد بعد: %s",
    ),
    "Network error while contacting the Uniom management API: %s": (
        "خطای شبکه هنگام تماس با API مدیریتی یونیوم: %s",
        "خطأ شبكة أثناء الاتصال بواجهة Uniom الإدارية: %s",
    ),
    "Uniom could not send the verification code: %s": (
        "یونیوم نتوانست کد تأیید را بفرستد: %s",
        "تعذّر على Uniom إرسال رمز التحقق: %s",
    ),
    "Uniom did not return a linking session. Please try again.": (
        "یونیوم نشست پیوندی برنگرداند. لطفاً دوباره تلاش کنید.",
        "لم ترجع Uniom جلسة ربط. حاول مرة أخرى.",
    ),
    "Uniom did not confirm the messenger link. Please try again.": (
        "یونیوم پیوند پیام‌رسان را تأیید نکرد. لطفاً دوباره تلاش کنید.",
        "لم تؤكد Uniom ربط المراسلة. حاول مرة أخرى.",
    ),
    "Uniom did not confirm the bot link.": (
        "یونیوم پیوند ربات را تأیید نکرد.",
        "لم تؤكد Uniom ربط البوت.",
    ),
    "Uniom did not return a messenger credential id. Please try again.": (
        "یونیوم شناسه اعتبار پیام‌رسان برنگرداند. لطفاً دوباره تلاش کنید.",
        "لم ترجع Uniom معرف اعتماد المراسلة. حاول مرة أخرى.",
    ),
    "Uniom signed you in but did not set an access-token cookie. Check that the gateway allows cookie sessions and try again.": (
        "یونیوم شما را وارد کرد اما کوکی access-token تنظیم نکرد. بررسی کنید دروازه نشست‌های کوکی را مجاز می‌داند و دوباره تلاش کنید.",
        "سجّلت Uniom دخولك لكنها لم تضبط ملف access-token. تحقق من سماح البوابة بجلسات الكوكيز وحاول مجدداً.",
    ),
    "Uniom did not report a messenger account this wizard can link. Enable Bale, Rubika, Eitaa, Soroush+ or Telegram on the gateway and try again.": (
        "یونیوم حساب پیام‌رسانی که این جادوگر بتواند پیوند کند گزارش نکرد. بله، روبیکا، ایتا، سروش‌پلاس یا تلگرام را روی دروازه فعال کنید و دوباره تلاش کنید.",
        "لم تبلغ Uniom عن حساب مراسلة يمكن لهذا المعالج ربطه. فعّل بله أو روبيكا أو إيتا أو سروش+ أو تيليجرام على البوابة وحاول مجدداً.",
    ),
    "Uniom asked for a '%(mode)s' verification, which this wizard does not support. Link this account in the Uniom dashboard instead.": (
        "یونیوم تأیید «%(mode)s» خواست که این جادوگر پشتیبانی نمی‌کند. در عوض این حساب را در داشبورد یونیوم پیوند کنید.",
        "طلبت Uniom تحقق '%(mode)s' الذي لا يدعمه هذا المعالج. اربط هذا الحساب في لوحة Uniom بدلاً منه.",
    ),
    "Uniom did not return an API key. Create one in the Uniom dashboard and connect it with the API-key wizard.": (
        "یونیوم کلید API برنگرداند. در داشبورد یونیوم یکی بسازید و با جادوگر کلید API متصلش کنید.",
        "لم ترجع Uniom مفتاح API. أنشئ واحداً في لوحة Uniom واربطه بمعالج مفتاح API.",
    ),
    "Messenger credential id on the Uniom management API, when this connection was created by the Link Messenger Account wizard.": (
        "شناسه اعتبار پیام‌رسان در API مدیریتی یونیوم، وقتی این اتصال با جادوگر پیوند حساب پیام‌رسان ساخته شده باشد.",
        "معرف اعتماد المراسلة في واجهة Uniom الإدارية، عندما يُنشأ هذا الاتصال عبر معالج ربط حساب المراسلة.",
    ),
    "Phone number (or bot identity) of the linked messenger account.": (
        "شماره تلفن (یا هویت ربات) حساب پیام‌رسان پیوندشده.",
        "رقم هاتف (أو هوية بوت) حساب المراسلة المرتبط.",
    ),
    "State reported for the linked messenger credential.": (
        "وضعیت گزارش‌شده برای اعتبار پیام‌رسان پیوندشده.",
        "الحالة المبلغ عنها لاعتماد المراسلة المرتبط.",
    ),
    "Native Discuss thread mirroring this conversation: inbound messages are posted here so they appear under Discuss.": (
        "رشته بومی Discuss که آینه این گفتگوست: پیام‌های ورودی اینجا منتشر می‌شوند تا زیر Discuss دیده شوند.",
        "سلسلة Discuss الأصلية المطابقة لهذه المحادثة: تُنشر الرسائل الواردة هنا لتظهر تحت Discuss.",
    ),
    "Messenger of the connection, exposed so kanban cards can show the platform badge without an extra read.": (
        "پیام‌رسان اتصال، برای اینکه کارت‌های کانبان نشان پلتفرم را بدون خواندن اضافه نشان دهند.",
        "مراسلة الاتصال، مكشوفة لتتمكن بطاقات كانبان من عرض شارة المنصة دون قراءة إضافية.",
    ),
    "Serialized requests.Session cookie jar (HttpOnly gateway cookies included). Transient only: never copied to a connection.": (
        "جار کوکی requests.Session سریال‌شده (شامل کوکی‌های HttpOnly دروازه). فقط موقت: هرگز به اتصال کپی نمی‌شود.",
        "وعاء كوكيز requests.Session مسلسل (يشمل كوكيز البوابة HttpOnly). مؤقت فقط: لا يُنسخ إلى اتصال أبداً.",
    ),
    "Own Messages Side": ("سمت پیام‌های خود", "جانب رسائلي"),
    "Left": ("چپ", "يسار"),
    "Right": ("راست", "يمين"),
    "Which side of the conversation your own (outgoing) messages appear on. Incoming messages take the other side.": (
        "پیام‌های خود (خروجی) در کدام سمت گفتگو دیده شوند. پیام‌های ورودی سمت دیگر را می‌گیرند.",
        "في أي جانب تظهر رسائلك (الصادرة). الرسائل الواردة تأخذ الجانب الآخر.",
    ),
    # ---- field helps (previously untranslated) -------------------------
    "All": ("همه", "الكل"),
    "Base URL of the Uniom Bot API. Use https://api.uniom.ir (Iran) or https://api.uniomi.ir (international mirror).": (
        "نشانی پایه Bot API یونیوم. از https://api.uniom.ir (ایران) یا https://api.uniomi.ir (آینه بین‌المللی) استفاده کنید.",
        "عنوان Base لـ Bot API في Uniom. استخدم https://api.uniom.ir (إيران) أو https://api.uniomi.ir (المرآة الدولية).",
    ),
    "Extra destinations, one per line: @channel, +989123456789, 09123456789 or numeric chat id. Useful to keep your own channel informed about new orders.": (
        "مقصدهای اضافه، هر خط یکی: @channel، +989123456789، 09123456789 یا شناسه عددی. برای مطلع نگه داشتن کانال خود از سفارش‌های جدید مفید است.",
        "وجهات إضافية، واحدة في كل سطر: @channel أو +989123456789 أو 09123456789 أو معرف رقمي. مفيد لإبقاء قناتك على اطلاع بالطلبات الجديدة.",
    ),
    "Leave empty to make this connection available in every company.": (
        "خالی بگذارید تا این اتصال در همه شرکت‌ها در دسترس باشد.",
        "اتركه فارغاً لإتاحة هذا الاتصال في كل الشركات.",
    ),
    "Manages connections, API keys, automation rules and templates.": (
        "مدیریت اتصال‌ها، کلیدهای API، قوانین خودکار و قالب‌ها.",
        "إدارة الاتصالات ومفاتيح API وقواعد الأتمتة والقوالب.",
    ),
    "Message text with placeholders, e.g.:\nHello {{ object.partner_id.name }}, your order {{ object.name }} is confirmed.\nUses Odoo's standard inline-template syntax ({{ }}), like mail and SMS templates.": (
        "متن پیام با جای‌نگه‌دار، مثلاً:\nسلام {{ object.partner_id.name }}، سفارش {{ object.name }} شما تأیید شد.\nاز نگارش استاندارد قالب درون‌خطی اودو ({{ }}) استفاده می‌کند، مثل قالب‌های ایمیل و پیامک.",
        "نص الرسالة مع عناصر نائبة، مثلاً:\nمرحباً {{ object.partner_id.name }}، تم تأكيد طلبك {{ object.name }}.\nيستخدم صيغة القوالب المضمنة القياسية في Odoo ({{ }})، مثل قوالب البريد والرسائل.",
    ),
    "Messenger destination for this contact: phone (+989123456789), @username or numeric chat id. Leave empty to use the mobile/phone number.": (
        "مقصد پیام‌رسان این مخاطب: تلفن (+989123456789)، @username یا شناسه عددی. خالی بگذارید تا از شماره موبایل/تلفن استفاده شود.",
        "وجهة المراسلة لجهة الاتصال: هاتف (+989123456789) أو @username أو معرف رقمي. اتركه فارغاً لاستخدام رقم الجوال/الهاتف.",
    ),
    "Optional Odoo domain restricting which records trigger this rule, e.g. [('amount_total', '>', 1000000)]": (
        "دامنه اختیاری اودو که مشخص می‌کند کدام رکوردها این قانون را فعال کنند، مثلاً [('amount_total', '>', 1000000)]",
        "نطاق Odoo اختياري يقيّد السجلات التي تفعّل هذه القاعدة، مثلاً [('amount_total', '>', 1000000)]",
    ),
    "Optional per-language templates: picked when they match the customer's language, otherwise the fallback template is used.": (
        "قالب‌های اختیاری هر زبان: وقتی با زبان مشتری مطابقت کنند انتخاب می‌شوند، وگرنه از قالب پیش‌فرض استفاده می‌شود.",
        "قوالب اختيارية لكل لغة: تُختار عند مطابقتها لغة العميل، وإلا يُستخدم القالب الاحتياطي.",
    ),
    "Optional translation language (ISO code) to select when sending out an email. If not set, the english version will be used. This should usually be a placeholder expression that provides the appropriate language, e.g. {{ object.partner_id.lang }}.": (
        "زبان ترجمه اختیاری (کد ISO) برای انتخاب هنگام ارسال ایمیل. اگر تنظیم نشود از نسخه انگلیسی استفاده می‌شود. معمولاً باید یک عبارت جای‌نگه‌دار باشد که زبان مناسب را بدهد، مثلاً {{ object.partner_id.lang }}.",
        "لغة الترجمة الاختيارية (رمز ISO) للاختيار عند إرسال بريد. إذا لم تُضبط تُستخدم النسخة الإنجليزية. ويفضل أن تكون تعبيراً نائباً يعطي اللغة المناسبة، مثلاً {{ object.partner_id.lang }}.",
    ),
    "Optional: this template is picked when the customer speaks this language. Leave empty for the fallback template.": (
        "اختیاری: این قالب وقتی انتخاب می‌شود که مشتری به این زبان صحبت کند. برای قالب پیش‌فرض خالی بگذارید.",
        "اختياري: يُختار هذا القالب عندما يتحدث العميل بهذه اللغة. اتركه فارغاً للقالب الاحتياطي.",
    ),
    "Optional: use a specific Uniom connection (messenger). Empty = first active connection of the company.": (
        "اختیاری: از یک اتصال یونیوم (پیام‌رسان) مشخص استفاده کن. خالی = اولین اتصال فعال شرکت.",
        "اختياري: استخدم اتصال Uniom (مراسلة) محدداً. فارغ = أول اتصال نشط للشركة.",
    ),
    "Relational field holding the customer to notify (partner_id for orders and invoices).": (
        "فیلد رابطه‌ای حاوی مشتری برای اطلاع‌رسانی (partner_id برای سفارش‌ها و فاکتورها).",
        "حقل علاقي يحمل العميل المراد إشعاره (partner_id للطلبات والفواتير).",
    ),
    "Secret sent back by Uniom in the X-Telegram-Bot-Api-Secret-Token header. Regenerate to invalidate.": (
        "رمزی که یونیوم در سربرگ X-Telegram-Bot-Api-Secret-Token برمی‌گرداند. برای ابطال دوباره تولید کنید.",
        "الرمز الذي ترجعه Uniom في ترويسة X-Telegram-Bot-Api-Secret-Token. أعد توليده للإبطال.",
    ),
    "Send the moment the event happens. Unchecked: only queue for the periodic cron. Failures are always re-queued either way.": (
        "همان لحظه وقوع رویداد ارسال کن. بدون تیک: فقط در صف کرون دوره‌ای قرار می‌گیرد. خرابی‌ها در هر صورت دوباره در صف قرار می‌گیرند.",
        "أرسل لحظة وقوع الحدث. بدون تحديد: يُحفظ في قائمة المهمة الدورية فقط. وتُعاد الإخفاقات إلى القائمة في كل الأحوال.",
    ),
    "Send the record's standard PDF report as a document with the message.": (
        "گزارش PDF استاندارد رکورد را به‌عنوان سند همراه پیام ارسال کن.",
        "أرسل تقرير PDF القياسي للسجل كمستند مع الرسالة.",
    ),
    "Technical reference of the QWeb report to attach (auto-filled from the event, editable).": (
        "ارجاع فنی گزارش QWeb برای پیوست (از رویداد خودکار پر می‌شود، قابل ویرایش).",
        "المرجع التقني لتقرير QWeb المرفق (يُملأ تلقائياً من الحدث، قابل للتحرير).",
    ),
    "Technical reference of the QWeb report to attach as a document, e.g. account.account_invoices.": (
        "ارجاع فنی گزارش QWeb برای پیوست به‌عنوان سند، مثلاً account.account_invoices.",
        "المرجع التقني لتقرير QWeb المرفق كمستند، مثلاً account.account_invoices.",
    ),
    "The uniom_... key issued in your Uniom dashboard (Account → API Keys). Bound to one messenger account per key.": (
        "کلید uniom_... صادرشده در داشبورد یونیوم (حساب ← کلیدهای API). هر کلید به یک حساب پیام‌رسان متصل است.",
        "مفتاح uniom_... الصادر في لوحة Uniom (الحساب ← مفاتيح API). كل مفتاح مرتبط بحساب مراسلة واحد.",
    ),
    "Webhook is instant but needs a publicly reachable Odoo; polling fetches new messages every minute and works behind NAT.": (
        "وب‌هوک فوری است اما به اودوی عمومی نیاز دارد؛ دریافت دوره‌ای هر دقیقه پیام‌های جدید را می‌گیرد و پشت NAT کار می‌کند.",
        "الـ Webhook فوري لكنه يحتاج عنوان Odoo عاماً؛ أما الاستطلاع فيجلب الرسائل الجديدة كل دقيقة ويعمل خلف NAT.",
    ),
    "When an incoming message cannot be matched to an existing contact, create one automatically.": (
        "وقتی پیام ورودی با مخاطب موجودی مطابقت نکرد، خودکار یکی بساز.",
        "عند تعذّر مطابقة رسالة واردة مع جهة اتصال موجودة، أنشئ واحدة تلقائياً.",
    ),
 # ---- hardening / safety messages -------------------------------------
    "Invalid URL: control characters are not allowed.": (
        "نشانی نامعتبر: نویسه‌های کنترلی مجاز نیستند.",
        "عنوان غير صالح: رموز التحكم غير مسموحة.",
    ),
    "Invalid URL %s: rejected by the HTTP stack (%s).": (
        "نشانی نامعتبر %s: پشته HTTP آن را رد کرد (%s).",
        "عنوان غير صالح %s: رفضه مكدس HTTP ‏(%s).",
    ),
    "Ambiguous URL %s: the HTTP stack resolves a different host than the validator.": (
        "نشانی مبهم %s: پشته HTTP میزبانی متفاوت با اعتبارسنج تشخیص می‌دهد.",
        "عنوان غامض %s: يحدد مكدس HTTP مضيفاً مختلفاً عن المدقق.",
    ),
    "Unexpected error: %s": ("خطای غیرمنتظره: %s", "خطأ غير متوقع: %s"),
    "Report %s is not allowed for this document.": (
        "گزارش %s برای این سند مجاز نیست.",
        "التقرير %s غير مسموح لهذا المستند.",
    ),
    "Document not attached: %s": ("سند پیوست نشد: %s", "لم يُرفق المستند: %s"),
    "Could not render the PDF report: %s": ("رندر گزارش PDF ممکن نشد: %s", "تعذّر إنشاء تقرير PDF: %s"),
    # review-fix + link-wizard strings (Nov 2026)
    "%s update(s) failed processing and will be retried.": ("%s به‌روزرسانی پردازش نشد و دوباره تلاش می‌شود.", "تعذّرت معالجة %s من التحديثات وستُعاد المحاولة."),
    "Available Platforms": ("پیام‌رسان‌های موجود", "المنصات المتاحة"),
    "Cached profile photo from getUserProfilePhotos.": ("عکس پروفایل ذخیره‌شده از getUserProfilePhotos.", "صورة الملف الشخصي المخزنة من getUserProfilePhotos."),
    "Delete": ("حذف", "حذف"),
    "Delete this message from the messenger?": ("این پیام از پیام‌رسان حذف شود؟", "حذف هذه الرسالة من المراسلة؟"),
    "Deleted On Messenger": ("حذف‌شده در پیام‌رسان", "محذوفة في المراسلة"),
    "Delivered": ("تحویل‌شده", "تم التسليم"),
    "Edit": ("ویرایش", "تعديل"),
    "Edit message": ("ویرایش پیام", "تعديل الرسالة"),
    "Enter %(label)s.": ("%(label)s را وارد کنید.", "أدخل %(label)s."),
    "Enter the token.": ("توکن را وارد کنید.", "أدخل الرمز."),
    "JSON list of {type, name, description} for the chosen platform, from GET /platforms — drives the radio cards.": ("فهرست JSON از {type, name, description} برای پیام‌رسان انتخاب‌شده، از GET /platforms — محرک کارت‌های انتخابی.", "قائمة JSON من {type, name, description} للمنصة المختارة، من GET /platforms — تغذي بطاقات الاختيار."),
    "Link Auth Options": ("گزینه‌های احراز پیوند", "خيارات مصادقة الربط"),
    "Link Dynamic Help": ("راهنمای پویای پیوند", "مساعدة الربط الديناميكية"),
    "Link Dynamic Token Label": ("برچسب توکن پویای پیوند", "تسمية رمز الربط الديناميكي"),
    "Link Dynamic Token Placeholder": ("متن راهنمای توکن پویای پیوند", "النص التوضيحي لرمز الربط الديناميكي"),
    "Link Pair Code": ("کد جفت‌سازی پیوند", "رمز إقران الربط"),
    "Link Qr Link": ("پیوند QR", "رابط QR"),
    "Login Method": ("روش ورود", "طريقة الدخول"),
    "Login methods offered by the gateway for this platform.": ("روش‌های ورودی که دروازه برای این پیام‌رسان ارائه می‌دهد.", "طرق الدخول التي توفرها البوابة لهذه المنصة."),
    "Messenger Photo": ("عکس پیام‌رسان", "صورة المراسلة"),
    "Messenger Photo Updated At": ("زمان به‌روزرسانی عکس پیام‌رسان", "وقت تحديث صورة المراسلة"),
    "No messengers available for linking right now.": ("در حال حاضر پیام‌رسانی برای پیوند موجود نیست.", "لا توجد مراسلات متاحة للربط حالياً."),
    "Only outgoing text messages can be edited.": ("فقط پیام‌های متنی خروجی قابل ویرایش‌اند.", "يمكن تعديل الرسائل النصية الصادرة فقط."),
    "Read": ("خوانده‌شده", "مقروءة"),
    "Read/delivery state reported by getMessageStates.": ("وضعیت خوانده/تحویل گزارش‌شده توسط getMessageStates.", "حالة القراءة/التسليم المبلغة من getMessageStates."),
    "Seen": ("دیده‌شده", "شوهدت"),
    "Seen Count": ("تعداد دیده‌شده", "عدد المشاهدات"),
    "Seen State": ("وضعیت دیده‌شدن", "حالة المشاهدة"),
    "Seen count from getMessageStates.": ("تعداد دیده‌شده از getMessageStates.", "عدد المشاهدات من getMessageStates."),
    "Set once in Settings → Uniom → Gateway URL; every wizard and connection uses that value.": ("یک بار در تنظیمات ← یونیوم ← نشانی دروازه تنظیم کنید؛ همه جادوگرها و اتصال‌ها از همان مقدار استفاده می‌کنند.", "اضبط مرة واحدة في الإعدادات ← Uniom ← عنوان البوابة؛ كل المعالجات والاتصالات تستخدم تلك القيمة."),
    "Sign in first to load the available messengers.": ("اول وارد شوید تا پیام‌رسان‌های موجود بارگذاری شوند.", "سجّل الدخول أولاً لتحميل المراسلات المتاحة."),
    "State Updated At": ("زمان به‌روزرسانی وضعیت", "وقت تحديث الحالة"),
    "The API key was rejected (revoked or wrong account). Create a fresh key in your Uniom dashboard and update it here.": ("کلید API رد شد (باطل‌شده یا حساب اشتباه). یک کلید تازه در داشبورد یونیوم بسازید و اینجا به‌روز کنید.", "رُفض مفتاح API (ملغى أو حساب خاطئ). أنشئ مفتاحاً جديداً في لوحة Uniom وحدّثه هنا."),
    "The Uniom gateway did not answer.": ("دروازه یونیوم پاسخ نداد.", "لم ترد بوابة Uniom."),
    "The Uniom gateway is having trouble (HTTP %s). Try again in a few minutes.": ("دروازه یونیوم دچار مشکل است (HTTP %s). چند دقیقه دیگر دوباره تلاش کنید.", "تواجه بوابة Uniom مشكلة (HTTP %s). حاول مجدداً بعد بضع دقائق."),
    "The action did not complete.": ("عملیات کامل نشد.", "لم تكتمل العملية."),
    "The action failed unexpectedly; retry it from the connection form.": ("عملیات به‌طور غیرمنتظره ناموفق بود؛ از فرم اتصال دوباره تلاش کنید.", "فشلت العملية بشكل غير متوقع؛ أعد المحاولة من نموذج الاتصال."),
    "The message was deleted on the messenger side.": ("پیام در سمت پیام‌رسان حذف شد.", "حُذفت الرسالة من جهة المراسلة."),
    "This login method is not offered for this messenger. Pick one from the list.": ("این روش ورود برای این پیام‌رسان ارائه نمی‌شود. یکی را از فهرست انتخاب کنید.", "طريقة الدخول هذه غير متاحة لهذه المراسلة. اختر واحدة من القائمة."),
    "This login method opens the Uniom dashboard in a browser. Link this account at %(url)s, then connect it here with an API key.": ("این روش ورود داشبورد یونیوم را در مرورگر باز می‌کند. این حساب را در %(url)s پیوند کنید، بعد با کلید API اینجا وصلش کنید.", "طريقة الدخول هذه تفتح لوحة Uniom في المتصفح. اربط هذا الحساب في %(url)s، ثم صِله هنا بمفتاح API."),
    "This messenger is not available right now. Pick one from the list.": ("این پیام‌رسان در حال حاضر موجود نیست. یکی را از فهرست انتخاب کنید.", "هذه المراسلة غير متاحة حالياً. اختر واحدة من القائمة."),
    "Token": ("توکن", "الرمز"),
    "Too many requests — try again in %s seconds.": ("درخواست‌ها بیش از حد است — %s ثانیه دیگر دوباره تلاش کنید.", "طلبات كثيرة جداً — حاول مجدداً بعد %s ثانية."),
    "Too many requests — wait a minute and try again.": ("درخواست‌ها بیش از حد است — یک دقیقه صبر کنید و دوباره تلاش کنید.", "طلبات كثيرة جداً — انتظر دقيقة وحاول مجدداً."),
    "View count from getMessageStates.": ("تعداد بازدید از getMessageStates.", "عدد المشاهدات من getMessageStates."),
    "Views Count": ("تعداد بازدید", "عدد المشاهدات"),
    "Webhook registration failed (%s); polling could not be started either (%s).": ("ثبت وب‌هوک ناموفق بود (%s)؛ نظرسنجی دوره‌ای هم شروع نشد (%s).", "فشل تسجيل webhook (%s)؛ وتعذّر بدء الاستطلاع أيضاً (%s)."),
    "Write the edited text first.": ("اول متن ویرایش‌شده را بنویسید.", "اكتب النص المعدّل أولاً."),
    "edited": ("ویرایش‌شده", "معدّلة"),
    # poll poison-bound strings
    "Consecutive polls the same update id failed; past the bound the poison update is skipped so polling never wedges.": ("نظرسنجی‌های پیاپی که همان شناسه به‌روزرسانی ناموفق بود؛ پس از سقف، به‌روزرسانی مسموم رد می‌شود تا نظرسنجی گیر نکند.", "مرات الاستطلاع المتتالية التي فشل فيها نفس معرف التحديث؛ بعد الحد يُتخطى التحديث المسموم حتى لا يتعطل الاستطلاع."),
    "First update id that failed processing; the offset is held here for retry until it succeeds or exceeds the retry bound.": ("شناسه اولین به‌روزرسانی که پردازشش ناموفق بود؛ آفست برای تلاش مجدد اینجا نگه داشته می‌شود تا موفق شود یا از سقف بگذرد.", "معرف أول تحديث فشلت معالجته؛ تُحفظ الإزاحة هنا لإعادة المحاولة حتى ينجح أو يتجاوز الحد."),
    "Poll Failed Streak": ("رشته ناکامی نظرسنجی", "سلسلة فشل الاستطلاع"),
    "Poll Failed Update": ("به‌روزرسانی ناموفق نظرسنجی", "تحديث الاستطلاع الفاشل"),
    "Update %s failed %s times and was skipped; check the logs.": ("به‌روزرسانی %s بعد از %s بار ناموفق رد شد؛ لاگ‌ها را بررسی کنید.", "تُخطّي التحديث %s بعد %s محاولات فاشلة؛ راجع السجلات."),
    # poll dead-letter strings
    "Update %s failed %s times and was skipped; payload kept on the connection.": ("به‌روزرسانی %s بعد از %s بار ناموفق رد شد؛ محموله روی اتصال نگه داشته شد.", "تُخطّي التحديث %s بعد %s محاولات فاشلة؛ الحمولة محفوظة على الاتصال."),
    "Raw payload of the last skipped poison update (JSON), kept for support replay after the retry bound gave up on it.": ("محموله خام آخرین به‌روزرسانی مسموم ردشده (JSON)، نگه داشته شده برای بازپخش پشتیبانی بعد از اینکه سقف تلاش تسلیمش شد.", "الحمولة الخام لآخر تحديث مسموم تم تخطيه (JSON)، محفوظة لإعادة التشغيل بعد استنفاد حد المحاولات."),
    "Poll Dead Update": ("به‌روزرسانی مسموم نظرسنجی", "تحديث الاستطلاع المسموم"),
    "Only outgoing messages can be deleted.": ("فقط پیام‌های خروجی قابل حذف‌اند.", "يمكن حذف الرسائل الصادرة فقط."),
    "Uniom: sync message states": ("یونیوم: همگام‌سازی وضعیت پیام‌ها", "Uniom: مزامنة حالات الرسائل"),
    # whole view terms (model_terms are matched verbatim; never substring)
    "A new Uniom API key is created for the linked account\n                        and saved on a connection in Odoo.": ("یک کلید API جدید یونیوم برای حساب پیوندشده ساخته می‌شود و روی یک اتصال در اودو ذخیره می‌شود.", "يُنشأ مفتاح API جديد في Uniom للحساب المرتبط ويُحفظ على اتصال في Odoo."),
    "Back": ("بازگشت", "رجوع"),
    "Choose the messenger and the phone number registered on\n                        it. Uniom sends the verification code through that\n                        messenger.": ("پیام‌رسان و شماره تلفن ثبت‌شده روی آن را انتخاب کنید. یونیوم کد تأیید را از طریق همان پیام‌رسان می‌فرستد.", "اختر المراسلة ورقم الهاتف المسجل عليها. ترسل Uniom رمز التحقق عبر تلك المراسلة."),
    "Close": ("بستن", "إغلاق"),
    "Create an API key in your Uniom dashboard (Account → API Keys)\n                        and paste it below — one key per messenger account\n                        (Bale, Rubika, Eitaa, Soroush+, Telegram).": ("در داشبورد یونیوم یک کلید API بسازید (حساب ← کلیدهای API) و پایین بچسبانید — یک کلید برای هر حساب پیام‌رسان (بله، روبیکا، ایتا، سروش‌پلاس، تلگرام).", "أنشئ مفتاح API في لوحة Uniom (الحساب ← مفاتيح API) والصقه أدناه — مفتاح واحد لكل حساب مراسلة (بله، روبیکا، إیتا، سروش‌پلاس، تلگرام)."),
    "Create the API key": ("ساخت کلید API", "إنشاء مفتاح API"),
    "Create Connection": ("ساخت اتصال", "إنشاء الاتصال"),
    "Default Uniom Bot API URL used by new connections.": ("نشانی پیش‌فرض Bot API یونیوم که اتصال‌های جدید استفاده می‌کنند.", "عنوان Bot API الافتراضي في Uniom الذي تستخدمه الاتصالات الجديدة."),
    "Enter the Uniom code": ("کد یونیوم را وارد کنید", "أدخل رمز Uniom"),
    "Enter the code Uniom sent to your phone. You can request\n                        a new code if it did not arrive.": ("کدی که یونیوم به گوشی شما فرستاد را وارد کنید. اگر نرسید می‌توانید کد جدید بخواهید.", "أدخل الرمز الذي أرسلته Uniom إلى هاتفك. يمكنك طلب رمز جديد إذا لم يصل."),
    "Enter the code you received in the messenger.": ("کدی که در پیام‌رسان دریافت کردید را وارد کنید.", "أدخل الرمز الذي استلمته في المراسلة."),
    "Internal notes...": ("یادداشت‌های داخلی...", "ملاحظات داخلية..."),
    "Kind": ("نوع", "النوع"),
    "Link Bot": ("پیوند ربات", "ربط البوت"),
    "Link a contact...": ("پیوند مخاطب...", "اربط جهة اتصال..."),
    "Link a messenger account": ("پیوند حساب پیام‌رسان", "ربط حساب مراسلة"),
    "Link with a bot token": ("پیوند با توکن ربات", "الربط برمز بوت"),
    "Manage API-key connections and register the inbound webhook.": ("مدیریت اتصال‌های کلید API و ثبت وب‌هوک ورودی.", "إدارة اتصالات مفاتيح API وتسجيل webhook الوارد."),
    "Master switch for all automated Uniom messages.": ("کلید اصلی همه پیام‌های خودکار یونیوم.", "المفتاح الرئيسي لجميع رسائل Uniom التلقائية."),
    "Media": ("رسانه", "الوسائط"),
    "Messenger account linked": ("حساب پیام‌رسان پیوند شد", "تم ربط حساب المراسلة"),
    "Open Connection": ("باز کردن اتصال", "فتح الاتصال"),
    "Paste the token issued by the messenger's bot father.\n                        The token is sent once to Uniom and is never stored in\n                        Odoo.": ("توکن صادرشده توسط بات‌فادر پیام‌رسان را بچسبانید. توکن فقط یک بار به یونیوم فرستاده می‌شود و هرگز در اودو ذخیره نمی‌شود.", "الصق الرمز الصادر عن bot father الخاص بالمراسلة. يُرسل الرمز مرة واحدة إلى Uniom ولا يُخزن في Odoo أبداً."),
    "Per-language templates (fa, ar, ...)": ("قالب‌های هر زبان (fa، ar و ...)", "قوالب لكل لغة (fa، ar، ...)"),
    "Resend Code": ("ارسال مجدد کد", "إعادة إرسال الرمز"),
    "Right (WhatsApp style) or left for your outgoing bubbles; incoming takes the other side.": ("راست (به سبک واتساپ) یا چپ برای حباب‌های خروجی شما؛ ورودی سمت دیگر را می‌گیرد.", "اليمين (بأسلوب WhatsApp) أو اليسار لفقاعاتك الصادرة؛ والواردة تأخذ الجهة الأخرى."),
    "Scan this code with the messenger app, then press Verify.": ("این کد را با اپ پیام‌رسان اسکن کنید، بعد تأیید را بزنید.", "امسح هذا الرمز بتطبيق المراسلة، ثم اضغط تحقق."),
    "Send Code": ("ارسال کد", "إرسال الرمز"),
    "Sign in to Uniom": ("ورود به یونیوم", "تسجيل الدخول إلى Uniom"),
    "Start Linking": ("شروع پیوند", "بدء الربط"),
    "The API key is stored on the connection below. Open it\n                        to send a test message or manage webhook/polling.": ("کلید API روی اتصال پایین ذخیره شده. آن را باز کنید تا پیام آزمایشی بفرستید یا وب‌هوک/دریافت دوره‌ای را مدیریت کنید.", "مفتاح API مخزن على الاتصال أدناه. افتحه لإرسال رسالة اختبار أو لإدارة webhook/الاستطلاع."),
    "This messenger account has two-step verification\n                        enabled. Enter its password to finish linking.": ("این حساب پیام‌رسان تأیید دومرحله‌ای فعال دارد. برای تکمیل پیوند، گذرواژه‌اش را وارد کنید.", "حساب المراسلة هذا لديه تحقق بخطوتين. أدخل كلمة مروره لإتمام الربط."),
    "Two-step password": ("گذرواژه دومرحله‌ای", "كلمة مرور الخطوتين"),
    "Type": ("نوع", "النوع"),
    "Use a Bot Token": ("استفاده از توکن ربات", "استخدام رمز بوت"),
    "Use the phone number of your Uniom account. We send a\n                        one-time code, then let you choose the messenger account\n                        to link.": ("از شماره تلفن حساب یونیوم خود استفاده کنید. ما یک کد یک‌بارمصرف می‌فرستیم، بعد می‌گذاریم حساب پیام‌رسانی که می‌خواهید پیوند کنید را انتخاب کنید.", "استخدم رقم هاتف حساب Uniom الخاص بك. نرسل رمزاً لمرة واحدة، ثم ندعك تختار حساب المراسلة المراد ربطه."),
    "Verify": ("تأیید", "تحقق"),
    "Verify Password": ("تأیید گذرواژه", "التحقق من كلمة المرور"),
    "Verify the messenger account": ("تأیید حساب پیام‌رسان", "التحقق من حساب المراسلة"),
    "Write your message...": ("پیام خود را بنویسید...", "اكتب رسالتك..."),
    "e.g. Bale — Sales Notifications": ("مثلاً بله — اطلاع‌رسانی فروش", "مثال: Bale — إشعارات المبيعات"),
    "e.g. Notify customer when order is confirmed": ("مثلاً اطلاع به مشتری هنگام تأیید سفارش", "مثال: إشعار العميل عند تأكيد الطلب"),
    # Odoo 19 help texts
    "Messenger destination for this contact: phone (+989123456789), @username or numeric chat id. Leave empty to use the phone number.": ("مقصد پیام‌رسان این مخاطب: تلفن (+989123456789)، @نام‌کاربری یا شناسه عددی چت. خالی بگذارید تا از شماره تلفن استفاده شود.", "وجهة المراسلة لجهة الاتصال هذه: الهاتف (+989123456789) أو @اسم_المستخدم أو معرف المحادثة الرقمي. اتركه فارغاً لاستخدام رقم الهاتف."),
    "Optional translation language (ISO code) to select when sending out an email. If not set, the main partner's language will be used. This should usually be a placeholder expression that provides the appropriate language, e.g. {{ object.partner_id.lang }}.": ("زبان ترجمه اختیاری (کد ISO) که هنگام ارسال ایمیل انتخاب می‌شود. اگر تنظیم نشود، از زبان مخاطب اصلی استفاده می‌شود. معمولاً باید یک عبارت جای‌نگه‌دار باشد که زبان مناسب را بدهد، مثلاً {{ object.partner_id.lang }}.", "لغة الترجمة الاختيارية (رمز ISO) للاختيار عند إرسال بريد. إذا لم تُضبط تُستخدم لغة جهة الاتصال الرئيسية. يجب أن يكون عادة تعبيراً نائباً يوفر اللغة المناسبة، مثل {{ object.partner_id.lang }}."),
    "Message id assigned by the messenger, needed to edit later. Stored as text: gateway ids exceed the 32-bit integer range.": ("شناسه پیام تخصیص‌یافته توسط پیام‌رسان، لازم برای ویرایش بعدی. به‌صورت متن ذخیره می‌شود: شناسه‌های دروازه از بازه عدد صحیح ۳۲ بیتی بیشترند.", "معرف الرسالة المخصص من المراسلة، لازم للتعديل لاحقاً. يُخزن كنص: معرفات البوابة تتجاوز نطاق العدد الصحيح 32 بت."),
}


def _metadata(code=None, team=None):
    meta = {
        "Project-Id-Version": "Odoo Server %s" % SERIES,
        "Report-Msgid-Bugs-To": "",
        "POT-Creation-Date": NOW,
        "PO-Revision-Date": NOW,
        "Last-Translator": "Uniom",
        "Language-Team": team or "Uniom",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
    }
    if code:
        meta["Language"] = code
        meta["Plural-Forms"] = "nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);" if code.startswith("ar") else "nplurals=2; plural=(n > 1);"
    return meta


def _translate_arch(arch, index):
    """Translate the UI strings inside a model_terms view/action-help block.

    Whole-term match first; the substring fallback requires word
    boundaries so short keys never corrupt longer words ("poll" inside
    "polling" produced "نظرسنجیing").
    """
    table = dict(T)
    table.update(T_EXTRA)
    if arch in table:
        return table[arch][index]
    for key in sorted(table, key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(key) + r"(?!\w)"
        arch = re.sub(pattern, lambda _m, v=table[key][index]: v, arch)
    return arch


def _build_from_skeleton(skeleton, index=None, code=None, team=None):
    """index=None -> POT (all msgstr empty); 0/1 -> fa/ar merge."""
    po = polib.POFile()
    po.metadata = _metadata(code, team)
    table = dict(T)
    table.update(T_EXTRA)
    count = 0
    for entry in skeleton:
        if entry.obsolete:
            continue
        msgstr = ""
        if index is not None:
            occurrence = entry.occurrences[0][0] if entry.occurrences else ""
            if occurrence.startswith("model_terms:"):
                msgstr = _translate_arch(entry.msgid, index)
            elif entry.msgid in table:
                msgstr = table[entry.msgid][index]
            elif entry.msgstr and entry.msgid:
                msgstr = entry.msgstr  # keep already-translated code entries
        po.append(
            polib.POEntry(
                msgid=entry.msgid,
                msgstr=msgstr,
                occurrences=entry.occurrences,
                comment=entry.comment,
            )
        )
        count += 1
    return po, count


def _build_legacy(index=None, code=None, team=None):
    po = polib.POFile()
    po.metadata = _metadata(code, team)
    table = dict(T)
    table.update(T_EXTRA)
    for msgid in sorted(table):
        entry = polib.POEntry(msgid=msgid, msgstr=table[msgid][index] if index is not None else "")
        # Odoo's translation importer requires a "# module: <name>" comment
        # and occurrences in "code:<path>" (or "model:...") form; bare file
        # paths are rejected as "unknown occurrence" and skipped.
        entry.comment = f"module: {MODULE}"
        entry.occurrences = [("code:models/uniom_tools.py", "1")]
        po.append(entry)
    return po


def main():
    skeleton_path = sys.argv[1] if len(sys.argv) > 1 else None
    if skeleton_path:
        skeleton = polib.pofile(skeleton_path)
        build = lambda **kw: _build_from_skeleton(skeleton, **kw)
    else:
        print("WARNING: no Odoo-exported skeleton given; UI model_terms "
              "translations (views, menus) will be missing — see header.")
        build = _build_legacy
    pot, count = build()
    pot.save(str(I18N / f"{MODULE}.pot"))
    fa, _n = build(index=0, code="fa_IR", team="Uniom <support@uniom.ir>")
    fa.save(str(I18N / "fa_IR.po"))
    ar, _m = build(index=1, code="ar_001", team="Uniom <support@uniom.ir>")
    ar.save(str(I18N / "ar_001.po"))
    print("i18n files written:", count, "entries each; translated terms:", len(T) + len(T_EXTRA))


if __name__ == "__main__":
    main()

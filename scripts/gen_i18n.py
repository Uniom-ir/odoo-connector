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
import sys

import polib
from pathlib import Path

NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M%z")
MODULE = "uniom_connector"
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
}


def _metadata(code=None, team=None):
    meta = {
        "Project-Id-Version": "Odoo Server 18.0",
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
    """Translate the UI strings inside a model_terms view/action-help block
    by longest-match-first replacement (attribute values and text nodes)."""
    table = dict(T)
    table.update(T_EXTRA)
    for key in sorted(table, key=len, reverse=True):
        if key in arch:
            arch = arch.replace(key, table[key][index])
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

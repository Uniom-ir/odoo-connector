#!/usr/bin/env python3
# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Regenerate i18n/uniom_connector.pot, i18n/fa_IR.po and i18n/ar_101.po.

Run from the repo root:  python3 scripts/gen_i18n.py
"""
import datetime

import polib
from pathlib import Path

NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M%z")
MODULE = "uniom_connector"
HERE = Path(__file__).resolve().parent
I18N = HERE.parent / MODULE / "i18n"
I18N.mkdir(exist_ok=True)

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
}


def build_pot():
    pot = polib.POFile()
    pot.metadata = {
        "Project-Id-Version": "Odoo 18.0/17.0",
        "Report-Msgid-Bugs-To": "",
        "POT-Creation-Date": NOW,
        "PO-Revision-Date": NOW,
        "Last-Translator": "Uniom",
        "Language-Team": "Uniom",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
    }
    for msgid in sorted(T):
        entry = polib.POEntry(msgid=msgid, msgstr="")
        entry.occurrences = [("models/uniom_models.py", "1")]
        pot.append(entry)
    return pot


def build_po(lang, code, team, index):
    po = polib.POFile()
    po.metadata = dict(build_pot().metadata)
    po.metadata["Language"] = code
    po.metadata["Language-Team"] = team
    po.metadata["Plural-Forms"] = (
        "nplurals=2; plural=(n > 1);" if code.startswith("ar") else "nplurals=2; plural=(n > 1);"
    )
    for msgid in sorted(T):
        po.append(polib.POEntry(msgid=msgid, msgstr=T[msgid][index]))
    return po


def main():
    build_pot().save(str(I18N / f"{MODULE}.pot"))
    build_po("persian", "fa_IR", "Uniom <support@uniom.ir>", 0).save(str(I18N / "fa_IR.po"))
    build_po("arabic", "ar_001", "Uniom <support@uniom.ir>", 1).save(str(I18N / "ar_001.po"))
    print("i18n files written:", len(T), "entries each")


if __name__ == "__main__":
    main()

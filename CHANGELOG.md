# Changelog

## 18.0.1.0.0 (2026-10-29)

Initial release.

* Uniom connections (one API key per messenger account), gateway health check via `getMe`.
* Event automation rules: quotation sent, sale confirmed (PDF), invoice posted (PDF),
  payment received, delivery done, product published, product price changed with
  `editMessageText` in-place editing.
* Message queue with retry/backoff cron, `429 retry_after`, 504 no-retry policy,
  full in/out log and chatter notes.
* Templates with `${object.field}` rendering and per-language variants (en/fa/ar).
* Inbound webhook controller with secret-token verification and contact matching.
* "Send via Uniom" wizard on partners, sale orders, invoices, deliveries.
* Security groups, multi-company record rules, master switch in Settings.
* UI translations: English (source), Persian (fa_IR), Arabic (ar_001).

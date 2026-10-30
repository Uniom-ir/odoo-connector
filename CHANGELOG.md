# Changelog

## 18.0.1.2.1 (2026-10-30)

* Demo: the prospect conversation now keeps its intended 9-hour-old timestamp
  (the failed demo message had no date, so it sorted first as "now").
* Store screenshots of the messenger dashboard captured live with DOM
  render assertions; superseded kanban/form conversation shots removed.
* Translations regenerated from a fresh Odoo export (281 terms; all
  dashboard strings translated in fa/ar).

## 18.0.1.2.0 (2026-10-30)

* **Messenger dashboard**: the Conversations menu now opens a WhatsApp-Web-style
  two-pane client action (OWL) — conversation list with avatars, previews and
  counters on one side; chat **bubbles** (incoming left, outgoing right) with
  per-message state icons and a bottom composer (Enter to send) on the other.
  Auto-refreshes every 8 s; fully mirrored under RTL.
* The kanban/form views remain available behind the dashboard's Manage button.
* New `action_send_dashboard_reply` on uniom.chat (reply pipeline shared with
  the form reply box); tests extended (53 total).

## 18.0.1.1.1 (2026-10-30)

* Fix: conversations kanban crashed on render (kanban template name and the
  removed `kanban_image` helper) — now a plain `/web/image` avatar.
* Fix: inbound chat ids are canonicalized, so differently-spelled gateway ids
  never split a conversation; explicit thread links are trusted on create.
* Uniqueness constraint on (connection, chat id) with a savepoint-safe
  race recovery; inbound records anchored to the connection's company.
* Reply box reports failures and keeps failed drafts queued instead of
  clearing silently; drafts validated before any send.
* Settings "Connect Account" gated to Uniom managers; misc hardening.

## 18.0.1.1.0 (2026-10-30)

* Conversations: messenger-style UI (WhatsApp-connector parity) — every
  inbound/outbound message auto-opens a thread, kanban of conversations,
  thread form with IN/OUT badges and a **reply box** that sends via Uniom.
* **Connect Uniom Account** wizard: login-style onboarding (API key +
  Connect; gateway-confirmed account name), from the Uniom menu and Settings.
* Partner smart button now opens their conversations.
* Translations extended to 272 terms (fa/ar), new screenshots, go-to-market
  notes removed from the public repo.

## 18.0.1.0.0 (2026-10-29)

Initial release.

* Uniom connections (one API key per messenger account), gateway health check via `getMe`.
* Event automation rules: quotation sent, sale confirmed (PDF), invoice posted (PDF),
  payment received, delivery done, product published, product price changed with
  `editMessageText` in-place editing.
* Message queue with retry/backoff cron, `429 retry_after`, 504 no-retry policy,
  full in/out log and chatter notes.
* Templates with `{{ object.field }}` rendering and per-language variants (en/fa/ar).
* Inbound webhook controller with secret-token verification and contact matching.
* "Send via Uniom" wizard on partners, sale orders, invoices, deliveries.
* Security groups, multi-company record rules, master switch in Settings.
* UI translations: English (source), Persian (fa_IR), Arabic (ar_001).
* Hardening: SSRF-guarded HTTP client (public hosts only, no redirects,
  parser-confusion resistant), allowlisted PDF reports with per-user record
  access checks, API-key-safe error reporting, webhook auth-before-parse
  with size cap.

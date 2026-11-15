# Changelog

## 19.0.2.0.2 (2026-11-15)

Odoo 19 series: same features as 18.0.2.0.2, ported to the 19.0 APIs:

* Contacts use the unified `phone` field (`res.partner.mobile` removed).
* Uniqueness via `models.Constraint` (`_sql_constraints` unsupported).
* Groups without `category_id`; system admins inherit Uniom management
  (19 no longer auto-assigns new-app groups).
* Search views use the bare `<group>` element (`expand`/`string` gone).
* Display-name search uses `odoo.fields.Domain` (osv deprecated).
* Suite: 106 tests green; Persian/Arabic at 580/580 user-facing terms.

## 18.0.2.0.2 (2026-11-15)

Merge-review fixes (backend + frontend teams):

* Read/delivery ticks now work: new 5-minute cron refreshes states for
  recent outbound messages via getMessageStates (was wired to nothing).
* Messenger delete is outbound-only: inbound rows carry gateway ids too,
  so both delete paths now guard on direction.
* Skipped poison updates keep a dead-letter payload on the connection
  for support replay; chatter posts are best-effort guarded.
* History backfill no longer flips directions when the own id is unknown.
* Link-wizard key minting is row-locked against double-click/retried RPC.
* Deep links use the Odoo router (locked key + ROUTE_CHANGE) instead of
  the hash, so chatter links open the right conversation on /odoo/ URLs.
* Wizard/settings translations fixed: whole-term model_terms (42 terms),
  word-boundary substring fallback — no more "نظرسنجیing" corruption.
* Removed dead scroll-pin flag and unused labels; declared the
  decoration dependency in the connections list.
* Suite: 105 tests green; Persian/Arabic at 586/586.

## 18.0.2.0.1 (2026-11-15)

* Polling can no longer wedge on a poison update: the offset hold is now
  bounded (5 retries, then the update is skipped with an error log).
* Wizard follow-up steps run inside a savepoint, so a DB error surfaces
  as a best-effort note instead of aborting the wizard transaction.
* Suite: 102 tests green; Persian/Arabic at 584/584.

## 18.0.2.0.0 (2026-11-15)

Messenger rework — the chat surface is now a real client, live-validated
against api.uniom.ir (Bale) and Odoo 18:

* **Inbound that works everywhere**: getUpdates polling mode (1-min cron,
  offset persisted, 409 conflict backoff) alongside webhook; the setup
  wizard picks a mode, falls back to polling when the URL is not public,
  and seeds conversations from getDialogs.
* **Unread that means unread**: per-message read state, per-chat counters,
  total pill, mark-read on open (plus best-effort markChatRead).
* **Media**: photo/document/video/audio/voice/sticker/location/contact/poll
  inbound with captions-or-labels, getFile downloads into attachments;
  composer sends photos/documents via sendPhoto/sendDocument.
* **Presence**: last-seen label/timestamp from getChatActivity, synced on
  open and by a 6-hour cron; typing action broadcast while composing.
* **History**: per-chat backfill from getChatHistory, deduped by gateway
  id (ids now stored as text — Bale ids exceed int32).
* **Live updates**: bus push (ids only, no body leak) with polling
  fallback; day dividers, ticks, retry/cancel bubbles, optimistic sends.
* **Discuss-native**: every conversation mirrors into a Discuss channel
  (visible under Direct Messages); replies typed in Discuss forward back
  through the Uniom queue with loop guards; company-scoped membership.
* **Platform brands**: per-messenger icons (Bale/Rubika/Eitaa/Soroush+/
  Telegram) in sidebar rows, thread header and kanban cards.
* **In-Odoo linking**: Link Messenger Account wizard mirrors the Uniom
  panel — Uniom phone+OTP sign-in (cookie session + CSRF), messenger
  phone+OTP/2FA-password/bot-token linking, API key minting, connection
  creation with dialog seeding.
* **Odoo integration**: failure to-dos on business records, chatter posts
  with deep links, connection health (webhook status, poll errors,
  dialog sync), Persian/Arabic at 579/579.
* Registering a webhook never drops the pending queue anymore.
* **Hardening (2026-11-15)**: company record rules on chats/messages,
  API-key redaction in logs/errors, per-chat gateway-id scoping for
  edits/backfill, wizard inbound activation with polling fallback,
  poll offset held on failed updates for retry, friendly gateway errors
  everywhere, secrets wiped from the link wizard, audio/video players in
  bubbles, profile-photo caching, read/delivery states from
  getMessageStates, seen/view counts, message edit/delete from the
  thread, RTL + English README split.
* Suite: 101 tests green (polling, media, presence, dialogs, history,
  read receipts, failure activities, attachments, link wizard, Discuss,
  review-fix regressions).

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

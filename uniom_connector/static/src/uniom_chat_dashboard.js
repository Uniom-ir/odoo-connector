/** @odoo-module **/
// Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
// copyright and licensing details.
import { Component, onMounted, onWillStart, onWillUnmount, proxy, signal } from "@odoo/owl";
import { router, routerBus } from "@web/core/browser/router";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, formatDate } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { user } from "@web/core/user";

const { DateTime } = luxon;

// Chat fields guaranteed by the backend contract. `avatar_url` is computed
// server-side from the linked contact or the messenger profile picture.
const CHAT_FIELDS = [
    "display_name",
    "chat_id",
    "chat_type",
    "partner_id",
    "connection_id",
    "messenger_title",
    "messenger_username",
    "messenger_photo_url",
    "avatar_url",
    "last_message_preview",
    "last_message_date",
    "last_message_kind",
    "unread_count",
    "last_seen_label",
    "last_seen_at",
    "last_seen_is_exact",
    "presence_updated_at",
];

// Optional helpers some backends expose; they are only requested when the
// server actually defines them (see `detectOptionalChatFields`).
const OPTIONAL_CHAT_FIELDS = ["last_message_direction", "last_message_state"];

const MESSAGE_FIELDS = [
    "direction",
    "body",
    "message_kind",
    "state",
    "error_message",
    "date_sent",
    "date_edited",
    "edit_count",
    "seen_state",
    "seen_count",
    "views_count",
    "deleted_on_messenger",
    "create_date",
    "uniom_message_id",
    "uniom_update_id",
    "is_read",
    "attachment_ids",
    "chat_session_id",
];

const ATTACHMENT_FIELDS = ["name", "mimetype", "file_size"];

const CHAT_LIMIT = 150;
const THREAD_PAGE_SIZE = 30;
// The thread is chronological by send time, not by local id: history
// backfill inserts old gateway messages with brand-new local ids, so id order
// would put them at the end of the conversation. Unresolved outbound rows have
// no date_sent yet and PostgreSQL sorts NULLs first on DESC, which keeps them
// at the newest end of the thread.
const MESSAGE_ORDER = "date_sent desc, id desc";
const SEARCH_DEBOUNCE_MS = 300;
const POLL_INTERVAL_MS = 8000;
const TYPING_THROTTLE_MS = 5000;
const PIN_TOLERANCE_PX = 48;

// Messenger platforms with a bundled official icon, mirroring the `platform`
// selection on uniom.connection. Filenames follow the Uniom frontend assets
// (bale/rubika ship PNG, the rest SVG). Unknown platforms get the dot.
const PLATFORM_ICON_FILES = {
    bale: "bale.png",
    rubika: "rubika.png",
    eitaa: "eitaa.svg",
    soroushplus: "soroushplus.svg",
    telegram: "telegram.svg",
};
const PLATFORM_ICON_BASE = "/uniom_connector/static/img/platforms/";

const KIND_ICONS = {
    photo: "photo_camera",
    document: "description",
    video: "videocam",
    audio: "volume_up",
    voice: "mic",
    sticker: "sentiment_satisfied",
    location: "location_on",
    contact: "person",
    poll: "bar_chart",
    text: "chat_bubble",
    unknown: "chat_bubble",
};

/**
 * WhatsApp-style two-pane messenger: conversation list on one side, chat
 * bubbles with a composer on the other. Data lives on uniom.chat /
 * uniom.message; sending goes through the same queued, retried pipeline as
 * every other Uniom message.
 *
 * The list is fetched server-side (debounced search, filter tabs and a
 * per-connection filter); the thread is refreshed by the bus notification
 * `uniom.message/new` with an 8 second polling fallback while the tab is
 * visible. No message body ever crosses the bus — the payload only carries
 * ids, so the client re-reads through the ORM and record rules apply.
 */
export class UniomChatDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notificationService = useService("notification");
        this.busService = useService("bus_service");
        // keep the deep-link chat id across router pushes (back/forward,
        // canonical /odoo/ URLs); unlocked keys are dropped from the URL
        router.addLockedKey("uniom_chat_id");

        this.threadRef = signal.ref();
        this.composerRef = signal.ref();
        this.fileInputRef = signal.ref();

        this._timers = {};
        this._destroyed = false;
        this._chatsSeq = 0;
        this._chatsLoadedOnce = false;
        this._pendingSeq = 0;
        this._polling = false;
        this._lastTypingAt = 0;
        this._lastErrorAt = 0;
        this._attachmentCache = new Map();
        this._optionalChatFields = [];
        this._displayNameSearchable = false;
        this._locale = user.lang || "en-US";

        this.state = proxy({
            chats: [],
            connections: [],
            activeId: null,
            activeChat: null,
            messages: [],
            search: "",
            filter: "all",
            connectionId: null,
            outgoingSide: "right",
            loadingChats: true,
            loadingMessages: false,
            loadingOlder: false,
            refreshing: false,
            sending: false,
            uploading: false,
            syncingPresence: false,
            totalUnread: 0,
            failedChatIds: [],
            hasMoreHistory: true,
            brokenAvatars: [],
            lastDirectionByChat: {},
        });

        onWillStart(async () => {
            await this.detectOptionalChatFields();
            await Promise.all([
                this.loadConnections(),
                this.loadOutgoingSide(),
                this.refreshSidebar(),
            ]);
        });

        onMounted(() => {
            this.startBus();
            this.startPolling();
            this._onVisibilityChange = () => this.onVisibilityChange();
            this._onRouteChange = () => this.onRouteChange();
            document.addEventListener("visibilitychange", this._onVisibilityChange);
            routerBus.addEventListener("ROUTE_CHANGE", this._onRouteChange);
            const chatId = this.routeChatId();
            if (chatId) {
                this.openChatById(chatId);
            }
        });

        onWillUnmount(() => {
            this._destroyed = true;
            this.stopBus();
            this.stopPolling();
            this.clearTimer("search");
            this.clearTimer("sidebarRefresh");
            this.clearTimer("threadSync");
            if (this._onVisibilityChange) {
                document.removeEventListener("visibilitychange", this._onVisibilityChange);
            }
            if (this._onRouteChange) {
                routerBus.removeEventListener("ROUTE_CHANGE", this._onRouteChange);
            }
        });
    }

    // ------------------------------------------------------------------
    // Static labels (every user-facing string is translated)
    // ------------------------------------------------------------------
    get labels() {
        return {
            conversations: _t("Conversations"),
            searchPlaceholder: _t("Search conversations..."),
            all: _t("All"),
            unread: _t("Unread"),
            failed: _t("Failed"),
            allConnections: _t("All connections"),
            refresh: _t("Refresh"),
            newChat: _t("New conversation"),
            manage: _t("Manage connections"),
            emptyTitle: _t("No conversations yet"),
            emptyHint: _t(
                "Connect your messenger account and the conversations will show up here."
            ),
            emptyFiltered: _t("No conversations match your search or filters."),
            loading: _t("Loading conversations..."),
            failedBadge: _t("Some messages could not be sent"),
            selectChat: _t("Select a conversation to start chatting."),
            noMessages: _t("No messages yet. Say hello!"),
            loadOlder: _t("Load older messages"),
            openPartner: _t("Open contact"),
            linkPartner: _t("Link contact"),
            syncPresence: _t("Sync presence"),
            composerPlaceholder: _t("Type a message"),
            send: _t("Send"),
            sending: _t("Sending..."),
            attach: _t("Attach a file"),
            uploading: _t("Uploading..."),
            retry: _t("Retry"),
            cancel: _t("Cancel"),
            edit: _t("Edit"),
            delete: _t("Delete"),
            editPrompt: _t("Edit message"),
            deleteConfirm: _t("Delete this message from the messenger?"),
            sent: _t("Sent"),
            delivered: _t("Delivered"),
            seen: _t("Seen"),
            read: _t("Read"),
            edited: _t("edited"),
            today: _t("Today"),
            yesterday: _t("Yesterday"),
            online: _t("Online"),
            offline: _t("Offline"),
            presenceUnavailable: _t("Presence unavailable"),
            lastSeenRecently: _t("Last seen recently"),
            lastSeenWeek: _t("Last seen within a week"),
            lastSeenMonth: _t("Last seen within a month"),
            lastSeenLongAgo: _t("Last seen a long time ago"),
            photo: _t("Photo"),
            document: _t("Document"),
            video: _t("Video"),
            audio: _t("Audio"),
            voice: _t("Voice message"),
            sticker: _t("Sticker"),
            location: _t("Location"),
            contact: _t("Contact"),
            poll: _t("Poll"),
            text: _t("Text message"),
            unknown: _t("Message"),
            messageNotSent: _t("Message not sent"),
            failedMessage: _t("Failed"),
            canceled: _t("Canceled"),
            queued: _t("Queued"),
            attachmentNotSent: _t("Attachment not sent"),
            uploadFailed: _t("The file could not be uploaded."),
            chatNotFound: _t("The requested conversation could not be found."),
            genericError: _t("Something went wrong. Please try again."),
            groupChat: _t("Group"),
            supergroupChat: _t("Supergroup"),
            channelChat: _t("Channel"),
        };
    }

    get chatFields() {
        return CHAT_FIELDS.concat(this._optionalChatFields);
    }

    get connectionOptions() {
        return this.state.connections.filter((connection) => connection.active !== false);
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------
    async detectOptionalChatFields() {
        this._optionalChatFields = [];
        this._displayNameSearchable = false;
        try {
            const fields = await this.orm.call(
                "uniom.chat",
                "fields_get",
                [["display_name"].concat(OPTIONAL_CHAT_FIELDS)],
                { attributes: ["searchable"] }
            );
            this._optionalChatFields = OPTIONAL_CHAT_FIELDS.filter(
                (name) => name in (fields || {})
            );
            // A computed display_name without a search method or store flag
            // is ignored by the ORM; partner_id.name covers that case below.
            this._displayNameSearchable = Boolean(
                fields && fields.display_name && fields.display_name.searchable
            );
        } catch {
            // Contract-only backend: ticks simply have no direction to show.
            this._optionalChatFields = [];
            this._displayNameSearchable = false;
        }
    }

    async loadConnections() {
        try {
            this.state.connections = await this.orm.searchRead(
                "uniom.connection",
                [],
                ["name", "platform", "active"],
                { order: "sequence, id" }
            );
        } catch {
            this.state.connections = [];
        }
    }

    async loadOutgoingSide() {
        try {
            // via uniom.chat: ir.config_parameter is settings-only and
            // regular Uniom users would hit AccessError here
            const side = await this.orm.call("uniom.chat", "get_outgoing_side", []);
            this.state.outgoingSide = side === "left" ? "left" : "right";
        } catch {
            this.state.outgoingSide = "right";
        }
    }

    bubbleSide(direction) {
        // WhatsApp default: own messages right, incoming left; the
        // Settings switch swaps both sides at once
        const outgoingRight = this.state.outgoingSide !== "left";
        if (direction === "out") {
            return outgoingRight ? "out" : "in";
        }
        return outgoingRight ? "in" : "out";
    }

    chatDomain() {
        const domain = [];
        if (this.state.filter === "unread") {
            domain.push(["unread_count", ">", 0]);
        } else if (this.state.filter === "failed") {
            domain.push(["message_ids.state", "=", "error"]);
        }
        if (this.state.connectionId) {
            domain.push(["connection_id", "=", this.state.connectionId]);
        }
        const query = (this.state.search || "").trim();
        if (query) {
            const leaves = [];
            if (this._displayNameSearchable) {
                leaves.push(["display_name", "ilike", query]);
            }
            leaves.push(
                ["partner_id.name", "ilike", query],
                ["chat_id", "ilike", query],
                ["messenger_title", "ilike", query],
                ["last_message_preview", "ilike", query]
            );
            for (let index = 0; index < leaves.length - 1; index += 1) {
                domain.push("|");
            }
            domain.push(...leaves);
        }
        return domain;
    }

    async refreshSidebar() {
        const seq = ++this._chatsSeq;
        if (!this.state.chats.length && !this._chatsLoadedOnce) {
            this.state.loadingChats = true;
        }
        const unreadPromise = this.orm
            .searchRead("uniom.chat", [["unread_count", ">", 0]], ["unread_count"])
            .catch(() => []);
        try {
            const [chats, unreadChats, failedChatIds] = await Promise.all([
                this.orm.searchRead("uniom.chat", this.chatDomain(), this.chatFields, {
                    limit: CHAT_LIMIT,
                    order: "last_message_date desc nulls last, id desc",
                }),
                unreadPromise,
                this.loadFailedChatIds(),
            ]);
            if (this._destroyed || seq !== this._chatsSeq) {
                return;
            }
            this.state.chats = chats;
            this.state.totalUnread = unreadChats.reduce(
                (total, chat) => total + (chat.unread_count || 0),
                0
            );
            this.state.failedChatIds = failedChatIds;
            this.syncActiveChatFromList();
        } catch (error) {
            if (!this._destroyed) {
                this.notifyError(error);
            }
        } finally {
            if (seq === this._chatsSeq) {
                this.state.loadingChats = false;
                this._chatsLoadedOnce = true;
            }
        }
    }

    async loadFailedChatIds() {
        try {
            const ids = await this.orm.call("uniom.message", "get_failed_chat_ids", [], {
                limit: 200,
            });
            return (ids || []).filter(Boolean);
        } catch {
            return [];
        }
    }

    syncActiveChatFromList() {
        if (!this.state.activeId) {
            return;
        }
        const fresh = this.state.chats.find((chat) => chat.id === this.state.activeId);
        if (fresh) {
            this.state.activeChat = { ...(this.state.activeChat || {}), ...fresh };
        }
    }

    async refresh() {
        if (this.state.refreshing) {
            return;
        }
        this.state.refreshing = true;
        try {
            await Promise.all([this.refreshSidebar(), this.syncThread()]);
        } finally {
            this.state.refreshing = false;
        }
    }

    async refreshThread() {
        await this.refresh();
    }

    // ------------------------------------------------------------------
    // Conversations
    // ------------------------------------------------------------------
    async openChat(chatId) {
        chatId = Number(chatId);
        if (!chatId) {
            return;
        }
        const isSame = this.state.activeId === chatId;
        this.state.activeId = chatId;
        const listed = this.state.chats.find((chat) => chat.id === chatId);
        if (listed) {
            this.state.activeChat = listed;
        }
        this.updateRoute(chatId);
        if (!isSame) {
            this._attachmentCache = new Map();
            this.state.messages = [];
            this.state.hasMoreHistory = true;
            await this.loadThread();
        }
        this.markRead(chatId);
        this.focusComposer();
    }

    async openChatById(chatId) {
        chatId = Number(chatId);
        if (!chatId) {
            return;
        }
        let chat = this.state.chats.find((item) => item.id === chatId);
        if (!chat) {
            try {
                const records = await this.orm.read("uniom.chat", [chatId], this.chatFields);
                chat = records && records[0];
            } catch (error) {
                this.notifyError(error);
                return;
            }
        }
        if (!chat) {
            this.notificationService.add(this.labels.chatNotFound, {
                title: _t("Uniom"),
                type: "warning",
            });
            return;
        }
        if (!this.state.chats.some((item) => item.id === chat.id)) {
            this.state.chats = [chat, ...this.state.chats];
        }
        await this.openChat(chat.id);
    }

    async loadThread() {
        const chatId = this.state.activeId;
        if (!chatId) {
            return;
        }
        this.state.loadingMessages = true;
        try {
            const rows = await this.orm.searchRead(
                "uniom.message",
                [["chat_session_id", "=", chatId]],
                MESSAGE_FIELDS,
                { limit: THREAD_PAGE_SIZE, order: MESSAGE_ORDER }
            );
            if (this._destroyed || this.state.activeId !== chatId) {
                return;
            }
            const messages = await this.decorateMessages(rows);
            if (this._destroyed || this.state.activeId !== chatId) {
                return;
            }
            this.state.messages = messages;
            this.state.hasMoreHistory = rows.length >= THREAD_PAGE_SIZE;
            this.rememberLastDirection(chatId, messages);
            await this.nextFrame();
            this.scrollToBottom();
        } catch (error) {
            this.notifyError(error);
        } finally {
            if (this.state.activeId === chatId) {
                this.state.loadingMessages = false;
            }
        }
    }

    /**
     * Re-read the newest page of the thread and merge it with everything the
     * user already loaded. Merging by record id (and re-sorting by send time)
     * keeps backfilled history in place while picking up state changes and new
     * messages. The viewport is preserved unless the user was pinned to the
     * bottom.
     */
    async syncThread() {
        const chatId = this.state.activeId;
        if (!chatId) {
            return;
        }
        const threadEl = this.threadRef();
        const wasPinned = threadEl ? this.isPinnedToBottom() : true;
        const previousTop = threadEl ? threadEl.scrollTop : 0;
        const loadedBefore = this.state.messages.filter((message) => !message.optimistic).length;
        try {
            const rows = await this.orm.searchRead(
                "uniom.message",
                [["chat_session_id", "=", chatId]],
                MESSAGE_FIELDS,
                { limit: THREAD_PAGE_SIZE, order: MESSAGE_ORDER }
            );
            if (this._destroyed || this.state.activeId !== chatId) {
                return;
            }
            const messages = await this.decorateMessages(rows);
            if (this._destroyed || this.state.activeId !== chatId) {
                return;
            }
            const merged = new Map();
            for (const message of this.state.messages) {
                if (!message.optimistic) {
                    merged.set(message.id, message);
                }
            }
            for (const message of messages) {
                merged.set(message.id, message);
            }
            this.state.messages = this.applyDayDividers(
                this.sortMessages([
                    ...merged.values(),
                    ...this.state.messages.filter((message) => message.optimistic),
                ])
            );
            if (loadedBefore <= THREAD_PAGE_SIZE) {
                this.state.hasMoreHistory = rows.length >= THREAD_PAGE_SIZE;
            }
            this.rememberLastDirection(chatId, this.state.messages);
            await this.nextFrame();
            if (wasPinned) {
                this.scrollToBottom();
            } else if (this.threadRef()) {
                this.threadRef().scrollTop = previousTop;
            }
        } catch (error) {
            this.notifyError(error);
        }
    }

    /**
     * Backfill from the gateway through `action_load_history`, then read the
     * page of dated messages immediately older than the oldest loaded one.
     * Paging by date_sent (not local id) is what makes backfilled history
     * land in the right place: the inserted rows carry new local ids.
     */
    async loadOlder() {
        const chatId = this.state.activeId;
        if (!chatId || this.state.loadingOlder || !this.state.hasMoreHistory) {
            return;
        }
        const loaded = this.state.messages.filter((message) => !message.optimistic);
        const dated = loaded.filter((message) => message.date_sent);
        if (!dated.length) {
            this.state.hasMoreHistory = false;
            return;
        }
        const oldest = dated.reduce(
            (candidate, message) =>
                message.timestamp < candidate.timestamp ? message : candidate,
            dated[0]
        );
        const sameDateCount = dated.filter(
            (message) => message.date_sent === oldest.date_sent
        ).length;
        const threadEl = this.threadRef();
        const previousHeight = threadEl ? threadEl.scrollHeight : 0;
        const previousTop = threadEl ? threadEl.scrollTop : 0;
        this.state.loadingOlder = true;
        try {
            await this.orm.call("uniom.chat", "action_load_history", [[chatId]], {
                limit: THREAD_PAGE_SIZE,
                before_uniom_id: oldest.uniom_message_id || null,
            });
            const rows = await this.orm.searchRead(
                "uniom.message",
                [
                    ["chat_session_id", "=", chatId],
                    ["date_sent", "<=", oldest.date_sent],
                ],
                MESSAGE_FIELDS,
                {
                    limit: THREAD_PAGE_SIZE + sameDateCount,
                    order: MESSAGE_ORDER,
                }
            );
            if (this._destroyed || this.state.activeId !== chatId) {
                return;
            }
            const knownIds = new Set(loaded.map((message) => message.id));
            const pageRows = rows
                .filter((row) => !knownIds.has(row.id))
                .slice(0, THREAD_PAGE_SIZE);
            const messages = await this.decorateMessages(pageRows);
            if (this._destroyed || this.state.activeId !== chatId) {
                return;
            }
            const merged = new Map(loaded.map((message) => [message.id, message]));
            for (const message of messages) {
                merged.set(message.id, message);
            }
            this.state.messages = this.applyDayDividers(
                this.sortMessages([
                    ...merged.values(),
                    ...this.state.messages.filter((message) => message.optimistic),
                ])
            );
            this.state.hasMoreHistory = pageRows.length >= THREAD_PAGE_SIZE;
            await this.nextFrame();
            if (this.threadRef()) {
                this.threadRef().scrollTop =
                    this.threadRef().scrollHeight - previousHeight + previousTop;
            }
        } catch (error) {
            this.notifyError(error);
        } finally {
            this.state.loadingOlder = false;
        }
    }

    async markRead(chatId) {
        try {
            await this.orm.call("uniom.chat", "action_mark_read", [[chatId]]);
        } catch {
            return;
        }
        const listed = this.state.chats.find((chat) => chat.id === chatId);
        if (listed) {
            listed.unread_count = 0;
        }
        if (this.state.activeChat && this.state.activeChat.id === chatId) {
            this.state.activeChat = { ...this.state.activeChat, unread_count: 0 };
        }
        try {
            const unreadChats = await this.orm.searchRead(
                "uniom.chat",
                [["unread_count", ">", 0]],
                ["unread_count"]
            );
            this.state.totalUnread = unreadChats.reduce(
                (total, chat) => total + (chat.unread_count || 0),
                0
            );
        } catch {
            // The pill is cosmetic; leave the previous total.
        }
    }

    async syncPresence() {
        if (!this.state.activeId || this.state.syncingPresence) {
            return;
        }
        this.state.syncingPresence = true;
        try {
            await this.orm.call("uniom.chat", "action_sync_presence", [[this.state.activeId]]);
            await this.refreshSidebar();
        } catch (error) {
            this.notifyError(error);
        } finally {
            this.state.syncingPresence = false;
        }
    }

    // ------------------------------------------------------------------
    // Sidebar interactions
    // ------------------------------------------------------------------
    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.clearTimer("search");
        this._timers.search = window.setTimeout(
            () => this.refreshSidebar(),
            SEARCH_DEBOUNCE_MS
        );
    }

    setFilter(filter) {
        if (this.state.filter === filter) {
            return;
        }
        this.state.filter = filter;
        this.refreshSidebar();
    }

    onConnectionChange(ev) {
        const value = ev.target.value;
        this.state.connectionId = value ? Number(value) : null;
        this.refreshSidebar();
    }

    onChatKeydown(ev, chatId) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.openChat(chatId);
        }
    }

    onAvatarError(chatId) {
        if (!this.state.brokenAvatars.includes(chatId)) {
            this.state.brokenAvatars.push(chatId);
        }
    }

    // ------------------------------------------------------------------
    // Bus + polling
    // ------------------------------------------------------------------
    startBus() {
        this._onBusMessage = (payload) => this.onBusMessage(payload);
        try {
            this.busService.subscribe("uniom.message/new", this._onBusMessage);
        } catch {
            // The polling fallback still keeps the dashboard fresh.
        }
        try {
            const started = this.busService.start();
            if (started && typeof started.catch === "function") {
                started.catch(() => {});
            }
        } catch {
            // Bus unavailable (worker blocked); polling covers it.
        }
    }

    stopBus() {
        if (!this._onBusMessage) {
            return;
        }
        try {
            this.busService.unsubscribe("uniom.message/new", this._onBusMessage);
        } catch {
            // nothing to do
        }
    }

    onBusMessage(payload) {
        if (!payload || this._destroyed) {
            return;
        }
        const chatId = Number(payload.chat_id);
        if (chatId) {
            this.state.lastDirectionByChat[chatId] = payload.direction === "out" ? "out" : "in";
        }
        this.scheduleSidebarRefresh();
        if (chatId && chatId === this.state.activeId) {
            this.scheduleThreadSync();
            if (payload.direction === "in" && payload.state !== "outgoing" && !document.hidden) {
                this.markRead(chatId);
            }
        }
    }

    scheduleSidebarRefresh() {
        this.clearTimer("sidebarRefresh");
        this._timers.sidebarRefresh = window.setTimeout(() => {
            this.refreshSidebar();
        }, 250);
    }

    scheduleThreadSync() {
        this.clearTimer("threadSync");
        this._timers.threadSync = window.setTimeout(() => {
            this.syncThread();
        }, 120);
    }

    startPolling() {
        this.stopPolling();
        this._pollTimer = window.setInterval(() => {
            if (document.hidden) {
                return;
            }
            this.pollRefresh();
        }, POLL_INTERVAL_MS);
    }

    stopPolling() {
        if (this._pollTimer) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    }

    async pollRefresh() {
        if (this._polling || this._destroyed || document.hidden) {
            return;
        }
        this._polling = true;
        try {
            await this.refreshSidebar();
            if (this.state.activeId) {
                await this.syncThread();
            }
        } finally {
            this._polling = false;
        }
    }

    onVisibilityChange() {
        if (document.hidden) {
            this.stopPolling();
            return;
        }
        this.startPolling();
        this.pollRefresh();
        if (this.state.activeId) {
            this.markRead(this.state.activeId);
        }
    }

    onRouteChange() {
        const chatId = this.routeChatId();
        if (chatId && chatId !== this.state.activeId) {
            this.openChatById(chatId);
        }
    }

    routeChatId() {
        const routed = Number(router.current.uniom_chat_id);
        if (Number.isInteger(routed) && routed > 0) {
            return routed;
        }
        // legacy /web# URLs carry the id in the hash
        const match = (window.location.hash || "").match(/uniom_chat_id=(\d+)/);
        return match ? Number(match[1]) : null;
    }

    updateRoute(chatId) {
        try {
            if (Number(router.current.uniom_chat_id) !== chatId) {
                router.replaceState({ uniom_chat_id: chatId });
            }
        } catch {
            // The route is a convenience only.
        }
    }

    // ------------------------------------------------------------------
    // Composer
    // ------------------------------------------------------------------
    focusComposer() {
        window.requestAnimationFrame(() => {
            if (this.composerRef()) {
                this.composerRef().focus();
            }
        });
    }

    onComposerInput(ev) {
        this.autogrow(ev.target);
        this.sendTypingAction();
    }

    onComposerKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.sendReply();
        }
    }

    autogrow(el) {
        if (!el) {
            return;
        }
        el.style.height = "auto";
        const styles = window.getComputedStyle(el);
        const lineHeight = parseFloat(styles.lineHeight) || 20;
        const maxHeight = Math.round(lineHeight * 5);
        el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
        el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
    }

    resetComposerHeight() {
        if (this.composerRef()) {
            this.composerRef().style.height = "";
            this.composerRef().style.overflowY = "";
        }
    }

    clearComposer() {
        if (this.composerRef()) {
            this.composerRef().value = "";
            this.resetComposerHeight();
        }
    }

    restoreComposer(body) {
        if (this.composerRef() && !this.composerRef().value.trim()) {
            this.composerRef().value = body;
            this.autogrow(this.composerRef());
            this.focusComposer();
        }
    }

    sendTypingAction() {
        const chatId = this.state.activeId;
        if (!chatId) {
            return;
        }
        const now = Date.now();
        if (now - this._lastTypingAt < TYPING_THROTTLE_MS) {
            return;
        }
        this._lastTypingAt = now;
        this.orm
            .call("uniom.chat", "action_send_chat_action", [[chatId]], { action: "typing" })
            .catch(() => {});
    }

    async sendReply() {
        const body = (this.composerRef() ? this.composerRef().value : "").trim();
        const chatId = this.state.activeId;
        if (!body || !chatId || this.state.sending || this.state.uploading) {
            return;
        }
        this.state.sending = true;
        this.clearComposer();
        const pending = this.makePendingMessage(body);
        this.state.messages = this.applyDayDividers([...this.state.messages, pending]);
        this.state.lastDirectionByChat[chatId] = "out";
        await this.nextFrame();
        this.scrollToBottom();

        let result = null;
        try {
            result = await this.orm.call("uniom.chat", "action_send_dashboard_reply", [[chatId]], {
                body,
            });
        } catch (error) {
            this.removePendingMessage(pending);
            this.restoreComposer(body);
            this.state.sending = false;
            this.notifyError(error);
            return;
        }
        this.removePendingMessage(pending);
        this.state.sending = false;
        const state = result && result.state;
        if (!result || state === "error" || state === "canceled") {
            this.notificationService.add(
                (result && result.error_message) || _t("The message could not be sent."),
                {
                    title: this.labels.messageNotSent,
                    type: "danger",
                    sticky: true,
                }
            );
        } else if (state !== "sent" || result.error_message) {
            // Queued for an automatic retry, or the gateway outcome is
            // unknown (HTTP 504): warn without pretending it failed.
            this.notificationService.add(
                result.error_message ||
                    _t("The message is queued and will be retried automatically."),
                {
                    title: this.labels.messageNotSent,
                    type: "warning",
                    sticky: true,
                }
            );
        }
        await Promise.all([this.refreshSidebar(), this.syncThread()]);
        this.focusComposer();
    }

    get timeFormat() {
        // Odoo 20 dropped localization.shortTimeFormat; derive HH:mm from the
        // locale time format (strip the seconds token and keep js/luxon as-is).
        return (localization.timeFormat || "HH:mm:ss")
            .replace(/:s{1,2}/, "")
            .replace(/\s+([aApP])$/, " $1");
    }

    makePendingMessage(body) {
        const now = DateTime.local();
        return {
            id: `pending-${++this._pendingSeq}`,
            optimistic: true,
            direction: "out",
            body,
            showBody: true,
            kind: "text",
            message_kind: "text",
            state: "outgoing",
            attachments: [],
            extra: null,
            timestamp: now.toMillis(),
            timeLabel: now.toFormat(this.timeFormat),
            dayLabel: this.dayLabel(now),
            showDay: false,
            error_message: "",
        };
    }

    removePendingMessage(pending) {
        this.state.messages = this.applyDayDividers(
            this.state.messages.filter((message) => message.id !== pending.id)
        );
    }

    openFilePicker() {
        if (this.state.uploading || !this.state.activeId) {
            return;
        }
        if (this.fileInputRef()) {
            this.fileInputRef().click();
        }
    }

    async onFilePicked(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file || !this.state.activeId || this.state.uploading) {
            return;
        }
        const chatId = this.state.activeId;
        const caption = (this.composerRef() ? this.composerRef().value : "").trim();
        this.state.uploading = true;
        try {
            const attachment = await this.uploadAttachment(file, chatId);
            const result = await this.orm.call(
                "uniom.chat",
                "action_send_dashboard_attachment",
                [[chatId]],
                { attachment_id: attachment.id, caption }
            );
            const failed =
                result &&
                ((result.state && result.state !== "sent") || result.error_message);
            if (failed) {
                this.notificationService.add(
                    result.error_message || _t("The attachment could not be sent."),
                    {
                        title: this.labels.attachmentNotSent,
                        type: "warning",
                        sticky: true,
                    }
                );
            } else if (this.state.activeId === chatId) {
                this.clearComposer();
            }
            await Promise.all([this.refreshSidebar(), this.syncThread()]);
        } catch (error) {
            this.notifyError(error);
        } finally {
            this.state.uploading = false;
        }
    }

    async uploadAttachment(file, chatId) {
        const formData = new FormData();
        formData.append("csrf_token", odoo.csrf_token);
        formData.append("model", "uniom.chat");
        formData.append("id", String(chatId));
        formData.append("ufile", file);
        const response = await fetch("/web/binary/upload_attachment", {
            method: "POST",
            body: formData,
            credentials: "same-origin",
        });
        if (!response.ok) {
            throw new Error(_t("Upload failed (HTTP %s).", response.status));
        }
        const payload = await response.json();
        const attachment = Array.isArray(payload) ? payload[0] : payload;
        if (!attachment || attachment.error || !attachment.id) {
            throw new Error((attachment && attachment.error) || this.labels.uploadFailed);
        }
        return attachment;
    }

    async retryMessage(message) {
        try {
            await this.orm.call("uniom.message", "action_send_now", [[message.id]]);
        } catch (error) {
            this.notifyError(error);
            return;
        }
        await Promise.all([this.refreshSidebar(), this.syncThread()]);
    }

    async cancelMessage(message) {
        try {
            if (message.state === "error") {
                // action_cancel only stops queued rows; a failed row is already
                // terminal, so dismissing it means marking it canceled.
                await this.orm.write("uniom.message", [message.id], { state: "canceled" });
            } else {
                await this.orm.call("uniom.message", "action_cancel", [[message.id]]);
            }
        } catch (error) {
            this.notifyError(error);
            return;
        }
        await Promise.all([this.refreshSidebar(), this.syncThread()]);
    }

    async editMessage(message) {
        const current = (message.body || "").trim();
        const edited = window.prompt(this.labels.editPrompt, current);
        if (edited === null) {
            return;
        }
        const text = edited.trim();
        if (!text || text === current) {
            return;
        }
        try {
            await this.orm.call("uniom.message", "action_edit_body", [[message.id]], {
                new_body: text,
            });
        } catch (error) {
            this.notifyError(error);
            return;
        }
        await Promise.all([this.refreshSidebar(), this.syncThread()]);
    }

    async deleteMessage(message) {
        if (!window.confirm(this.labels.deleteConfirm)) {
            return;
        }
        try {
            await this.orm.call("uniom.message", "action_delete_message", [[message.id]]);
        } catch (error) {
            this.notifyError(error);
            return;
        }
        await Promise.all([this.refreshSidebar(), this.syncThread()]);
    }

    // ------------------------------------------------------------------
    // Header actions
    // ------------------------------------------------------------------
    async openPartner() {
        const chat = this.state.activeChat;
        if (!chat) {
            return;
        }
        if (!chat.partner_id) {
            // unlinked thread: open the conversation form focused on the
            // contact field instead of dead-ending on a warning
            this.actionService.doAction({
                type: "ir.actions.act_window",
                name: this.labels.linkPartner,
                res_model: "uniom.chat",
                res_id: chat.id,
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
            });
            return;
        }
        try {
            const action = await this.orm.call("uniom.chat", "action_open_partner", [[chat.id]]);
            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            this.notifyError(error);
        }
    }

    openNewChat() {
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                name: this.labels.newChat,
                res_model: "uniom.send.wizard",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
            },
            {
                onClose: () => this.refresh(),
            }
        );
    }

    openManage() {
        this.actionService.doAction("uniom_connector.action_uniom_connection");
    }

    // ------------------------------------------------------------------
    // Thread / message decoration
    // ------------------------------------------------------------------
    async decorateMessages(rows) {
        const attachmentMap = await this.resolveAttachments(rows);
        const messages = rows.map((row) => this.decorateMessage(row, attachmentMap));
        return this.applyDayDividers(this.sortMessages(messages));
    }

    decorateMessage(row, attachmentMap) {
        const message = { ...row };
        const attachmentIds = Array.isArray(message.attachment_ids)
            ? message.attachment_ids
            : [];
        message.attachments = attachmentIds
            .map((item) => {
                if (item && typeof item === "object") {
                    return item;
                }
                const id = Number(item);
                if (!Number.isFinite(id) || id <= 0) {
                    return null;
                }
                return attachmentMap.get(id) || { id };
            })
            .filter((attachment) => attachment && attachment.id)
            .map((attachment) => this.decorateAttachment(attachment));
        message.kind = message.message_kind || this.inferKind(message);
        const sentAt = this.toDateTime(message.date_sent || message.create_date);
        message.timestamp = sentAt ? sentAt.toMillis() : null;
        message.timeLabel = sentAt ? sentAt.toFormat(this.timeFormat) : "";
        message.dayLabel = sentAt ? this.dayLabel(sentAt) : "";
        message.extra = this.buildExtra(message);
        message.showBody = this.shouldShowBody(message);
        return message;
    }

    /**
     * Media-only rows carry a generated label as body ("Photo",
     * "Document: file.pdf", ...). Do not print it twice under the attachment;
     * real captions still show. Location/contact/poll render as cards.
     */
    shouldShowBody(message) {
        if (!message.body || message.extra) {
            return false;
        }
        if (!message.attachments.length || message.kind === "text") {
            return true;
        }
        const body = message.body.trim();
        const labels = this.labels;
        const plainLabels = [
            labels.photo,
            labels.video,
            labels.audio,
            labels.voice,
            labels.sticker,
        ];
        if (plainLabels.includes(body)) {
            return false;
        }
        if (body === labels.document || body.startsWith(`${labels.document}:`)) {
            return false;
        }
        if (body.startsWith(`${labels.audio}:`)) {
            return false;
        }
        return true;
    }

    async resolveAttachments(rows) {
        const ids = new Set();
        for (const row of rows) {
            if (!Array.isArray(row.attachment_ids)) {
                continue;
            }
            for (const item of row.attachment_ids) {
                if (item && typeof item === "object" && item.id) {
                    this._attachmentCache.set(item.id, item);
                } else if (item !== false && item !== null && item !== undefined) {
                    const id = Number(item);
                    if (Number.isFinite(id) && id > 0) {
                        ids.add(id);
                    }
                }
            }
        }
        const missing = [...ids].filter((id) => !this._attachmentCache.has(id));
        if (missing.length) {
            try {
                const records = await this.orm.read("ir.attachment", missing, ATTACHMENT_FIELDS);
                for (const record of records || []) {
                    this._attachmentCache.set(record.id, record);
                }
            } catch {
                // Unreadable attachments keep a generic download chip below.
            }
        }
        return this._attachmentCache;
    }

    decorateAttachment(attachment) {
        const mimetype = attachment.mimetype || "";
        return {
            ...attachment,
            name: attachment.name || _t("Attachment"),
            isImage: mimetype.startsWith("image/"),
            isAudio: mimetype.startsWith("audio/"),
            isVideo: mimetype.startsWith("video/"),
            contentUrl: `/web/content/${attachment.id}`,
            downloadUrl: `/web/content/${attachment.id}?download=true`,
            sizeLabel: this.formatFileSize(attachment.file_size),
        };
    }

    inferKind(message) {
        if (message.attachments && message.attachments.length) {
            const first = message.attachments[0];
            if (first.isImage) {
                return "photo";
            }
            if (first.isAudio) {
                return "voice";
            }
            if (first.isVideo) {
                return "video";
            }
            return "document";
        }
        return "text";
    }

    applyDayDividers(messages) {
        let previousDay = null;
        for (const message of messages) {
            message.showDay = Boolean(message.dayLabel) && message.dayLabel !== previousDay;
            if (message.dayLabel) {
                previousDay = message.dayLabel;
            }
        }
        return messages;
    }

    /**
     * Chronological order (oldest first). Rows with no date_sent yet (queued
     * or failed outbound) are the newest ones, matching the gateway thread.
     */
    compareMessages(first, second) {
        const firstTime = first.timestamp;
        const secondTime = second.timestamp;
        if (firstTime === null || firstTime === undefined) {
            if (secondTime === null || secondTime === undefined) {
                return Number(first.id) - Number(second.id);
            }
            return 1;
        }
        if (secondTime === null || secondTime === undefined) {
            return -1;
        }
        if (firstTime !== secondTime) {
            return firstTime - secondTime;
        }
        return Number(first.id) - Number(second.id);
    }

    sortMessages(messages) {
        const regular = messages.filter((message) => !message.optimistic);
        const optimistic = messages.filter((message) => message.optimistic);
        regular.sort((first, second) => this.compareMessages(first, second));
        optimistic.sort(
            (first, second) => (first.timestamp || 0) - (second.timestamp || 0)
        );
        return [...regular, ...optimistic];
    }

    /**
     * The sidebar preview tick needs the direction of the last message. The
     * contract does not expose it on uniom.chat, so remember it whenever a
     * thread is loaded/updated (the bus also carries it on live changes).
     */
    rememberLastDirection(chatId, messages) {
        const latest = [...messages].reverse().find((message) => !message.optimistic);
        if (latest && chatId) {
            this.state.lastDirectionByChat[chatId] = latest.direction === "in" ? "in" : "out";
        }
    }

    buildExtra(message) {
        if (message.kind === "location") {
            const data = this.parseJson(message.body);
            const source = data && data.location && typeof data.location === "object"
                ? data.location
                : data;
            const parsed = source || this.parseLocationLabel(message.body);
            if (!parsed) {
                return null;
            }
            const latitude = parsed.latitude !== undefined ? parsed.latitude : parsed.lat;
            const longitude = parsed.longitude !== undefined ? parsed.longitude : parsed.lng;
            if (latitude === undefined || longitude === undefined) {
                return null;
            }
            return {
                type: "location",
                latitude,
                longitude,
                url: `https://www.google.com/maps?q=${encodeURIComponent(
                    latitude
                )},${encodeURIComponent(longitude)}`,
            };
        }
        if (message.kind === "contact") {
            const data = this.parseJson(message.body);
            const source = data && data.contact && typeof data.contact === "object"
                ? data.contact
                : data;
            const parsed = source || this.parseContactLabel(message.body);
            if (!parsed) {
                return null;
            }
            const phone = parsed.phone_number || parsed.phone || "";
            const name =
                parsed.name ||
                [parsed.first_name, parsed.last_name].filter(Boolean).join(" ").trim();
            if (!phone && !name) {
                return null;
            }
            return {
                type: "contact",
                name,
                phone,
                phoneUrl: phone ? `tel:${String(phone).replace(/[^\d+]/g, "")}` : "",
            };
        }
        if (message.kind === "poll") {
            const raw = this.parseJson(message.body);
            const data = raw && raw.poll && typeof raw.poll === "object" ? raw.poll : raw;
            if (data && data.question) {
                const options = (data.options || data.answers || [])
                    .map((option) =>
                        typeof option === "string" ? option : option && option.text
                    )
                    .filter(Boolean);
                return { type: "poll", question: data.question, options };
            }
            const question = this.parsePollLabel(message.body);
            return question ? { type: "poll", question, options: [] } : null;
        }
        return null;
    }

    /** Backend composes a localized "Location: lat, lon" label for media. */
    parseLocationLabel(value) {
        const text = this.labelPayload(value);
        if (!text) {
            return null;
        }
        const match = text.match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
        if (!match) {
            return null;
        }
        return { latitude: match[1], longitude: match[2] };
    }

    /** Backend composes a localized "Contact: name +phone" label. */
    parseContactLabel(value) {
        const text = this.labelPayload(value);
        if (!text) {
            return null;
        }
        const match = text.match(/^(.*?)\s*(\+?\d[\d\s()\-]*)$/);
        if (!match) {
            return null;
        }
        return { name: match[1].trim(), phone: match[2].trim() };
    }

    /** Backend composes a localized "Poll: question" label. */
    parsePollLabel(value) {
        const text = this.labelPayload(value);
        return text || null;
    }

    /**
     * Strip the localized kind prefix ("Location: ", "Contact: ", ...) from a
     * human-readable body. The prefix is translated, so only the delimiter is
     * assumed.
     */
    labelPayload(value) {
        if (typeof value !== "string") {
            return "";
        }
        const text = value.trim();
        const colon = text.indexOf(":");
        return colon >= 0 ? text.slice(colon + 1).trim() : text;
    }

    parseJson(value) {
        if (typeof value !== "string") {
            return null;
        }
        const text = value.trim();
        if (!text || (text[0] !== "{" && text[0] !== "[")) {
            return null;
        }
        try {
            const parsed = JSON.parse(text);
            return parsed && typeof parsed === "object" ? parsed : null;
        } catch {
            return null;
        }
    }

    // ------------------------------------------------------------------
    // Formatting helpers
    // ------------------------------------------------------------------
    toDateTime(value) {
        if (!value) {
            return null;
        }
        try {
            if (value.isLuxonDateTime) {
                return value.isValid ? value : null;
            }
            const dateTime =
                value instanceof Date
                    ? DateTime.fromJSDate(value)
                    : deserializeDateTime(String(value));
            return dateTime && dateTime.isValid ? dateTime : null;
        } catch {
            return null;
        }
    }

    relativeTime(value) {
        const dateTime = this.toDateTime(value);
        if (!dateTime) {
            return "";
        }
        try {
            return dateTime.setLocale(this._locale).toRelative() || "";
        } catch {
            return "";
        }
    }

    dayLabel(value) {
        const dateTime = this.toDateTime(value);
        if (!dateTime) {
            return "";
        }
        const day = dateTime.startOf("day");
        const today = DateTime.local().startOf("day");
        if (day.equals(today)) {
            return this.labels.today;
        }
        if (day.equals(today.minus({ days: 1 }))) {
            return this.labels.yesterday;
        }
        return formatDate(day);
    }

    formatUnread(value) {
        const count = Number(value) || 0;
        return count > 99 ? _t("99+") : String(count);
    }

    seenTitle(msg) {
        if (msg.error_message) {
            return msg.error_message;
        }
        const map = {
            read: this.labels.read,
            seen: this.labels.seen,
            delivered: this.labels.delivered,
        };
        return map[msg.seen_state] || this.labels.sent;
    }

    formatFileSize(size) {
        const bytes = Number(size) || 0;
        if (!bytes) {
            return "";
        }
        const units = ["B", "KB", "MB", "GB"];
        let value = bytes;
        let index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index += 1;
        }
        const printed = index === 0 ? String(value) : value.toFixed(1);
        return _t("%(size)s %(unit)s", { size: printed, unit: units[index] });
    }

    kindIcon(kind) {
        return KIND_ICONS[kind] || KIND_ICONS.unknown;
    }

    kindLabel(kind) {
        const labels = this.labels;
        const map = {
            photo: labels.photo,
            document: labels.document,
            video: labels.video,
            audio: labels.audio,
            voice: labels.voice,
            sticker: labels.sticker,
            location: labels.location,
            contact: labels.contact,
            poll: labels.poll,
            text: labels.text,
            unknown: labels.unknown,
        };
        return map[kind] || labels.unknown;
    }

    lastKindIcon(chat) {
        const kind = chat.last_message_kind;
        if (!kind || kind === "text" || kind === "unknown") {
            return "";
        }
        return this.kindIcon(kind);
    }

    lastKindLabel(chat) {
        return this.kindLabel(chat.last_message_kind || "text");
    }

    lastDirectionIsOut(chat) {
        const direction =
            chat.last_message_direction || this.state.lastDirectionByChat[chat.id] || "";
        return direction === "out";
    }

    isChatFailed(chat) {
        if (this.state.failedChatIds.includes(chat.id)) {
            return true;
        }
        return chat.last_message_state === "error";
    }

    // ------------------------------------------------------------------
    // Avatar / connection / presence helpers
    // ------------------------------------------------------------------
    /**
     * Avatar URL computed server-side (messenger photo, else contact
     * photo when present, else "" → initial-letter avatar in template).
     */
    chatAvatarUrl(chat) {
        // server decides: messenger photo, else contact photo (only when
        // the contact actually has one), else "" → initial-letter avatar
        return chat.avatar_url || "";
    }

    chatInitials(chat) {
        const candidates = [
            chat.display_name,
            chat.messenger_title,
            chat.messenger_username,
        ].map((value) => (value || "").replace(/\s+/g, " ").trim());
        // prefer a real name; a bare numeric chat id ("1269001975") would
        // render as meaningless digits — fall through to the chat icon
        const name = candidates.find(
            (value) => value && !/^[\d\s+@-]+$/.test(value)
        );
        if (!name) {
            return "";
        }
        const words = name.split(" ").filter(Boolean);
        if (words.length === 1) {
            return Array.from(words[0]).slice(0, 2).join("").toUpperCase();
        }
        const first = Array.from(words[0])[0] || "";
        const last = Array.from(words[words.length - 1])[0] || "";
        return (first + last).toUpperCase();
    }

    chatHue(chat) {
        return this.hashHue(chat.display_name || chat.chat_id || "");
    }

    chatAvatarStyle(chat) {
        return `background-color: hsl(${this.chatHue(chat)}, 45%, 45%)`;
    }

    connectionStyle(chat) {
        return `background-color: hsl(${this.connectionHue(chat)}, 55%, 45%)`;
    }

    /**
     * Static badge for a messenger platform. Returns "" when the platform has
     * no bundled icon so templates keep the colored-dot fallback.
     */
    platformIconUrl(platform) {
        const file = PLATFORM_ICON_FILES[platform];
        if (!file) {
            return "";
        }
        return `${PLATFORM_ICON_BASE}${file}`;
    }

    /** Raw platform key of the chat's connection ("" when unavailable). */
    connectionPlatformKey(chat) {
        const connection = this.connectionOf(chat);
        return (connection && connection.platform) || "";
    }

    connectionOf(chat) {
        if (!chat || !chat.connection_id) {
            return null;
        }
        const connectionId = Array.isArray(chat.connection_id)
            ? chat.connection_id[0]
            : chat.connection_id;
        return this.state.connections.find((connection) => connection.id === connectionId) || null;
    }

    connectionName(chat) {
        const connection = this.connectionOf(chat);
        if (connection) {
            return connection.name;
        }
        return Array.isArray(chat.connection_id) ? chat.connection_id[1] : "";
    }

    connectionPlatform(chat) {
        const connection = this.connectionOf(chat);
        return connection ? this.platformLabel(connection.platform) : "";
    }

    connectionHue(chat) {
        return this.hashHue(this.connectionName(chat) || "connection");
    }

    platformLabel(platform) {
        if (!platform) {
            return "";
        }
        const map = {
            bale: _t("Bale"),
            rubika: _t("Rubika"),
            eitaa: _t("Eitaa"),
            soroushplus: _t("Soroush+"),
            telegram: _t("Telegram"),
            other: _t("Other"),
        };
        return map[platform] || platform;
    }

    connectionOptionLabel(connection) {
        const platform = this.platformLabel(connection.platform);
        return platform ? `${connection.name} (${platform})` : connection.name;
    }

    hashHue(value) {
        const text = String(value || "");
        let hash = 0;
        for (const character of text) {
            hash = (hash * 31 + character.codePointAt(0)) % 360;
        }
        return Math.abs(hash) % 360;
    }

    chatTypeLabel(chat) {
        const map = {
            group: this.labels.groupChat,
            supergroup: this.labels.supergroupChat,
            channel: this.labels.channelChat,
        };
        return map[chat.chat_type] || "";
    }

    presenceText(chat) {
        if (!chat) {
            return "";
        }
        const label = chat.last_seen_label || "";
        if (label === "online") {
            return this.labels.online;
        }
        if (chat.last_seen_is_exact && chat.last_seen_at) {
            const relative = this.relativeTime(chat.last_seen_at);
            if (relative) {
                return _t("Last seen %s", relative);
            }
        }
        const map = {
            recently: this.labels.lastSeenRecently,
            last_week: this.labels.lastSeenWeek,
            last_month: this.labels.lastSeenMonth,
            long_ago: this.labels.lastSeenLongAgo,
            offline: this.labels.offline,
        };
        return map[label] || this.labels.presenceUnavailable;
    }

    presenceClass(chat) {
        const label = chat && chat.last_seen_label;
        if (label === "online") {
            return "o_uniom_presence_online";
        }
        if (label === "recently") {
            return "o_uniom_presence_recent";
        }
        if (label) {
            return "o_uniom_presence_offline";
        }
        return "o_uniom_presence_unknown";
    }

    presenceTooltip(chat) {
        if (!chat || !chat.presence_updated_at) {
            return "";
        }
        const relative = this.relativeTime(chat.presence_updated_at);
        return relative ? _t("Presence updated %s", relative) : "";
    }

    // ------------------------------------------------------------------
    // Scrolling / timers
    // ------------------------------------------------------------------
    isPinnedToBottom() {
        const element = this.threadRef();
        if (!element) {
            return true;
        }
        return (
            element.scrollHeight - element.scrollTop - element.clientHeight <= PIN_TOLERANCE_PX
        );
    }

    scrollToBottom() {
        window.requestAnimationFrame(() => {
            const element = this.threadRef();
            if (element) {
                element.scrollTop = element.scrollHeight;
            }
        });
    }

    nextFrame() {
        return new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
    }

    clearTimer(name) {
        if (this._timers[name]) {
            window.clearTimeout(this._timers[name]);
            delete this._timers[name];
        }
    }

    // ------------------------------------------------------------------
    // Errors
    // ------------------------------------------------------------------
    errorMessage(error) {
        if (error && error.data && error.data.message) {
            return error.data.message;
        }
        if (error && error.message) {
            return error.message;
        }
        return this.labels.genericError;
    }

    notifyError(error) {
        // Poll failures would otherwise pop a toast every 8 seconds while the
        // network is down; keep the first one and stay quiet for a while.
        const now = Date.now();
        if (now - this._lastErrorAt < 5000) {
            return;
        }
        this._lastErrorAt = now;
        this.notificationService.add(this.errorMessage(error), {
            title: _t("Uniom"),
            type: "danger",
            sticky: false,
        });
    }
}

UniomChatDashboard.template = "uniom_connector.ChatDashboard";
registry.category("actions").add("uniom.chat_dashboard", UniomChatDashboard);

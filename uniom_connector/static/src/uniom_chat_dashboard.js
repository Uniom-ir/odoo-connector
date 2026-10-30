/** @odoo-module **/
// Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
// copyright and licensing details.
import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * WhatsApp-style two-pane messenger: conversation list on one side, chat
 * bubbles with a composer on the other. Data lives on uniom.chat /
 * uniom.message; sending goes through the same queued, retried pipeline as
 * every other Uniom message.
 */
export class UniomChatDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.threadRef = useRef("thread");
        this.composerRef = useRef("composer");
        this.state = useState({
            chats: [],
            activeId: null,
            activeChat: null,
            messages: [],
            search: "",
        });
        onWillStart(() => this.loadChats());
        onMounted(() => {
            this.timer = setInterval(() => this.refresh(), 8000);
        });
        onWillUnmount(() => clearInterval(this.timer));
    }

    get filteredChats() {
        const query = this.state.search.trim().toLowerCase();
        if (!query) {
            return this.state.chats;
        }
        return this.state.chats.filter(
            (chat) =>
                (chat.display_name || "").toLowerCase().includes(query) ||
                (chat.chat_id || "").toLowerCase().includes(query)
        );
    }

    async loadChats() {
        const chats = await this.orm.call("uniom.chat", "search_read", [], {
            domain: [],
            fields: [
                "display_name",
                "chat_id",
                "partner_id",
                "last_message_preview",
                "last_message_date",
                "message_count",
                "connection_id",
            ],
            order: "last_message_date desc nulls last, id desc",
        });
        this.state.chats = chats.map((chat) => ({
            ...chat,
            avatarUrl: chat.partner_id
                ? `/web/image/res.partner/${chat.partner_id[0]}/image_128/64x64`
                : "",
        }));
    }

    async openChat(chatId) {
        this.state.activeId = chatId;
        this.state.activeChat = this.state.chats.find((chat) => chat.id === chatId) || null;
        await this.loadMessages();
    }

    async loadMessages() {
        if (!this.state.activeId) {
            return;
        }
        this.state.messages = await this.orm.call("uniom.message", "search_read", [], {
            domain: [["chat_session_id", "=", this.state.activeId]],
            fields: ["direction", "body", "date_sent", "create_date", "state", "error_message"],
            order: "id asc",
        });
        this.scrollThread();
    }

    async refresh() {
        await this.loadChats();
        if (this.state.activeId) {
            await this.loadMessages();
        }
    }

    scrollThread() {
        requestAnimationFrame(() => {
            const el = this.threadRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    formatTs(value) {
        if (!value) {
            return "";
        }
        const date = new Date(String(value).replace(" ", "T") + "Z");
        if (isNaN(date)) {
            return value;
        }
        return date.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }

    onComposerKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendReply();
        }
    }

    async sendReply() {
        const body = (this.composerRef.el ? this.composerRef.el.value : "").trim();
        if (!body || !this.state.activeId) {
            return;
        }
        await this.orm.call("uniom.chat", "action_send_dashboard_reply", [this.state.activeId], {
            body,
        });
        if (this.composerRef.el) {
            this.composerRef.el.value = "";
        }
        await this.refresh();
    }

    openManage() {
        this.actionService.doAction("uniom_connector.action_uniom_chat");
    }
}

UniomChatDashboard.template = "uniom_connector.ChatDashboard";
registry.category("actions").add("uniom.chat_dashboard", UniomChatDashboard);

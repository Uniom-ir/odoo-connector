/** @odoo-module **/
// Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
// copyright and licensing details.
import { Component, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Platform picker rendering the LIVE GET /platforms list like the Uniom v2
 * panel: icon button per available messenger. A static Selection cannot do
 * this — Odoo evaluates selection callables on an empty recordset, so the
 * options would never see this wizard's available_platforms JSON.
 *
 * Reads `available_platforms` (JSON [{name, display_name}]) from the same
 * record and writes the picked name into `link_platform`.
 */
export class UniomPlatformPicker extends Component {
    static template = "uniom_connector.PlatformPicker";
    props = useProps(standardFieldProps);

    get platforms() {
        try {
            const raw = this.props.record.data.available_platforms || "[]";
            const list = JSON.parse(raw);
            return Array.isArray(list) ? list.filter((p) => p && p.name) : [];
        } catch {
            return [];
        }
    }

    get emptyText() {
        if (this.props.record.data.mgmt_signed_in) {
            return _t("No messengers available for linking right now.");
        }
        return _t("Sign in first to load the available messengers.");
    }

    platformIcon(name) {
        const files = {
            bale: "bale.png",
            rubika: "rubika.png",
            eitaa: "eitaa.svg",
            soroushplus: "soroushplus.svg",
            telegram: "telegram.svg",
        };
        const file = files[name];
        return file ? `/uniom_connector/static/img/platforms/${file}` : "";
    }

    isActive(name) {
        return this.props.record.data.link_platform === name;
    }

    async pick(name) {
        await this.props.record.update({ link_platform: name });
    }
}

export const uniomPlatformPicker = {
    component: UniomPlatformPicker,
};

registry.category("fields").add("uniom_platform_picker", uniomPlatformPicker);

/**
 * Auth-method radio cards for the chosen platform, from the live
 * `link_auth_options` JSON (v2 auth_types). Same empty-recordset reason
 * as above: a Selection cannot see per-record options.
 */
export class UniomAuthTypeCards extends Component {
    static template = "uniom_connector.AuthTypeCards";
    props = useProps(standardFieldProps);

    get authTypes() {
        try {
            const raw = this.props.record.data.link_auth_options || "[]";
            const list = JSON.parse(raw);
            return Array.isArray(list) ? list.filter((a) => a && a.type) : [];
        } catch {
            return [];
        }
    }

    isActive(type) {
        return this.props.record.data.link_auth_type === type;
    }

    async pick(type) {
        await this.props.record.update({ link_auth_type: type });
    }
}

export const uniomAuthTypeCards = {
    component: UniomAuthTypeCards,
};

registry.category("fields").add("uniom_auth_type_cards", uniomAuthTypeCards);

# Where to sell/publish the Uniom Odoo connector

Research summary (October 2026). Facts marked ⚠ could not be verified
first-hand (site unreachable from the research network) and should be
double-checked before committing to a channel.

## 1. Odoo Apps Store (apps.odoo.com) — primary international channel

* **No listing fee.** Odoo keeps a **30% commission**; you get 70%.
* Self-service publishing at https://apps.odoo.com/apps/upload:
  register the git repo (GitHub: authorize user `online-odoo`;
  GitLab: `OdooApps`), one branch per Odoo version (`17.0`, `18.0`, …).
* Paid apps: minimum price **€9**, currency EUR/USD, license `OPL-1`
  recommended for proprietary (our manifest ships `LGPL-3`, which also
  allows a price). Store price must be ≤ any other channel's price.
* Ranking score needs: icon, thumbnail/cover, license set, rating ≥ 3,
  **HTML description** (`static/description/index.html`, English only —
  already prepared). First screenshot filename ending `_screenshot` becomes
  the hero shot.
* No pre-publication human review; an automated repo scan runs and a
  manifest error unpublishes the whole repo, so never break the manifest on
  a live branch.
* Versions as of Oct 2026: **19.0 mainstream**, 18.0 mature base, 20.0 just
  opened (early listings get visibility). Maintained branches: 18.0/19.0/20.0.
  → recommended: publish 17.0 + 18.0 now, port to 19.0/20.0 next.
* **Iran caveat**: publishing works from Iran (precedents exist), but payouts
  are SWIFT bank transfers against vendor-portal purchase orders ≥ €400;
  sellers in Iran report using foreign bank accounts. ⚠
* Alternative store: theodoostore.com (25% commission, open marketplace).

## 2. Iranian marketplaces — no open "Odoo plugin bazaar" exists

* **rtl-theme.com** and **zhaket.com** are **WordPress-only** ecosystems —
  they cannot carry an Odoo module. (The "Jakub" name you heard doesn't
  resolve to any Iranian Odoo marketplace; the real Odoo-specific sellers
  are below.)
* Realistic Iranian channels for an Odoo module:
  * **Hooshan (hooshangroup.com)** — the best-known Iranian Odoo module
    store; first-party, mostly "contact for price". Approach them for a
    listing/reseller deal.
  * **OdooLearn shop (odoolearn.ir/shop)** — sells Odoo 18/19 modules at
    fixed Toman prices (~900k–4.5M for comparable modules).
  * **Iran Odoo Community shop (shop.odoo-community.ir)** — community-run
    listing place for localization modules. ⚠ prices seen: SMS module
    ~1.8M Toman.
  * **Torob (torob.com)** — not a store but the price-discovery layer;
    listing your own shop's product there drives Iranian buyers.
  * **CafeProzhe** — commission-based custom-development marketplace where
    clients post Odoo module projects.
* Typical Iranian price band for messaging/SMS gateway modules:
  **≈ 0.9–4.5M Toman** one-time.
* No Odoo Gold/Silver partner exists in Iran (sanctions), so an
  "official-looking" channel is not available; positioning as the Uniom
  vendor with your own site + Torob + the stores above is the practical path.

## 3. Recommended launch sequence

1. Push this repo to a public git host, publish **18.0 branch free** on
   apps.odoo.com (fast adoption, reviews, ranking).
2. Add the 17.0 branch (and 19.0/20.0 ports) for coverage.
3. Approach Hooshan/OdooLearn for paid Persian-support listings in Toman.
4. Keep a paid "Pro" variant (OPL-1) if you later want channel analytics,
   Discuss inbox, or per-user inboxes as paid-only features.

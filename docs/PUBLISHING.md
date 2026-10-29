# Publishing checklist — Uniom Messaging Gateway for Odoo

Step-by-step from this repo to a live listing. Everything technical is
already in place (store-format description, screenshots, license, branch per
version, CI).

## 0. Pre-flight (already done)

- [x] Module installs cleanly on Odoo 18.0 and 17.0 (fresh DBs, fa/ar loaded)
- [x] Test suite green (`--test-tags /uniom_connector`): 43/43 on 18.0
- [x] LGPL-3 license + LICENSE file
- [x] `static/description/icon.png` + `index.html` (English, Bootstrap only,
      no external resources) + 6 screenshots named `*_screenshot.png`
- [x] One branch per version: `18.0` (main), `17.0`
- [x] `post_init_hook`, no demo data required for install, `images` listed

## 1. Push to a git host

```bash
git remote add origin git@github.com:uniom/uniom-odoo.git
git push -u origin 18.0 17.0
```

CI (`.github/workflows/ci.yml`) runs the suite on push — wait for the green
check before publishing.

## 2. Odoo Apps store (apps.odoo.com)

1. Create/verify your Odoo account, then open
   <https://apps.odoo.com/apps/upload>.
2. Register the repository `ssh://git@github.com/uniom/uniom-odoo#18.0`.
   On GitHub, grant read to the user **`online-odoo`** for that repo.
3. The scan validates the manifest of every module on the branch; a broken
   manifest unpublishes the whole repo, so never force-push a broken tip.
4. Repeat for `#17.0` — the same module name must be used on both branches.
5. Pricing: the module currently ships free (no `price` key). To sell later:
   set `"price": 49, "currency": "EUR"` (minimum €9) and switch
   `license` to `OPL-1`; the store price must always be ≤ any other channel.
6. Store ranking checklist: icon ✓, screenshots ✓, license ✓, HTML
   description ✓, keep the rating healthy (support buyers within a few days;
   support is mandatory for paid apps).
7. Payouts (paid listings): Odoo keeps 30%; you invoice against vendor-portal
   purchase orders ≥ €400 via international transfer. From Iran there is no
   direct payout rail — plan a foreign entity/account before going paid.

## 3. Iranian market (Toman pricing)

There is no open Iranian Odoo marketplace; work with the first-party stores:

1. **Hooshan** (hooshangroup.com) — best-known Iranian Odoo module store;
   approach for a listing or reseller deal (most items are "contact for
   price").
2. **OdooLearn shop** (odoolearn.ir/shop) — sells fixed-price Odoo 18/19
   modules; comparable messaging modules sit around 0.9–4.5M Toman.
3. **Iran Odoo Community shop** (shop.odoo-community.ir) — community-run
   listing place for localization modules.
4. **Torob** — list your own product page for price discovery.
5. Selling from your own site: bundle installation support (1h setup call +
   webhook registration) as the paid tier, module itself free — matches the
   international free-listing strategy.

RTL-Theme / Zhaket are WordPress-only ecosystems — do not spend time there
for an Odoo product.

## 4. When a new Odoo version lands (19.0 / 20.0)

1. Branch from the newest branch, bump `"version"`, and check the diff:
   - 19.0+ keeps `<list>`; verify renamed xpaths and `ir.cron` fields again
     (18.0 already removed `numbercall`, views removed `<tree>`).
2. Run the suite locally the same way CI does (fresh DB, `--without-demo=all`,
   `--load-language en_US,fa_IR,ar_001`).
3. Push the branch — the store lists it after the scan; publish early when a
   version opens (first movers get visibility).

## 5. Release hygiene

- Bump the manifest version on every change (e.g. `18.0.1.0.1` for fixes).
- Update `CHANGELOG.md`.
- Never delete or rename a branch the store still references (breaks its
  fetch — confirmed store behavior).
- Regenerate translations after adding UI strings:
  `python3 scripts/gen_i18n.py <exported po from Odoo>` (see the script
  header for the export step).

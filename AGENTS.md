# AGENTS.md

`entirius-django-getresponse` (Django app `django_getresponse`) — GetResponse marketing integration of Entirius.
Syncs product catalog, categories, carts, orders and contacts from `django_pim` / `django_checkout` into
GetResponse Shops and Campaigns. Real-time cart/order sync via Django signals, bulk catalog sync via management
commands and Celery tasks. Each channel maps to one or more GetResponse accounts, shops and campaigns.

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label / DB table prefix `django_getresponse` — it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Default: do not commit — git is the user's call.

### Commit Message Format

**NEVER add `Co-Authored-By: Claude ...` (or any other Claude/Anthropic attribution) to commit messages.**

This overrides the default Claude Code behavior of appending a `Co-Authored-By` trailer. Commit messages MUST contain only the user's authored content — no robot footer, no "Generated with Claude Code" line, no co-author trailer.

Same rule applies to PR descriptions: no `Generated with [Claude Code]` footer.

## Architecture

```
src/django_getresponse/
├── apps.py                         # DjangoPricemanagerConfig (sic) — wires signal receivers in ready()
├── settings.py                     # MEDIA_URL passthrough + consent/url-key settings
├── bi.py                           # BI event class
├── admin/                          # Django admin + inline mixins
├── models/                         # Channel, GetResponseAccount/Campaign/Contact/Shop,
│                                   # ProductSync, CategorySync, CartSync, OrderSync
├── services/                       # per-resource sync services + consent gate
├── receivers/                      # post_save on django_checkout.Cart / Order (lazy string sender)
├── tasks/                          # Celery shared_task bulk sync (queue "pim_pull")
├── management/commands/            # sync-shops/-campaigns/-categories/-products
├── dto/                            # cart, category, order, product payload DTOs
└── utils/                          # contact_helpers (email-based contact lookups), sync_helpers
```

Sync direction: most flows push Entirius → GetResponse. Campaigns are pulled GR → Entirius
(so operators don't recreate them locally).

Signal receivers: `apps.py ready()` imports `receivers/` (`post_save` on `django_checkout.Cart` / `Order`); details in
`docs/sync.md`.

| Topic | Where |
|---|---|
| Entities, key fields, relationships, sync status | `docs/data-model.md` |
| Signal receivers, shop and API key resolution | `docs/sync.md` |
| Management commands and their Celery equivalents | `docs/commands.md` |
| Test suite and its settings | `docs/testing.md` |
| Sibling packages and what each is used for | `README.md` § Requirements |


## Settings

| Setting | Default | Purpose |
|---|---|---|
| `GETRESPONSE_MARKETING_CONSENT_GRACE_SECONDS` | `180` | consent grace window before contact creation |
| `GETRESPONSE_USE_CONFIG_URL_KEY` | `False` | variants send parent configurable's url_key |
| `SEND_CART_UID_TO_GETRESPONSE_IN_LINK` | `False` | append `?cart=<uuid>` to cartUrl |

## Gotchas

- `apps.py` class name is `DjangoPricemanagerConfig` — a copy-paste leftover. Django only cares
  about `name = "django_getresponse"`, so wiring works, but the class name is misleading.
- `GetResponseShop.save()` calls `_ensure_custom_fields()` which creates three custom fields
  (`customer_type`, `total_orders_count`, `last_order_date`) in GetResponse on first save after
  the shop is synced. Failure is logged via `ProcessLogger` and swallowed — check logs if custom
  field IDs stay empty.
- `GetResponseShop.locale` returns `external_language.iso2` (sent to GR), while `language` is
  used for DB lookups. Regional language codes like `gb` / `us` must map to an
  `external_language` GR accepts (`en`).
- `GetResponseCampaign.get_for_language(language_iso2, account)` falls back to the campaign with
  `language=NULL` when no language match is found — the null-language row is the catch-all.
  Keep exactly one fallback per account.
- Cart/order receivers require `cart.channel` (or `order.channel`) to be set. Signals skip
  silently when missing — grep process logs for `"has no channel, skipping GR sync"`.
- Cart `cartUrl` is built from `GetResponseShop.domain_url_cart`; empty field → key omitted from
  the payload (not sent blank). The cart UUID is appended as `?cart=<uuid>` only when
  `SEND_CART_UID_TO_GETRESPONSE_IN_LINK` is True.
- `ProductSync` / `CategorySync` FK into `django_pim.Product` / `.ProductCategory` — this module
  will not load without django-pim installed.
- `0002_contact_email_drop_crm_form` is idempotent raw SQL bridging 2.x databases (FK on
  django_crm.Form) to the email-based contact — the squash carries the final state; never
  reintroduce a crm dependency here.

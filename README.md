# entirius-django-getresponse

GetResponse marketing integration for Volkanos: API accounts and campaigns, automatic contact
synchronization, category/product/shop sync from `django_pim`, and cart/order-driven contact
updates via `django_checkout` signals. Works together with `django_crm` (forms and consents).

## Features

- **Account management** — store and manage GetResponse API credentials per shop
- **Campaign management** — sync and configure GetResponse campaigns (multi-language with fallback)
- **Contact sync** — automatic contact creation and custom-field updates
- **Category / product / shop sync** — from `django_pim` (Celery tasks + management commands)
- **Marketing consent gate** — grace-window consent checks before contact creation

## Installation

```shell
pip install entirius-django-getresponse
```

The host service must also install `django_crm` — the two apps are mutually integrated
(crm forms feed contact sync; crm's compatibility layer builds on these models).

## Configuration

Optional settings (see `src/django_getresponse/settings.py`):
`GETRESPONSE_MARKETING_CONSENT_GRACE_SECONDS`, `GETRESPONSE_USE_CONFIG_URL_KEY`,
`SEND_CART_UID_TO_GETRESPONSE_IN_LINK`.

## Development

```shell
make install   # uv sync (incl. extras)
make test      # run tests
make check     # ruff lint + format-check
```

## License

MPL-2.0

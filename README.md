# entirius-django-getresponse

GetResponse marketing integration for Volkanos: API accounts and campaigns, automatic contact
synchronization, category/product/shop sync from `django_pim`, and cart/order-driven contact
updates via `django_checkout` signals. Marketing consent is read from `django_agreements`.

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

The marketing consent gate reads `django_agreements` consent records (per-shop agreement slug;
leave the slug empty to disable the gate for a shop).

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

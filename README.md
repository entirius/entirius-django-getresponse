# entirius-django-getresponse

A Django module that connects Entirius, the open-source modular ecommerce platform, to GetResponse email marketing.
It keeps GetResponse accounts and campaigns, creates and updates contacts, pushes shops, categories and products
from the catalog, and sends carts and orders as they change.

[![PyPI](https://img.shields.io/pypi/v/entirius-django-getresponse.svg)](https://pypi.org/project/entirius-django-getresponse/)
[![Python](https://img.shields.io/pypi/pyversions/entirius-django-getresponse.svg)](https://pypi.org/project/entirius-django-getresponse/)
[![License: MPL-2.0](https://img.shields.io/badge/license-MPL--2.0-blue.svg)](https://github.com/entirius/entirius-django-getresponse/blob/develop/LICENSE)

## What it does

- Stores GetResponse API credentials per sales channel and maps channels to GetResponse shops.
- Pulls campaigns from GetResponse and picks one per language, with a fallback campaign.
- Creates contacts and updates their custom fields when carts and orders are saved.
- Pushes shops, categories and products from the catalog (Celery tasks and management commands).
- Checks marketing consent, with a grace window, before a contact is created.

## Installation

```shell
uv add entirius-django-getresponse
pip install entirius-django-getresponse
```

```python
INSTALLED_APPS = [
    ...
    "django_regional",
    "django_utils",
    "django_pim",
    "django_pricemanager",
    "django_checkout",
    "django_agreements",
    "django_getresponse",
]
```

The module has no URL routes. Optional settings: `GETRESPONSE_MARKETING_CONSENT_GRACE_SECONDS`,
`GETRESPONSE_USE_CONFIG_URL_KEY`, `SEND_CART_UID_TO_GETRESPONSE_IN_LINK`; reference with defaults in
https://github.com/entirius/entirius-django-getresponse/blob/develop/AGENTS.md (section Settings).

The consent gate reads `django_agreements` consent records by a per-shop agreement slug; an empty slug
disables the gate for that shop.

## Quick start

```python
from django_getresponse.models import GetResponseAccount, GetResponseCampaign

account = GetResponseAccount.objects.get(name="main")
campaign = GetResponseCampaign.get_for_language(language_iso2="en", account=account)
```

```shell
python manage.py sync-campaigns-from-getresponse
python manage.py sync-shops-to-getresponse
```

## Requirements

- Python 3.11 or newer, Django 5.0 or newer, PostgreSQL, a Celery worker for the bulk sync tasks.
- Entirius packages pulled in: `entirius-django-checkout` (cart and order signals), `entirius-django-agreements`
  (marketing consent), `entirius-django-pim` (products and categories), `entirius-django-regional` (languages,
  currencies, countries), `entirius-django-utils` (base model, command base), `entirius-django-pricemanager`
  (product prices), `entirius-py-get-response-sdk` (GetResponse REST client), `entirius-py-bievents` and
  `entirius-py-process-logger` (events and logging).

## Documentation

- Module docs: https://github.com/entirius/entirius-django-getresponse/tree/develop/docs
- Entirius documentation: https://docs.entirius.com/
- Releases: https://github.com/entirius/entirius-django-getresponse/releases

## Part of Entirius

This module runs inside the Entirius backend service (Volkanos), next to the checkout and product modules.

- Backend service: https://github.com/entirius/entirius-service-volkanos
- Docker harness: https://github.com/entirius/entirius-zeno
- Sibling modules: https://github.com/entirius/entirius-django-checkout, https://github.com/entirius/entirius-django-pim,
  https://github.com/entirius/entirius-django-agreements

## Development

```shell
make install     # sync dependencies (uv, incl. extras)
make check       # lint + format check (ruff)
make test        # test suite (pytest + pytest-django)
```

Development and agent instructions: https://github.com/entirius/entirius-django-getresponse/blob/develop/AGENTS.md

## License

Mozilla Public License 2.0 (MPL-2.0) — see https://github.com/entirius/entirius-django-getresponse/blob/develop/LICENSE.

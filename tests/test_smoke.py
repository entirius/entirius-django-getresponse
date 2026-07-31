# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Smoke test: every public submodule imports cleanly under a configured Django.

Import-only on purpose — django_agreements is not installed in tests/settings.py
(the consent gate imports it lazily), so no test may touch the DB.
"""

import importlib

import pytest

MODULES = [
    "django_getresponse.apps",
    "django_getresponse.settings",
    "django_getresponse.models",
    "django_getresponse.models.account",
    "django_getresponse.models.campaign",
    "django_getresponse.models.cart_sync",
    "django_getresponse.models.category_sync",
    "django_getresponse.models.channel",
    "django_getresponse.models.contact",
    "django_getresponse.models.order_sync",
    "django_getresponse.models.product_sync",
    "django_getresponse.models.shop",
    "django_getresponse.admin.admin",
    "django_getresponse.admin.mixins",
    "django_getresponse.bi",
    "django_getresponse.dto.cart",
    "django_getresponse.dto.category",
    "django_getresponse.dto.order",
    "django_getresponse.dto.product",
    "django_getresponse.receivers.cart_signals",
    "django_getresponse.receivers.contact_update_signals",
    "django_getresponse.receivers.order_signals",
    "django_getresponse.services.base_sync_service",
    "django_getresponse.services.campaign_sync_service",
    "django_getresponse.services.cart_sync_service",
    "django_getresponse.services.category_sync_service",
    "django_getresponse.services.contact_auto_create_service",
    "django_getresponse.services.contact_custom_fields_service",
    "django_getresponse.services.custom_field_service",
    "django_getresponse.services.marketing_consent_service",
    "django_getresponse.services.order_sync_service",
    "django_getresponse.services.product_sync_service",
    "django_getresponse.services.shop_sync_service",
    "django_getresponse.tasks.sync_campaigns_from_getresponse",
    "django_getresponse.tasks.sync_categories_to_getresponse",
    "django_getresponse.tasks.sync_products_to_getresponse",
    "django_getresponse.tasks.sync_shops_to_getresponse",
    "django_getresponse.utils.contact_helpers",
    "django_getresponse.utils.sync_helpers",
    "django_getresponse.views",
    "django_getresponse.workers",
    "django_getresponse.management.commands.sync-campaigns-from-getresponse",
    "django_getresponse.management.commands.sync-categories-to-getresponse",
    "django_getresponse.management.commands.sync-products-to-getresponse",
    "django_getresponse.management.commands.sync-shops-to-getresponse",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)

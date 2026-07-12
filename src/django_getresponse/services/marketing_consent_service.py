# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Consent gate for GetResponse sync.

Cart/Order push and GR contact creation are blocked until the customer has
granted a configurable marketing consent in django-crm. Resources created
BEFORE consent was granted are never pushed (no backfill), with a tolerance
window (MARKETING_CONSENT_GRACE_SECONDS) to absorb same-request races between
Order/Cart creation and Consent save.

When a shop's `marketing_consent_type_name` is empty, the gate is DISABLED for
that shop: sync proceeds without any consent check (contact is auto-created
from the cart/order email).
"""

from datetime import datetime, timedelta

from django_getresponse.settings import MARKETING_CONSENT_GRACE_SECONDS


def is_consent_required(shop) -> bool:
    """False when the shop has no consent type configured (gate disabled)."""
    return bool(shop and shop.marketing_consent_type_name)


def has_marketing_consent(*, email: str | None, shop, resource_created_at: datetime) -> bool:
    """True if consent is satisfied: either the gate is disabled for this shop,
    or the email granted the shop-configured consent within grace of resource_created_at."""
    from django_crm.models import Consent

    if not is_consent_required(shop):
        return True
    if not email:
        return False
    cutoff = resource_created_at + timedelta(seconds=MARKETING_CONSENT_GRACE_SECONDS)
    return Consent.objects.filter(
        form__email=email,
        consent_type__name=shop.marketing_consent_type_name,
        consent_bool=True,
        updated_at__lte=cutoff,
    ).exists()


def get_consent_type_name_for_channel(*, channel_idx: str | None, language_iso2: str | None = None) -> str:
    """Return the configured consent type name for a (channel, language) shop.

    Resolves the shop by channel matching language OR external_language (see
    get_shop_for_channel_language), then reads its consent type. Falls back to "marketing".
    """
    from django_getresponse.utils.sync_helpers import get_shop_for_channel_language

    shop = get_shop_for_channel_language(channel_idx, language_iso2)
    return shop.marketing_consent_type_name if shop else "marketing"

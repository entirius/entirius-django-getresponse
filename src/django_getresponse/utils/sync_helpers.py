# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Helper functions for sync setup and validation.

This module provides reusable functions for preparing sync operations
with GetResponse (shop, account, API key lookup).
"""

from dataclasses import dataclass
from typing import Optional

from process_logger import ProcessLogger

logger = ProcessLogger("sync_helpers")


@dataclass
class SyncSetup:
    """Container for sync setup data."""

    shop: "GetResponseShop"
    api_key: str


def get_synced_shop_for_channel(channel) -> Optional["GetResponseShop"]:
    """Get first synced GetResponse shop for channel.

    For channels with multiple shops (multi-language), use
    get_synced_shops_for_channel() to get all shops.

    Args:
        channel: Channel instance

    Returns:
        First GetResponseShop or None if not found
    """
    from django_getresponse.models import GetResponseShop

    shop = GetResponseShop.objects.filter(channel__idx=channel.idx, sync_status="synced").first()
    if not shop:
        logger.debug(f"No synced GetResponse shop for channel {channel.idx}")
    return shop


def get_synced_shops_for_channel(channel) -> list["GetResponseShop"]:
    """Get all synced GetResponse shops for channel.

    A channel may have multiple shops (e.g., one per language).
    Use this for bulk syncs (products, categories).
    Use get_synced_shop_for_channel() when you need exactly one shop (cart, order).

    Args:
        channel: Channel instance

    Returns:
        List of GetResponseShop instances (empty if none found)
    """
    from django_getresponse.models import GetResponseShop

    shops = list(
        GetResponseShop.objects.filter(channel__idx=channel.idx, sync_status="synced").select_related(
            "language", "external_language"
        )
    )
    if not shops:
        logger.debug(f"No synced GetResponse shops for channel {channel.idx}")
    return shops


def get_shop_for_checkout(channel, language_code: str | None, currency_code: str | None) -> Optional["GetResponseShop"]:
    """Select the right GR shop for a cart or order.

    Matching priority:
    1. language_code + currency_code (exact match)
    2. currency_code only
    3. first synced shop (fallback)

    language_code comes from checkout data (e.g., "gb", "pl", "us") and matches
    shop.language.iso2. currency_code is ISO 4217 3-letter (e.g., "GBP", "PLN").

    Args:
        channel: Channel instance
        language_code: 2-letter language code from cart/order (or None)
        currency_code: 3-letter currency ISO code from cart/order (or None)

    Returns:
        Best-matching GetResponseShop or None
    """
    from django_getresponse.models import GetResponseShop

    shops = list(
        GetResponseShop.objects.filter(channel__idx=channel.idx, sync_status="synced").select_related(
            "language", "currency"
        )
    )
    if not shops:
        logger.debug(f"No synced GR shops for channel {channel.idx}")
        return None

    if len(shops) == 1:
        return shops[0]

    lang = language_code.lower() if language_code else None
    curr = currency_code.upper() if currency_code else None

    if lang and curr:
        for shop in shops:
            if shop.language.iso2 == lang and shop.currency.iso3 == curr:
                logger.debug(f"Shop matched by language+currency: {shop.name}")
                return shop

    if curr:
        for shop in shops:
            if shop.currency.iso3 == curr:
                logger.debug(f"Shop matched by currency: {shop.name}")
                return shop

    logger.debug(f"No shop match for lang={lang} curr={curr}, using first: {shops[0].name}")
    return shops[0]


def get_shop_for_channel_language(channel_idx, language_iso2: str | None = None) -> Optional["GetResponseShop"]:
    """Resolve a shop by channel, matching language OR external_language.

    The request carries the EXTERNAL language code (e.g. "en"), while a shop may store a
    region-specific internal language (e.g. "gb"). Match against both, then fall back to any
    shop in the channel.

    Args:
        channel_idx: Channel idx
        language_iso2: 2-letter language code from the request (or None)

    Returns:
        Best-matching GetResponseShop or None
    """
    from django.db.models import Q

    from django_getresponse.models import GetResponseShop

    if not channel_idx:
        return None

    base = GetResponseShop.objects.filter(channel__idx=channel_idx)
    shop = None
    if language_iso2:
        lang = language_iso2.lower()
        shop = base.filter(Q(language__iso2__iexact=lang) | Q(external_language__iso2__iexact=lang)).first()
    return shop or base.first()


def get_api_key_for_channel(channel) -> str | None:
    """Get API key from enabled GetResponse account for channel.

    Args:
        channel: Channel instance

    Returns:
        API key string or None
    """
    from django_getresponse.models import GetResponseAccount

    try:
        account = GetResponseAccount.objects.filter(channel=channel, is_enabled=True).first()
        if not account:
            logger.warning(f"No enabled GetResponse account for channel {channel.idx}")
            return None
        return account.api_key
    except Exception as e:
        logger.error(f"Error getting GetResponse account: {e}")
        return None


def prepare_sync_setup(instance, entity_name: str = "entity") -> SyncSetup | None:
    """Prepare and validate sync setup (shop + API key).

    Args:
        instance: Entity instance (Order, Cart, etc.) with channel attribute
        entity_name: Name of entity for logging (e.g., "order", "cart")

    Returns:
        SyncSetup with shop and api_key or None if validation fails
    """
    if not hasattr(instance, "channel") or not instance.channel:
        entity_id = getattr(instance, f"{entity_name}_id", "unknown")
        logger.debug(f"{entity_name.capitalize()} {entity_id} has no channel, skipping GR sync")
        return None

    shop = get_synced_shop_for_channel(instance.channel)
    if not shop:
        return None

    api_key = get_api_key_for_channel(shop.channel)
    if not api_key:
        return None

    return SyncSetup(shop=shop, api_key=api_key)

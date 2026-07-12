# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from django.db.models.signals import post_save
from django.dispatch import receiver
from process_logger import ProcessLogger

from django_getresponse.services.cart_sync_service import CartSyncContext, CartSyncService
from django_getresponse.services.marketing_consent_service import has_marketing_consent, is_consent_required
from django_getresponse.utils.contact_helpers import get_synced_contact_id_from_email
from django_getresponse.utils.sync_helpers import get_api_key_for_channel, get_shop_for_checkout

logger_process = ProcessLogger("sync_cart_on_save")


@receiver(post_save, sender="django_checkout.Cart")
def sync_cart_on_save(sender, instance, created, **kwargs):
    """
    Sync cart to GetResponse when cart is created or updated.

    Triggered by: Cart save (create or update)
    """

    cart = instance
    logger_process.add_log_param("cart_id", cart.cart_id)

    if not cart.channel:
        logger_process.debug("Cart has no channel, skipping GR sync")
        return

    checkout_data = _get_checkout_data(cart)
    language_code = getattr(checkout_data, "language_code", None) if checkout_data else None
    currency_code = getattr(checkout_data, "currency_code", None) if checkout_data else None

    shop = get_shop_for_checkout(cart.channel, language_code, currency_code)
    if not shop:
        return

    current_email = _extract_email_from_cart(cart)
    if not current_email:
        logger_process.debug("Cart has no email yet, skipping GR sync")
        return

    if not has_marketing_consent(email=current_email, shop=shop, resource_created_at=cart.updated):
        logger_process.debug(f"Cart {cart.cart_id}: no marketing consent for {current_email}, skipping GR sync")
        return

    if not is_consent_required(shop):
        # Gate disabled for this shop -> CRM form is not the contact source.
        # Auto-create the GR contact from the cart email so the cart can sync.
        _auto_create_contact_from_cart_email(cart, shop, current_email)

    contact_id = _get_synced_contact_id_from_cart(cart)

    if not contact_id:
        return

    logger_process.add_log_param("contact_id", contact_id)

    api_key = get_api_key_for_channel(shop.channel)
    if not api_key:
        return

    try:
        context = CartSyncContext(cart=cart, shop=shop, api_key=api_key, contact_id=contact_id)
        service = CartSyncService()
        success, message = service.sync_cart(context)

        if success:
            logger_process.add_log_param_once("message", message)
            logger_process.info("Cart synced to GetResponse")
        else:
            logger_process.add_log_param_once("message", message)
            logger_process.error("Failed to sync cart GetResponse")
    except Exception as e:
        logger_process.exception(e)
    finally:
        logger_process.delete_log_param("cart_id")


def _auto_create_contact_from_cart_email(cart: "Cart", shop: "GetResponseShop", email: str) -> None:
    """Auto-create a GR contact from the cart email (used only when the consent gate is disabled)."""
    from django_getresponse.services.contact_auto_create_service import (
        ContactAutoCreateContext,
        ContactAutoCreateService,
    )

    try:
        api_key = get_api_key_for_channel(shop.channel)
        if not api_key:
            return
        context = ContactAutoCreateContext(email=email, shop=shop, api_key=api_key, source="cart")
        ContactAutoCreateService().create_contact_if_needed(context)
    except Exception as e:
        logger_process.exception(e)


def _get_synced_contact_id_from_cart(cart: "Cart") -> str | None:
    """Get GetResponse contact_id from cart (ONLY if synced).

    Returns contact_id only if contact has sync_status='synced' and contact_id is set.
    Returns None if contact is pending or doesn't exist.
    """
    email = _extract_email_from_cart(cart)
    if not email:
        return None

    return get_synced_contact_id_from_email(email)


def _get_checkout_data(cart: "Cart"):
    """Return cart.as_data or None on error."""
    try:
        return cart.as_data
    except Exception as e:
        logger_process.exception(e)
        return None


def _extract_email_from_cart(cart: "Cart") -> str | None:
    """Extract billing email from cart checkout data."""
    try:
        checkout_data = cart.as_data
        if checkout_data.addresses and checkout_data.addresses.billing_address:
            return checkout_data.addresses.billing_address.email
    except Exception as e:
        logger_process.exception(e)
    return None

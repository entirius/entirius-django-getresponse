# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Signals for updating contact custom fields after cart/order operations."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from process_logger import ProcessLogger

from django_getresponse.services.marketing_consent_service import has_marketing_consent

logger = ProcessLogger("contact_update_signals")


@receiver(post_save, sender="django_checkout.Cart")
def update_contact_fields_on_cart_save(sender, instance, created, **kwargs):
    """
    Update contact custom fields when cart is saved.

    This runs asynchronously in the background to not block the user.

    Args:
        sender: Cart model
        instance: Cart instance
        created: Whether this is a new cart
        kwargs: Additional signal kwargs
    """
    cart = instance

    email = _extract_email_from_cart(cart)
    if not email:
        return

    try:
        from django_getresponse.utils.sync_helpers import get_shop_for_checkout

        checkout_data = _get_checkout_data_safe(cart)
        language_code = getattr(checkout_data, "language_code", None) if checkout_data else None
        currency_code = getattr(checkout_data, "currency_code", None) if checkout_data else None

        shop = get_shop_for_checkout(cart.channel, language_code, currency_code)
        if not shop:
            logger.debug(f"No synced shop for channel {cart.channel.idx}")
            return

        if not has_marketing_consent(email=email, shop=shop, resource_created_at=cart.updated):
            return

        _update_contact_fields_async(email=email, shop=shop)

    except Exception as e:
        logger.exception(e)


@receiver(post_save, sender="django_checkout.Order")
def update_contact_fields_on_order_save(sender, instance, created, **kwargs):
    """
    Update contact custom fields when order is saved.

    This runs asynchronously in the background to not block the user.

    Args:
        sender: Order model
        instance: Order instance
        created: Whether this is a new order
        kwargs: Additional signal kwargs
    """
    order = instance

    email = None
    if hasattr(order, "customer") and order.customer:
        email = order.customer.email
    elif hasattr(order, "billing") and order.billing:
        email = getattr(order.billing, "email", None)

    if not email:
        logger.debug(f"No email found for order {order.order_id}")
        return

    try:
        from django_getresponse.utils.sync_helpers import get_shop_for_checkout

        try:
            order_data = order.as_data
            language_code = getattr(order_data, "language_code", None)
            currency_code = getattr(order_data, "currency_code", None)
        except Exception:
            language_code, currency_code = None, None

        shop = get_shop_for_checkout(order.channel, language_code, currency_code)
        if not shop:
            logger.debug(f"No synced shop for channel {order.channel.idx}")
            return

        if not has_marketing_consent(email=email, shop=shop, resource_created_at=order.created):
            return

        _update_contact_fields_async(email=email, shop=shop)

    except Exception as e:
        logger.exception(e)


def _update_contact_fields_async(email: str, shop: "GetResponseShop"):
    """
    Update contact custom fields in background task.

    This runs asynchronously to not block the main request.

    Args:
        email: Customer email
        shop: GetResponseShop instance
    """
    try:
        from django_getresponse.services.contact_custom_fields_service import ContactCustomFieldsService

        service = ContactCustomFieldsService()
        service.sync_contact_from_email(email=email, shop=shop)

    except Exception as e:
        logger.add_log_param_once("email", email)
        logger.exception(e)


def _get_checkout_data_safe(cart):
    try:
        return cart.as_data
    except Exception as e:
        logger.exception(e)
        return None


def _extract_email_from_cart(cart: "Cart") -> str | None:
    """Extract billing email from cart checkout data."""
    try:
        checkout_data = cart.as_data
        if checkout_data.addresses and checkout_data.addresses.billing_address:
            return checkout_data.addresses.billing_address.email
    except Exception as e:
        logger.debug(f"Could not extract email from cart: {e}")
    return None

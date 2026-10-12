---
title: Signal-Based Sync
description: How cart, order and contact changes reach GetResponse through Django signals.
---

`apps.py ready()` imports three receiver modules (post_save with lazy string senders —
`django_checkout` must be installed or Django's system check fails with signals.E001):

- `cart_signals.sync_cart_on_save` — `post_save` on `django_checkout.Cart`
- `order_signals.sync_order_on_create`, `sync_order_status_change` — `post_save` on `django_checkout.Order`
- `contact_update_signals.update_contact_fields_on_cart_save`, `update_contact_fields_on_order_save` — contact
  custom-field updates on cart/order saves

Receivers resolve the right `GetResponseShop` (per channel + language + currency) and call the
matching sync service. Channel lookup uses `get_shop_for_checkout()` and API key via
`get_api_key_for_channel()` (both in `utils/sync_helpers.py`).

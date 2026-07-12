# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.conf import settings

MEDIA_URL = settings.MEDIA_URL

MARKETING_CONSENT_GRACE_SECONDS = getattr(settings, "GETRESPONSE_MARKETING_CONSENT_GRACE_SECONDS", 180)

# When True, a configurable's variants (sub-products) send the parent configurable's url_key
# to GetResponse instead of their own simple url_key. Base URL resolution (channel + language ->
# shop.domain_url) is unchanged. Default False = each variant keeps its own url_key.
USE_CONFIG_URL_KEY = getattr(settings, "GETRESPONSE_USE_CONFIG_URL_KEY", False)

# When True, the cart UUID is appended to shop.domain_url_cart as a query param (?cart=<uuid>)
# in the cartUrl sent to GetResponse, so the PWA can restore the specific cart. Default False =
# send the configured cart URL as-is. No effect when shop.domain_url_cart is empty (cartUrl omitted).
SEND_CART_UID_TO_GETRESPONSE_IN_LINK = getattr(settings, "SEND_CART_UID_TO_GETRESPONSE_IN_LINK", False)

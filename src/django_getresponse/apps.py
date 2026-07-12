# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.apps import AppConfig


class DjangoPricemanagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_getresponse"
    verbose_name = "Django GetResponse"

    def ready(self):
        """Register signal handlers when app is ready."""
        import django_getresponse.receivers.cart_signals  # noqa
        import django_getresponse.receivers.order_signals  # noqa
        import django_getresponse.receivers.contact_update_signals  # noqa

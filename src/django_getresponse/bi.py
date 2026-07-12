# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from bievents import BiEventAbstract
from django.conf import settings

BI_SOURCE = "django-getresponse"
BI_ENVIRONMENT = settings.BI_ENVIRONMENT
BI_BUSINESS_UNIT = settings.BI_BUSINESS_UNIT


class EventAbstract(BiEventAbstract):
    details_type = "Event Abstract"
    version = 1

    def __init__(self, **kwargs):
        kwargs["source"] = BI_SOURCE
        kwargs["environment"] = BI_ENVIRONMENT
        kwargs["business_unit"] = BI_BUSINESS_UNIT
        super().__init__(**kwargs)

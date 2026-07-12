# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


class Channel(BaseModel):
    idx = models.CharField(max_length=255, unique=True, help_text="Unique identifier for the channel")

    objects = models.Manager()

    def __str__(self):
        return self.idx

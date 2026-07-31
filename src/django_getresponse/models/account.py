# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


class GetResponseAccount(BaseModel):
    """
    GetResponse API credentials and account configuration.

    Each account is assigned to a specific channel, allowing each channel
    to have its own GetResponse configuration.
    """

    channel = models.ForeignKey(
        "django_getresponse.Channel",
        on_delete=models.CASCADE,
        related_name="getresponse_accounts",
        help_text="Channel this GetResponse account belongs to",
    )
    api_key = models.CharField(max_length=64, help_text="GetResponse API key for authentication")
    is_enabled = models.BooleanField(default=False, help_text="Enable/disable this GetResponse account globally")
    name = models.CharField(
        max_length=128, blank=True, help_text="Friendly name for this account (e.g., 'Production', 'Test')"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = "GetResponse Account"
        verbose_name_plural = "GetResponse Accounts"
        db_table = "django_getresponse_account"
        unique_together = [("channel", "api_key")]

    def __str__(self):
        channel_name = self.channel.idx if self.channel else "no-channel"
        if self.name:
            return f"{channel_name} | {self.name} ({'enabled' if self.is_enabled else 'disabled'})"
        return f"{channel_name} | {self.api_key[:8]}... | enabled: {self.is_enabled}"

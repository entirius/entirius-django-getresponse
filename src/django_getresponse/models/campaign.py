# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_regional.models.language import Language
from django_utils.models.base_model import BaseModel


class GetResponseCampaign(BaseModel):
    """
    GetResponse campaign configuration.
    Moved from django_crm for better separation of concerns.
    """

    account = models.ForeignKey(
        "GetResponseAccount",
        on_delete=models.CASCADE,
        related_name="campaigns",
        help_text="GetResponse account that owns this campaign",
    )
    name = models.CharField(max_length=128, help_text="Campaign name from GetResponse")
    campaign_id = models.CharField(max_length=64, help_text="Campaign ID from GetResponse API")
    language = models.ForeignKey(
        Language,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text="Language for this campaign. If empty, this campaign serves as a fallback for languages without a specific campaign.",
    )
    is_active = models.BooleanField(default=False, help_text="Enable/disable this campaign")
    default_day_of_cycle = models.IntegerField(
        blank=True,
        null=True,
        help_text=(
            "Default day of the autoresponder cycle for contacts added to this campaign. "
            "Used when a contact does not set its own day_of_cycle; leave empty to omit dayOfCycle."
        ),
    )

    objects = models.Manager()

    class Meta:
        verbose_name = "GetResponse Campaign"
        verbose_name_plural = "GetResponse Campaigns"
        db_table = "django_getresponse_campaign"
        unique_together = [["account", "campaign_id"]]
        indexes = [
            models.Index(fields=["account", "is_active"]),
            models.Index(fields=["language", "is_active"]),
        ]

    def __str__(self):
        lang_info = f" ({self.language.iso2})" if self.language else " (fallback)"
        return f"{self.name}{lang_info} {self.account.channel.idx}"

    @property
    def owner(self):
        """Backward compatibility: alias for 'account' field."""
        return self.account

    @classmethod
    def get_for_language(cls, language_iso2=None, account=None):
        """
        Get active campaign for specific language.
        Priority: campaigns with matching language, then campaigns without language (fallback).

        Args:
            language_iso2: ISO2 language code (e.g., 'en', 'pl')
            account: Optional GetResponseAccount instance to filter by

        Returns:
            GetResponseCampaign instance or None
        """
        queryset = cls.objects.filter(is_active=True)

        if account:
            queryset = queryset.filter(account=account)

        if language_iso2:
            campaign = queryset.filter(language__iso2=language_iso2).first()
            if campaign:
                return campaign

        return queryset.filter(language__isnull=True).first()

    @classmethod
    def get_for_channel_and_language(cls, channel_idx, language_iso2=None):
        """
        Active campaign scoped to a channel; falls back to language=NULL within the SAME channel.

        Prevents cross-channel fallback (one channel's form POST resolving another channel's
        campaign) that happens with the channel-agnostic get_for_language().

        Args:
            channel_idx: Channel idx (account__channel__idx)
            language_iso2: ISO2 language code (e.g., 'en', 'pl')

        Returns:
            GetResponseCampaign instance or None
        """
        if not channel_idx:
            return cls.get_for_language(language_iso2=language_iso2)

        queryset = cls.objects.filter(account__channel__idx=channel_idx, is_active=True)

        if language_iso2:
            campaign = queryset.filter(language__iso2=language_iso2).first()
            if campaign:
                return campaign

        return queryset.filter(language__isnull=True).first()

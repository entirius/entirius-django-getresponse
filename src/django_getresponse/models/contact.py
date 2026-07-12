# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


def get_default_tags():
    """Default factory for tags JSONField"""
    return {"tags": []}


def get_default_custom_field_values():
    """Default factory for custom_field_values JSONField"""
    return {"custom_field_values": []}


class GetResponseContact(BaseModel):
    """
    GetResponse contact/profile configuration.
    Moved from django_crm.GetResponseProfiles for better separation of concerns.

    This model stores the configuration for syncing a form submission to GetResponse.
    """

    campaign = models.ForeignKey(
        "GetResponseCampaign",
        on_delete=models.CASCADE,
        related_name="contacts",
        help_text="GetResponse campaign for this contact",
    )
    form = models.ForeignKey(
        "django_crm.Form",
        on_delete=models.CASCADE,
        related_name="getresponse_contacts",
        help_text="CRM form associated with this contact",
    )
    day_of_cycle = models.IntegerField(blank=True, null=True, help_text="Day of autoresponder cycle")
    scoring = models.IntegerField(blank=True, null=True, help_text="Contact scoring value")
    tags = models.JSONField(default=get_default_tags, help_text="Tags to assign to contact in GetResponse")
    custom_field_values = models.JSONField(
        default=get_default_custom_field_values, help_text="Custom field values for the contact"
    )

    contact_id = models.CharField(
        max_length=255, blank=True, null=True, help_text="GetResponse contact ID (returned from API)"
    )
    sync_status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("synced", "Synced"), ("failed", "Failed")],
        default="pending",
        help_text="Synchronization status with GetResponse",
    )
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last successful synchronization timestamp")
    error_message = models.TextField(blank=True, help_text="Last error message if sync failed")

    objects = models.Manager()

    class Meta:
        verbose_name = "GetResponse Contact"
        verbose_name_plural = "GetResponse Contacts"
        db_table = "django_getresponse_contact"
        indexes = [
            models.Index(fields=["campaign", "form"]),
            models.Index(fields=["contact_id"]),
            models.Index(fields=["sync_status"]),
        ]

    def __str__(self):
        return f"Contact for {self.form.email} in {self.campaign.name}"

    def generate_payload(self, form=None, custom_tags=None) -> dict:
        """
        Generate GetResponse API payload for creating/updating contact.

        Args:
            form: Form instance (defaults to self.form)
            custom_tags: Optional tags to override default tags

        Returns:
            dict: Payload ready for GetResponse API
        """
        if form is None:
            form = self.form

        email = form.email
        tags = custom_tags if custom_tags else self.tags
        custom_field_values = self.custom_field_values

        campaign = {"campaign": {"campaignId": self.campaign.campaign_id}}
        resolved_day_of_cycle = (
            self.day_of_cycle if self.day_of_cycle is not None else self.campaign.default_day_of_cycle
        )
        day_of_cycle = {"dayOfCycle": resolved_day_of_cycle} if resolved_day_of_cycle is not None else {}
        scoring = {"scoring": self.scoring} if self.scoring is not None else {}

        return {"email": email, **campaign, **day_of_cycle, **scoring, **tags, **custom_field_values}

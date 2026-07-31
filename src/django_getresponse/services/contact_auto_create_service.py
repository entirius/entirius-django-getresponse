# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Service for auto-creating GetResponse contacts from cart checkout.

This service handles the automatic creation of GetResponse contacts
when users provide their email during the checkout process.
"""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from process_logger import ProcessLogger


@dataclass
class ContactAutoCreateContext:
    """Context for contact auto-creation."""

    email: str
    shop: "GetResponseShop"
    api_key: str
    source: str = "cart"


class ContactAutoCreateService:
    """Service for auto-creating contacts in GetResponse."""

    def __init__(self, client=None):
        from get_response_sdk import GetResponseClient

        self.client = client or GetResponseClient()
        self.logger = ProcessLogger("ContactAutoCreateService")
        self.context: ContactAutoCreateContext | None = None

    def create_contact_if_needed(self, context: ContactAutoCreateContext) -> bool:
        """Create contact if it doesn't already exist.

        Args:
            context: ContactAutoCreateContext with email, shop, api_key, source

        Returns:
            True if contact was created or already exists, False on error
        """
        self.context = context
        if self._synced_contact_exists():
            return True
        return self._create_contact()

    def _synced_contact_exists(self) -> bool:
        """Check if synced contact already exists for email."""
        from django_getresponse.utils.contact_helpers import synced_contact_exists_for_email

        return synced_contact_exists_for_email(self.context.email)

    def _create_contact(self) -> bool:
        """Create contact in GetResponse API."""
        try:
            with transaction.atomic():
                campaign = self._get_or_select_campaign()
                if not campaign:
                    return False

                if self._contact_exists_for_campaign(campaign):
                    return True

                success = self._create_contact_in_api(campaign)
                return success

        except Exception as e:
            self.logger.exception(e)
            return False

    def _get_or_select_campaign(self):
        """Get campaign - prefer shop.cart_campaign, fallback to channel-scoped language lookup."""
        from django_getresponse.models import GetResponseCampaign

        if self.context.shop.cart_campaign:
            campaign = self.context.shop.cart_campaign
            return campaign

        language_iso2 = self.context.shop.external_language.iso2
        campaign = GetResponseCampaign.get_for_channel_and_language(
            channel_idx=self.context.shop.channel.idx, language_iso2=language_iso2
        )
        if not campaign:
            self.logger.warning(f"No GetResponse campaign for language {language_iso2}")
            return None

        return campaign

    def _contact_exists_for_campaign(self, campaign) -> bool:
        """Check if contact already exists for this email and campaign."""
        from django_getresponse.models import GetResponseContact

        existing_contact = GetResponseContact.objects.filter(email=self.context.email, campaign=campaign).first()

        if existing_contact and existing_contact.contact_id:
            return True
        return False

    def _create_contact_in_api(self, campaign) -> bool:
        """Create contact in GetResponse API and store record."""
        from django_getresponse.models import GetResponseContact

        payload = self._build_api_payload(campaign)
        tags_data = {"tags": [self.context.source, "cart_checkout"]}

        status_code, response = self.client.create_profile(
            instance=payload, resource="contacts", api_key=self.context.api_key
        )

        contact_record = GetResponseContact.objects.create(
            email=self.context.email, campaign=campaign, tags=tags_data, sync_status="pending"
        )
        self.logger.debug(f"Created GetResponseContact record (id={contact_record.id})")

        if 200 <= status_code < 300:
            return self._fetch_and_update_contact_id(contact_record, campaign)
        elif status_code == 409:
            return self._fetch_and_update_contact_id(contact_record, campaign)
        else:
            self._mark_contact_as_failed(contact_record, status_code, response)
            return False

    def _build_api_payload(self, campaign) -> dict:
        """Build payload for GetResponse API.

        Auto-created contacts have no per-contact override, so dayOfCycle falls back
        to the campaign default (campaign.default_day_of_cycle); omitted when unset.
        """
        payload = {"email": self.context.email, "campaign": {"campaignId": campaign.campaign_id}}
        if campaign.default_day_of_cycle is not None:
            payload["dayOfCycle"] = campaign.default_day_of_cycle
        return payload

    def _fetch_and_update_contact_id(self, contact_record, campaign) -> bool:
        """Fetch contactId from API and update record.

        POST /contacts returns 202 without contactId, need to fetch it.
        """
        contacts = self.client.get_campaign_contact(
            campaign_id=campaign.campaign_id, api_key=self.context.api_key, query={"email": self.context.email}
        )

        if contacts and len(contacts) > 0:
            contact_id = contacts[0].get("contactId")
            if contact_id:
                contact_record.contact_id = contact_id
                contact_record.sync_status = "synced"
                contact_record.last_sync_at = timezone.now()
                contact_record.save(update_fields=["contact_id", "sync_status", "last_sync_at"])
                self.logger.add_log_param_once("contactId", contact_id)
                self.logger.add_log_param_once("email", self.context.email)
                self.logger.info("Contact synced.")
                return True
            else:
                return False
        else:
            return False

    def _mark_contact_as_failed(self, contact_record, status_code: int, response: dict):
        """Mark contact record as failed."""
        error_msg = f"API error (HTTP {status_code}): {response}"
        contact_record.sync_status = "failed"
        contact_record.error_message = error_msg
        contact_record.save(update_fields=["sync_status", "error_message"])
        self.logger.error(f"Failed to create contact for {self.context.email}: {error_msg}")
        raise Exception(f"Unexpected status code: {status_code}")

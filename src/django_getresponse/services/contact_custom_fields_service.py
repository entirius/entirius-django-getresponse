# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Service for calculating and updating contact custom fields."""

from dataclasses import dataclass

from process_logger import ProcessLogger

logger = ProcessLogger("ContactCustomFieldsService")


@dataclass
class ContactCustomFields:
    """Data class for contact custom field values."""

    customer_type: str  # "new" or "returning"
    total_orders_count: int
    last_order_date: str | None  # ISO format date or None


class ContactCustomFieldsService:
    """Service for calculating customer segmentation fields and updating contact."""

    def __init__(self, client=None):
        """
        Initialize service.

        Args:
            client: Optional GetResponse SDK client (for testing)
        """
        if client is None:
            from get_response_sdk import GetResponseClient as GRClient

            self.client = GRClient()
        else:
            self.client = client

    def calculate_fields_from_email(self, email: str) -> ContactCustomFields | None:
        """
        Calculate custom field values from customer email.

        Args:
            email: Customer email address

        Returns:
            ContactCustomFields with calculated values or None if contact not found
        """
        try:
            from django_getresponse.models import GetResponseContact

            contact = GetResponseContact.objects.filter(
                email=email, sync_status="synced", contact_id__isnull=False
            ).first()

            if not contact:
                logger.debug(f"No synced contact found for email: {email}")
                return None

            return self.calculate_fields_from_contact(contact)

        except Exception as e:
            logger.exception(f"Error calculating fields for email {email}: {e}")
            return None

    def calculate_fields_from_contact(self, contact: "GetResponseContact") -> ContactCustomFields:
        """
        Calculate custom field values from GetResponseContact instance.

        Uses OrderSync records to count orders for this contact.

        Args:
            contact: GetResponseContact instance

        Returns:
            ContactCustomFields with calculated values
        """
        from django_getresponse.models import OrderSync

        orders = OrderSync.objects.filter(contact_id=contact.contact_id, sync_status="synced").order_by("-processed_at")

        total_orders_count = orders.count()
        customer_type = "new" if total_orders_count == 0 else "returning"

        last_order = orders.first()
        last_order_date = last_order.processed_at.strftime("%Y-%m-%d") if last_order else None

        return ContactCustomFields(
            customer_type=customer_type,
            total_orders_count=total_orders_count,
            last_order_date=last_order_date,
        )

    def update_contact_fields(
        self,
        contact_id: str,
        shop: "GetResponseShop",
        fields: ContactCustomFields,
        api_key: str,
    ) -> bool:
        """
        Update contact custom fields in GetResponse.

        Args:
            contact_id: GetResponse contact ID
            shop: GetResponseShop with custom field IDs
            fields: Calculated custom field values
            api_key: GetResponse API key

        Returns:
            True if successful, False otherwise
        """
        try:
            custom_field_values = []

            if shop.customer_type_field_id:
                custom_field_values.append(
                    {"customFieldId": shop.customer_type_field_id, "value": [fields.customer_type]}
                )

            if shop.total_orders_count_field_id:
                custom_field_values.append(
                    {"customFieldId": shop.total_orders_count_field_id, "value": [str(fields.total_orders_count)]}
                )

            if shop.last_order_date_field_id and fields.last_order_date:
                custom_field_values.append(
                    {"customFieldId": shop.last_order_date_field_id, "value": [fields.last_order_date]}
                )

            if not custom_field_values:
                logger.add_log_param_once("shop_name", shop.name)
                logger.warning("No custom field IDs configured for shop")
                return False

            payload = {"customFieldValues": custom_field_values}

            status_code, response_data = self.client.upsert_contact_custom_fields(
                contact_id=contact_id,
                custom_fields_data=payload,
                api_key=api_key,
            )

            if status_code == 200:
                logger.add_log_param_once("contact_id", contact_id)
                logger.info("Successfully updated contact custom fields")
                return True
            else:
                logger.add_log_param_once("contact_id", contact_id)
                logger.add_log_param_once("status_code", status_code)
                logger.error("Failed to update contact custom fields")
                return False

        except Exception as e:
            logger.exception(f"Error updating contact {contact_id} custom fields: {e}")
            return False

    def sync_contact_from_email(
        self,
        email: str,
        shop: "GetResponseShop",
    ) -> bool:
        """
        Calculate and sync contact custom fields from email.

        This is the main entry point - combines calculation and update.

        Args:
            email: Customer email
            shop: GetResponseShop with custom field IDs

        Returns:
            True if successful, False otherwise
        """
        from django_getresponse.models import GetResponseAccount, GetResponseContact

        try:
            contact = GetResponseContact.objects.filter(email=email, sync_status="synced").first()

            if not contact or not contact.contact_id:
                logger.debug(f"No synced contact found for email: {email}")
                return False

            account = GetResponseAccount.objects.filter(channel=shop.channel, is_enabled=True).first()

            if not account or not account.api_key:
                logger.add_log_param_once("channel", shop.channel.idx)
                logger.warning("No API key for channel")
                return False

            fields = self.calculate_fields_from_email(email)

            if not fields:
                logger.add_log_param_once("email", email)
                logger.warning("Could not calculate fields for email")
                return False

            return self.update_contact_fields(
                contact_id=contact.contact_id,
                shop=shop,
                fields=fields,
                api_key=account.api_key,
            )

        except Exception as e:
            logger.exception(f"Error syncing contact for {email}: {e}")
            return False

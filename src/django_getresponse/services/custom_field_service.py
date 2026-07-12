# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Service for managing GetResponse custom fields."""

from process_logger import ProcessLogger

logger = ProcessLogger("CustomFieldService")


class CustomFieldService:
    """Service for creating and managing custom fields in GetResponse."""

    def __init__(self, client=None):
        """
        Initialize service.

        Args:
            client: Optional GetResponse SDK client (for testing)
        """
        if client is None:
            from get_response_sdk import GetResponseClient

            self.client = GetResponseClient()
        else:
            self.client = client

    def create_or_get_field(
        self,
        channel: "Channel",
        field_name: str,
        field_type: str,
        field_format: str = "text",
        hidden: str = "false",
    ) -> str | None:
        """
        Create custom field in GetResponse or get existing field ID.

        Args:
            channel: Channel for API key
            field_name: Name of custom field (e.g., "customer_type")
            field_type: Type (string, number, date, datetime, etc.)
            field_format: Format (text, textarea, radio, etc.)
            hidden: Whether field is hidden ("true" or "false")

        Returns:
            Custom field ID if successful, None otherwise

        """
        from django_getresponse.models import GetResponseAccount

        try:
            account = GetResponseAccount.objects.filter(channel=channel, is_enabled=True).first()

            if not account or not account.api_key:
                logger.add_log_param_once("channel", channel.idx)
                logger.warning("No API key found for channel")
                return None

            existing_field_id = self._get_existing_field(api_key=account.api_key, field_name=field_name)

            if existing_field_id:
                logger.add_log_param_once("field_name", field_name)
                logger.add_log_param_once("field_id", existing_field_id)
                logger.info("Custom field already exists")
                return existing_field_id

            return self._create_field(
                api_key=account.api_key,
                field_name=field_name,
                field_type=field_type,
                field_format=field_format,
                hidden=hidden,
            )

        except Exception as e:
            logger.exception(f"Error creating custom field '{field_name}': {e}")
            return None

    def _get_existing_field(self, api_key: str, field_name: str) -> str | None:
        """
        Check if custom field already exists.

        Args:
            api_key: GetResponse API key
            field_name: Name of field to search for

        Returns:
            Field ID if found, None otherwise
        """
        try:
            status_code, response_data = self.client.get_custom_fields(
                api_key=api_key, query_params={"query[name]": field_name}
            )

            if status_code == 200 and isinstance(response_data, list):
                for field in response_data:
                    if field.get("name") == field_name:
                        return field.get("customFieldId")

            return None

        except Exception as e:
            logger.debug(f"Error checking existing field '{field_name}': {e}")
            return None

    def _create_field(
        self,
        api_key: str,
        field_name: str,
        field_type: str,
        field_format: str,
        hidden: str,
    ) -> str | None:
        """
        Create new custom field in GetResponse.

        Args:
            api_key: GetResponse API key
            field_name: Name of custom field
            field_type: Type (string, number, date, etc.)
            field_format: Format (text, textarea, etc.)
            hidden: Whether hidden ("true"/"false")

        Returns:
            Custom field ID if successful, None otherwise
        """
        try:
            payload = {"name": field_name, "type": field_type, "format": field_format, "hidden": hidden, "values": []}

            status_code, response_data = self.client.create_custom_field(api_key=api_key, custom_field_data=payload)

            if status_code == 201:
                field_id = response_data.get("customFieldId")
                logger.add_log_param_once("field_name", field_name)
                logger.add_log_param_once("field_id", field_id)
                logger.info("Created custom field")
                return field_id
            else:
                logger.add_log_param_once("field_name", field_name)
                logger.add_log_param_once("status_code", status_code)
                logger.error("Failed to create custom field")
                return None

        except Exception as e:
            logger.exception(e)
            return None

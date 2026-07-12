# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Base class for GetResponse sync services.

This module provides an abstract base class that implements common
patterns for syncing entities (orders, carts) with GetResponse API.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from process_logger import ProcessLogger

ContextT = TypeVar("ContextT")
SyncRecordT = TypeVar("SyncRecordT")


class BaseSyncService(ABC, Generic[ContextT, SyncRecordT]):
    """Abstract base class for GetResponse sync services.

    Implements Template Method pattern for sync operations.
    Subclasses must implement abstract methods for specific entity logic.

    Type Parameters:
        ContextT: Type of context dataclass (e.g., OrderSyncContext)
        SyncRecordT: Type of sync record model (e.g., OrderSync)
    """

    def __init__(self, client=None, service_name: str = "BaseSyncService"):
        """Initialize sync service.

        Args:
            client: GetResponse client (optional, will be created if not provided)
            service_name: Name for logger identification
        """
        from get_response_sdk import GetResponseClient

        self.client = client or GetResponseClient()
        self.logger = ProcessLogger(service_name)
        self.context: ContextT | None = None

    def _should_skip_sync(self) -> bool:
        """Check if sync should be skipped.

        Default implementation checks if already synced and if data changed.
        Subclasses can override for custom logic.

        Returns:
            True if sync should be skipped, False otherwise
        """
        if not self._is_already_synced():
            return False
        return not self._has_data_changed()

    def _has_data_changed(self) -> bool:
        """Check if entity data changed since last sync.

        Compares current payload with last request data.

        Returns:
            True if data changed, False otherwise
        """
        sync_record = self._get_sync_record()
        if not sync_record or not sync_record.last_request_data:
            return True

        current_payload = self._generate_current_payload()
        return current_payload != sync_record.last_request_data

    def _handle_sync_error(self, error: Exception) -> None:
        """Handle sync error by logging and marking record as failed.

        Args:
            error: Exception that occurred during sync
        """
        entity_name = self._get_entity_name()
        entity_id = self._get_entity_id()
        self.logger.add_log_param_once("entity_name", entity_name)
        self.logger.add_log_param_once("entity_id", entity_id)
        self.logger.add_log_param_once("error", str(error))
        self.logger.error("Sync failed")

        sync_record = self._get_sync_record()
        if sync_record:
            sync_record.mark_as_failed(str(error))

    @abstractmethod
    def _is_already_synced(self) -> bool:
        """Check if entity is already synced.

        Returns:
            True if sync record exists, False otherwise
        """
        pass

    @abstractmethod
    def _get_sync_record(self) -> SyncRecordT | None:
        """Get existing sync record for entity.

        Returns:
            Sync record instance or None if not found
        """
        pass

    @abstractmethod
    def _generate_current_payload(self) -> dict:
        """Generate current payload for entity.

        This is used for change detection.

        Returns:
            Dictionary with current entity data as would be sent to API
        """
        pass

    @abstractmethod
    def _get_entity_name(self) -> str:
        """Get entity name for logging.

        Returns:
            Entity name (e.g., "Order", "Cart")
        """
        pass

    @abstractmethod
    def _get_entity_id(self) -> str:
        """Get entity ID for logging.

        Returns:
            Entity ID as string
        """
        pass

    def _log_sync_start(self) -> None:
        """Log sync start. Can be overridden for custom logging."""
        entity_name = self._get_entity_name()
        entity_id = self._get_entity_id()
        self.logger.add_log_param_once("entity_name", entity_name)
        self.logger.add_log_param_once("entity_id", entity_id)
        self.logger.info("Starting sync")

    def _log_sync_success(self, message: str) -> None:
        """Log sync success. Can be overridden for custom logging."""
        entity_name = self._get_entity_name()
        entity_id = self._get_entity_id()
        self.logger.add_log_param_once("entity_name", entity_name)
        self.logger.add_log_param_once("entity_id", entity_id)
        self.logger.add_log_param_once("message", message)
        self.logger.info("Synced successfully")

    def _log_sync_skip(self, reason: str) -> None:
        """Log sync skip. Can be overridden for custom logging."""
        entity_name = self._get_entity_name()
        entity_id = self._get_entity_id()
        self.logger.add_log_param_once("entity_name", entity_name)
        self.logger.add_log_param_once("entity_id", entity_id)
        self.logger.add_log_param_once("reason", reason)
        self.logger.info("Skipping sync")

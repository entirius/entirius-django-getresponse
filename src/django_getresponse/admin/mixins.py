# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Admin mixins for reusable admin functionality.

This module provides mixins to eliminate code duplication across admin classes,
following DRY and Clean Code principles.
"""

import json

from django.contrib import admin
from django.utils.safestring import mark_safe


class SyncStatusBadgeMixin:
    """Mixin providing sync_status_badge display method for admin classes.

    Usage:
        class MyAdmin(SyncStatusBadgeMixin, admin.ModelAdmin):
            list_display = ('name', 'sync_status_badge')
    """

    @admin.display(description="Status")
    def sync_status_badge(self, obj):
        """Display colored sync status badge with icon.

        Works with any model that has sync_status field with choices:
        - synced/SYNCED
        - failed/FAILED
        - pending/PENDING
        """
        colors = {
            "synced": "green",
            "failed": "red",
            "pending": "orange",
        }
        icons = {
            "synced": "[OK]",
            "failed": "[FAILED]",
            "pending": "[PENDING]",
        }

        status = str(obj.sync_status).lower()
        color = colors.get(status, "gray")
        icon = icons.get(status, "")

        return mark_safe(
            f'<span style="color: {color}; font-weight: bold;">{icon} {obj.get_sync_status_display()}</span>'
        )


class ApiDataPreviewMixin:
    """Mixin providing request/response preview methods for admin classes.

    Usage:
        class MyAdmin(ApiDataPreviewMixin, admin.ModelAdmin):
            readonly_fields = ('request_preview', 'response_preview')
    """

    @admin.display(description="Request Data")
    def request_preview(self, obj):
        """Display formatted JSON preview of last API request data."""
        if obj.last_request_data:
            formatted = json.dumps(obj.last_request_data, indent=2, ensure_ascii=False)
            return mark_safe(f'<pre style="background: #f5f5f5; padding: 10px;">{formatted}</pre>')
        return "No request data"

    @admin.display(description="Response Data")
    def response_preview(self, obj):
        """Display formatted JSON preview of last API response data."""
        if obj.last_response_data:
            formatted = json.dumps(obj.last_response_data, indent=2, ensure_ascii=False)
            return mark_safe(f'<pre style="background: #f5f5f5; padding: 10px;">{formatted}</pre>')
        return "No response data"


class ResyncActionMixin:
    """Mixin providing mark_for_resync action for sync admin classes.

    Usage:
        class MyAdmin(ResyncActionMixin, admin.ModelAdmin):
            actions = ['mark_for_resync']

            # Optional: override to customize message
            resync_success_message = "Custom message with {count} placeholder"
    """

    resync_success_message = "{count} item(s) marked for re-sync."

    @admin.action(description="Mark selected for re-sync")
    def mark_for_resync(self, request, queryset):
        """Mark selected items for re-synchronization.

        Resets sync_status to 'pending' and clears error_message.
        """
        updated = queryset.update(sync_status="pending", error_message="")

        message = self.resync_success_message.format(count=updated)
        self.message_user(request, message, level="success")

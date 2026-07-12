# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from datetime import datetime

from django_utils.workers.command import CeleryBaseCommand

from django_getresponse.models import Channel
from django_getresponse.tasks.sync_categories_to_getresponse import (
    sync_categories_to_getresponse,
)


class Command(CeleryBaseCommand):
    help = "Synchronize ProductCategory to GetResponse categories"

    def add_arguments(self, parser):
        _add_channel_argument(parser)
        _add_shop_id_argument(parser)
        _add_force_argument(parser)
        self.default_arguments.extend(["channel_idx", "gr_shop_id", "force"])
        super().add_arguments(parser)

    def handle(self, *args, **options):
        channel_idx = options.get("channel_idx")
        if not channel_idx:
            self._handle_multi_channel_sync(options)
        else:
            super().handle(*args, **options)

    def _handle_multi_channel_sync(self, options):
        channels = _get_channels_with_synced_shops()
        if not channels:
            _display_no_channels_warning(self)
            return
        _display_sync_info(channels, options, self)
        _trigger_channel_sync_tasks(channels, options, self)


def _add_channel_argument(parser) -> None:
    parser.add_argument(
        "--channel-idx",
        type=str,
        required=False,
        help="Channel idx (optional - syncs all channels if not specified)",
    )


def _add_shop_id_argument(parser) -> None:
    parser.add_argument(
        "--gr-shop-id",
        type=str,
        required=False,
        help="GetResponse shop ID (legacy - will use GetResponseShop if not provided)",
    )


def _add_force_argument(parser) -> None:
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-sync all categories (even if already synced)",
    )


def _get_channels_with_synced_shops() -> list[Channel]:
    return list(Channel.objects.filter(getresponse_shops__sync_status="synced").distinct())


def _display_no_channels_warning(command) -> None:
    command.stdout.write(command.style.WARNING("No channels with synced GetResponseShop found."))
    command.stdout.write("Create and sync GetResponseShop first using: sync-shops-to-getresponse")


def _display_sync_info(channels: list[Channel], options: dict, command) -> None:
    command.stdout.write(command.style.SUCCESS("=== Category Synchronization to GetResponse ===\n"))
    command.stdout.write(f"[OK] Found {len(channels)} channel(s) with synced shops")
    _display_force_warning_if_enabled(options, command)


def _display_force_warning_if_enabled(options: dict, command) -> None:
    if options.get("force"):
        command.stdout.write(
            command.style.WARNING("WARNING: Force mode enabled - will re-sync already synced categories")
        )


def _trigger_channel_sync_tasks(channels: list[Channel], options: dict, command) -> None:
    runned_at = datetime.now().isoformat()
    use_celery = options.get("celery", True)
    _display_trigger_info(len(channels), use_celery, command)

    task_ids = []
    for channel in channels:
        _trigger_single_channel_task(channel, runned_at, options, use_celery, task_ids, command)

    _display_completion_summary(len(task_ids), use_celery, command)


def _display_trigger_info(channel_count: int, use_celery: bool, command) -> None:
    mode = "Celery (async)" if use_celery else "synchronous"
    command.stdout.write(command.style.SUCCESS(f"\nTriggering {channel_count} task(s) in {mode} mode...\n"))


def _trigger_single_channel_task(
    channel: Channel,
    runned_at: str,
    options: dict,
    use_celery: bool,
    task_ids: list,
    command,
) -> None:
    if use_celery:
        _trigger_celery_task(channel, runned_at, options, task_ids, command)
    else:
        _execute_sync_directly(channel, runned_at, options, command)


def _trigger_celery_task(channel: Channel, runned_at: str, options: dict, task_ids: list, command) -> None:
    result = sync_categories_to_getresponse.delay(
        runned_at=runned_at,
        channel_idx=channel.idx,
        gr_shop_id=None,
        force=options.get("force", False),
        log_level=10,
    )
    task_ids.append((channel.idx, result.id))
    command.stdout.write(f"  [OK] {channel.idx}: Task {result.id}")


def _execute_sync_directly(channel: Channel, runned_at: str, options: dict, command) -> None:
    sync_categories_to_getresponse(
        runned_at=runned_at,
        channel_idx=channel.idx,
        gr_shop_id=None,
        force=options.get("force", False),
        log_level=10,
    )
    command.stdout.write(f"  [OK] {channel.idx}: Completed")


def _display_completion_summary(task_count: int, use_celery: bool, command) -> None:
    if use_celery:
        command.stdout.write(command.style.SUCCESS(f"\n[OK] {task_count} task(s) queued"))
        command.stdout.write("Monitor task progress in Celery logs or Flower dashboard.")
    else:
        command.stdout.write(command.style.SUCCESS(f"\n[OK] {task_count} channel(s) processed"))

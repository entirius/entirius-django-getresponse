# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django_utils.workers.command import CeleryBaseCommand


class Command(CeleryBaseCommand):
    """
    Synchronize GetResponseShop with GetResponse API.

    This command creates or updates shops in GetResponse based on
    GetResponseShop records in the database.
    """

    help = "Synchronize shops with GetResponse API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--channel-idx",
            type=str,
            required=False,
            help="Channel idx to filter shops (optional, syncs all if not specified)",
        )
        parser.add_argument("--force", action="store_true", help="Force update even if already synced")

        self.default_arguments.extend(["channel_idx", "force"])
        super().add_arguments(parser)

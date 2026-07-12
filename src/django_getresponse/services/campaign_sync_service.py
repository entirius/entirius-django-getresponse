# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from django.db import transaction
from get_response_sdk import GetResponseClient
from process_logger import ProcessLogger

from django_getresponse.models import GetResponseAccount, GetResponseCampaign


class CampaignSyncService:
    def __init__(self, gr_client: GetResponseClient | None = None):
        self.gr_client = gr_client or GetResponseClient()
        self.logger = ProcessLogger("CampaignSyncService")
        self._created_count = 0
        self._updated_count = 0

    @transaction.atomic
    def sync_campaigns_from_api(self, account: GetResponseAccount, delete_missing: bool = True) -> dict:
        campaigns = self._fetch_campaigns_from_api(account.api_key)
        seen_ids = self._upsert_campaigns(account, campaigns)
        deleted = self._delete_missing_campaigns(account, seen_ids, delete_missing)
        return self._build_stats_result(len(campaigns), deleted)

    def _fetch_campaigns_from_api(self, api_key: str) -> list[dict]:
        campaigns = self.gr_client.get_campaign_list(api_key)
        self.logger.add_log_param_once("count", len(campaigns))
        self.logger.info("Fetched campaigns from API")
        return campaigns

    def _upsert_campaigns(self, account: GetResponseAccount, campaigns: list[dict]) -> set[str]:
        seen_ids = set()
        for campaign_data in campaigns:
            self._upsert_single_campaign(account, campaign_data, seen_ids)
        return seen_ids

    def _upsert_single_campaign(self, account: GetResponseAccount, data: dict, seen_ids: set[str]) -> None:
        campaign_id = data["campaignId"]
        campaign, created = self._get_or_create_campaign(account, campaign_id)
        self._update_campaign_if_changed(campaign, data["name"], created)
        seen_ids.add(campaign_id)

    def _get_or_create_campaign(
        self, account: GetResponseAccount, campaign_id: str
    ) -> tuple[GetResponseCampaign, bool]:
        campaign, created = GetResponseCampaign.objects.get_or_create(account=account, campaign_id=campaign_id)
        return campaign, created

    def _update_campaign_if_changed(self, campaign: GetResponseCampaign, name: str, created: bool) -> None:
        if created:
            self._handle_campaign_created(campaign, name)
        else:
            self._handle_campaign_updated(campaign, name)

    def _handle_campaign_created(self, campaign: GetResponseCampaign, name: str) -> None:
        campaign.name = name
        campaign.save(update_fields=["name"])
        self._created_count += 1
        self.logger.add_log_param_once("name", name)
        self.logger.info("Created campaign")

    def _handle_campaign_updated(self, campaign: GetResponseCampaign, name: str) -> None:
        if campaign.name != name:
            campaign.name = name
            campaign.save(update_fields=["name"])
            self._updated_count += 1
            self.logger.add_log_param_once("name", name)
            self.logger.info("Updated campaign")

    def _delete_missing_campaigns(self, account: GetResponseAccount, seen_ids: set[str], delete_missing: bool) -> int:
        if not delete_missing:
            return 0
        return self._perform_deletion(account, seen_ids)

    def _perform_deletion(self, account: GetResponseAccount, seen_ids: set[str]) -> int:
        missing = self._find_missing_campaigns(account, seen_ids)
        count = missing.count()
        self._log_and_delete(missing, count)
        return count

    def _find_missing_campaigns(self, account: GetResponseAccount, seen_ids: set[str]):
        return GetResponseCampaign.objects.filter(account=account).exclude(campaign_id__in=seen_ids)

    def _log_and_delete(self, queryset, count: int) -> None:
        if count > 0:
            self.logger.add_log_param_once("count", count)
            self.logger.warning("Deleting campaigns not found in API")
        queryset.delete()

    def _build_stats_result(self, total: int, deleted: int) -> dict:
        return {
            "total": total,
            "created": self._created_count,
            "updated": self._updated_count,
            "deleted": deleted,
        }

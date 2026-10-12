---
title: Data Model
description: GetResponse module entities, their key fields and relationships.
---

All models inherit `django_utils.models.base_model.BaseModel` (adds `created_at` + `modified_at`).

| Entity | Key Fields | Relationships |
|---|---|---|
| Channel | idx (unique) | none (own channel model) |
| GetResponseAccount | api_key, is_enabled, name | FK → Channel (CASCADE). Unique(channel, api_key) |
| GetResponseCampaign | name, campaign_id, is_active, default_day_of_cycle | FK → GetResponseAccount (CASCADE), FK → django_regional.Language (null = fallback for any language). Unique(account, campaign_id) |
| GetResponseContact | email (sync identity), day_of_cycle (per-contact override), scoring, tags (JSON), custom_field_values (JSON) | FK → GetResponseCampaign |
| GetResponseShop | name, currency, language, external_language, domain_url(s), gr_shop_id, sync_status, last_sync_at, error_message + custom_field_ids | FK → Channel, FK → django_regional.Currency, FK → Language ×2, FK → Country, FK → GetResponseCampaign (cart_campaign). Unique(channel, name) |
| ProductSync | gr_product_id, external_id, sync status | FK → GetResponseShop, FK → django_pim.Product |
| CategorySync | sync status | FK → Channel, FK → GetResponseShop, FK → django_pim.ProductCategory |
| CartSync | cart_id (UUID), gr_cart_id, sync status | FK → GetResponseShop |
| OrderSync | order_id (UUID), gr_order_id, sync status | FK → GetResponseShop |

Sync status is a `TextChoices`: `pending / synced / failed`, tracked per resource.

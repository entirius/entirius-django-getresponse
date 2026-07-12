# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass


@dataclass
class GetResponseCategoryDTO:
    """
    Data Transfer Object for GetResponse category.

    Maps ProductCategory from django_pim to GetResponse API category format.
    """

    name: str
    external_id: str
    parent_id: str | None = None
    url: str | None = None
    is_default: bool = False

    def __post_init__(self):
        """Validate DTO fields according to GetResponse API constraints"""
        if not self.name or len(self.name) < 2:
            raise ValueError(f"Category name must be at least 2 characters, got: '{self.name}'")
        if len(self.name) > 64:
            raise ValueError(f"Category name must be at most 64 characters, got {len(self.name)}")

        if not self.external_id:
            raise ValueError("external_id is required")
        if len(self.external_id) > 255:
            raise ValueError(f"external_id must be at most 255 characters, got {len(self.external_id)}")

        if self.parent_id is not None:
            if len(self.parent_id) < 2 or len(self.parent_id) > 64:
                raise ValueError(f"parent_id must be 2-64 characters, got {len(self.parent_id)}")

        if self.url is not None and len(self.url) > 2048:
            raise ValueError(f"url must be at most 2048 characters, got {len(self.url)}")

    @classmethod
    def from_product_category(
        cls, product_category, parent_gr_category_id: str | None = None, category_url: str | None = None
    ) -> "GetResponseCategoryDTO":
        """
        Create DTO from django_pim ProductCategory.

        Args:
            product_category: ProductCategory instance from django_pim
            parent_gr_category_id: GetResponse category ID of parent (if has parent)
            category_url: Optional URL to category page

        Returns:
            GetResponseCategoryDTO instance
        """
        return cls(
            name=product_category.name[:64],  # Truncate to max 64 chars
            external_id=f"pim_cat_{product_category.id}",
            parent_id=parent_gr_category_id,
            url=category_url,
            is_default=False,
        )

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert DTO to dictionary for API request.

        Args:
            exclude_none: If True, exclude fields with None values

        Returns:
            Dictionary ready for GetResponse API
        """
        data = {
            "name": self.name,
            "externalId": self.external_id,
            "parentId": self.parent_id,
            "url": self.url,
            "isDefault": self.is_default,
        }

        if exclude_none:
            data = {k: v for k, v in data.items() if v is not None}

        return data

    def to_create_payload(self) -> dict:
        """
        Generate payload for POST /shops/{shopId}/categories.

        Returns:
            Dictionary ready for category creation
        """
        return self.to_dict(exclude_none=True)

    def to_update_payload(self, fields_to_update: list[str] | None = None) -> dict:
        """
        Generate payload for PATCH /shops/{shopId}/categories/{categoryId}.

        Args:
            fields_to_update: List of field names to include in update.
                             If None, includes all non-None fields.

        Returns:
            Dictionary ready for category update
        """
        data = self.to_dict(exclude_none=True)

        if fields_to_update is not None:
            field_mapping = {
                "name": "name",
                "external_id": "externalId",
                "parent_id": "parentId",
                "url": "url",
                "is_default": "isDefault",
            }

            filtered_data = {}
            for field in fields_to_update:
                api_field = field_mapping.get(field, field)
                if api_field in data:
                    filtered_data[api_field] = data[api_field]

            return filtered_data

        return data

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass


@dataclass
class GetResponseProductVariantDTO:
    sku: str
    name: str
    price: float
    quantity: int
    external_id: str
    url: str | None = None
    price_tax: float | None = None
    previous_price: float | None = None
    previous_price_tax: float | None = None
    images: list[dict] | None = None

    def __post_init__(self):
        self._validate_sku()
        self._validate_price()
        self._validate_quantity()
        self._validate_external_id()

    def _validate_sku(self):
        if not self.sku:
            raise ValueError("SKU is required")

    def _validate_price(self):
        if self.price < 0:
            raise ValueError(f"Price must be >= 0, got: {self.price}")

    def _validate_quantity(self):
        if self.quantity < 0:
            raise ValueError(f"Quantity must be >= 0, got: {self.quantity}")

    def _validate_external_id(self):
        if not self.external_id or len(self.external_id) > 255:
            raise ValueError("external_id required, max 255 chars")

    def to_dict(self) -> dict:
        data = self._build_base_dict()
        return self._filter_none_values(data)

    def _build_base_dict(self) -> dict:
        return {
            "sku": self.sku,
            "name": self.name,
            "price": self.price,
            "priceTax": self.price_tax,
            "previousPrice": self.previous_price,
            "previousPriceTax": self.previous_price_tax,
            "quantity": self.quantity,
            "url": self.url,
            "externalId": self.external_id,
            "images": self.images,
        }

    def _filter_none_values(self, data: dict) -> dict:
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_pim_product(cls, product, price, url, lang, media_url):
        variant_data = cls._extract_variant_data(product, price, lang, media_url)
        return cls(
            sku=product.sku,
            name=variant_data["name"],
            price=variant_data["price_gross"],
            quantity=variant_data["quantity"],
            external_id=product.sku,
            url=url,
            price_tax=variant_data["price_tax"],
            previous_price=variant_data["previous_price"],
            previous_price_tax=variant_data["previous_price_tax"],
            images=variant_data["images"],
        )

    @classmethod
    def _extract_variant_data(cls, product, price, lang, media_url):
        price_data = cls._build_price_dict(price)
        product_data = cls._extract_product_data(product, lang, media_url)
        return {**price_data, **product_data}

    @classmethod
    def _build_price_dict(cls, price):
        price_data = cls._extract_price_data(price)
        return {
            "price_gross": price_data["price_gross"],
            "price_tax": price_data["price_tax"],
            "previous_price": price_data["previous_price"],
            "previous_price_tax": price_data["previous_price_tax"],
        }

    @classmethod
    def _extract_product_data(cls, product, lang, media_url):
        return {
            "name": cls._get_product_name(product, lang),
            "quantity": cls._get_quantity(product),
            "images": cls._get_product_images(product, media_url),
        }

    @staticmethod
    def _extract_price_data(price):
        is_special = price.get("is_egible_for_special_price", False)
        special_gross = price.get("special_gross", 0)
        special_net = price.get("special_net", 0)
        if is_special and special_gross and special_net:
            special_gross = float(special_gross)
            special_net = float(special_net)
            gross = float(price.get("gross", 0))
            net = float(price.get("net", 0))

            return {
                "price_gross": special_gross,
                "price_tax": round(special_gross - special_net, 2),
                "previous_price": gross,
                "previous_price_tax": round(gross - net, 2),
            }
        else:
            gross = float(price.get("gross", 0))
            net = float(price.get("net", 0))

            return {
                "price_gross": gross,
                "price_tax": round(gross - net, 2),
                "previous_price": None,
                "previous_price_tax": None,
            }

    @staticmethod
    def _get_product_name(product, lang):
        return product.name_lang(lang)[:255]

    @staticmethod
    def _get_quantity(product):
        from django_pim.models.product_simple import ProductSimple

        if isinstance(product.as_child, ProductSimple):
            return product.as_child.quantity
        return 0

    @staticmethod
    def _get_product_images(product, media_url):
        pictures = product.general_pictures or []
        main = product.main_picture
        if main and main not in pictures:
            pictures = [main] + pictures
        if not pictures:
            return None
        return GetResponseProductVariantDTO._convert_pictures_to_images(pictures, media_url)

    @staticmethod
    def _convert_pictures_to_images(pictures, media_url):
        return [GetResponseProductVariantDTO._build_image_dict(pic, idx, media_url) for idx, pic in enumerate(pictures)]

    @staticmethod
    def _build_image_dict(picture, index: int, media_url: str) -> dict:
        full_url = GetResponseProductVariantDTO._build_full_image_url(picture, media_url)
        return {"src": full_url, "position": index + 1}

    @staticmethod
    def _build_full_image_url(picture, media_url: str) -> str:
        image_url = picture.image.url
        if image_url.startswith(("http://", "https://")):
            return image_url
        return f"{media_url}{image_url}"


@dataclass
class GetResponseProductDTO:
    name: str
    type: str
    external_id: str
    variants: list[GetResponseProductVariantDTO]
    url: str | None = None
    vendor: str | None = None
    categories: list[str] | None = None

    def __post_init__(self):
        self._validate_name()
        self._validate_type()
        self._validate_external_id()
        self._validate_variants()

    def _validate_name(self):
        if not self.name or len(self.name) < 2 or len(self.name) > 255:
            raise ValueError("Name must be 2-255 characters")

    def _validate_type(self):
        if self.type not in ["physical", "digital"]:
            raise ValueError("Type must be 'physical' or 'digital'")

    def _validate_external_id(self):
        if not self.external_id or len(self.external_id) > 255:
            raise ValueError("external_id required, max 255 chars")

    def _validate_variants(self):
        if not self.variants or len(self.variants) == 0:
            raise ValueError("At least one variant is required")

    def to_dict(self) -> dict:
        data = self._build_base_dict()
        return self._filter_none_values(data)

    def _build_base_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "url": self.url,
            "vendor": self.vendor,
            "categories": self.categories,
            "variants": [v.to_dict() for v in self.variants],
            "externalId": self.external_id,
        }

    def _filter_none_values(self, data: dict) -> dict:
        return {k: v for k, v in data.items() if v is not None}

    def to_create_payload(self) -> dict:
        return self.to_dict()

    def to_update_payload(self) -> dict:
        return self.to_dict()

    @classmethod
    def from_pim_product(cls, product, variants_dto, url, categories, lang):
        name = cls._get_product_name(product, lang)
        product_type = cls._get_product_type(product)
        return cls(
            name=name,
            type=product_type,
            external_id=product.sku,
            variants=variants_dto,
            url=url,
            vendor=None,
            categories=categories,
        )

    @staticmethod
    def _get_product_name(product, lang):
        return product.name_lang(lang)[:255]

    @staticmethod
    def _get_product_type(product):
        return "physical"

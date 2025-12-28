"""eBay Inventory API client for listings and offers."""

from datetime import datetime
from decimal import Decimal
from typing import Generator, Optional

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential

from src.ebay.auth import EbayAuth
from src.ebay.models import (
    Amount,
    InventoryItem,
    ListingFormat,
    ListingStatus,
    Offer,
)
from src.utils.logging import get_logger

logger = get_logger("ebay.inventory")

CALLS_PER_MINUTE = 500
ONE_MINUTE = 60


class InventoryClient:
    """Client for eBay Inventory API.

    Handles inventory items and offer (listing) management.
    """

    BASE_URL = "https://apiz.ebay.com/sell/inventory/v1"

    def __init__(self, auth: EbayAuth) -> None:
        """Initialize the Inventory API client.

        Args:
            auth: EbayAuth instance for authentication.
        """
        self.auth = auth

    @sleep_and_retry
    @limits(calls=CALLS_PER_MINUTE, period=ONE_MINUTE)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _make_request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> dict:
        """Make a rate-limited, retrying request to the Inventory API.

        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            requests.HTTPError: If request fails after retries
        """
        url = f"{self.BASE_URL}/{endpoint}"
        response = requests.get(
            url,
            headers=self.auth.get_rest_headers(),
            params=params,
            timeout=30,
        )

        if response.status_code == 401:
            logger.error("Authentication failed - token may be expired")
            raise requests.HTTPError("eBay token expired or invalid", response=response)

        response.raise_for_status()
        return response.json()

    def get_inventory_items(self) -> Generator[InventoryItem, None, None]:
        """Get all inventory items.

        Yields:
            InventoryItem objects
        """
        offset = 0
        limit = 100

        while True:
            params = {
                "limit": limit,
                "offset": offset,
            }

            logger.debug(f"Fetching inventory items: offset={offset}")
            data = self._make_request("inventory_item", params)

            items = data.get("inventoryItems", [])
            if not items:
                break

            for item_data in items:
                yield self._parse_inventory_item(item_data)

            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

    def get_inventory_item(self, sku: str) -> Optional[InventoryItem]:
        """Get a specific inventory item by SKU.

        Args:
            sku: Seller's SKU (we use item ID)

        Returns:
            InventoryItem or None if not found
        """
        try:
            data = self._make_request(f"inventory_item/{sku}")
            return self._parse_inventory_item(data)
        except requests.HTTPError as e:
            if e.response and e.response.status_code == 404:
                return None
            raise

    def _parse_inventory_item(self, data: dict) -> InventoryItem:
        """Parse an inventory item from API response.

        Args:
            data: Inventory item data from API

        Returns:
            InventoryItem object
        """
        product = data.get("product", {})
        availability = data.get("availability", {})
        ship_to_location = availability.get("shipToLocationAvailability", {})

        # Parse aspects (item specifics)
        aspects = product.get("aspects", {})

        return InventoryItem(
            sku=data.get("sku", ""),
            condition=data.get("condition"),
            condition_description=data.get("conditionDescription"),
            availability=ship_to_location.get("quantity"),
            product_title=product.get("title"),
            product_description=product.get("description"),
            aspects=aspects,
        )

    def get_offers(self, status: Optional[str] = None) -> Generator[Offer, None, None]:
        """Get all offers (listings).

        Args:
            status: Optional filter by status (PUBLISHED, UNPUBLISHED)

        Yields:
            Offer objects
        """
        offset = 0
        limit = 100

        while True:
            params = {
                "limit": limit,
                "offset": offset,
            }
            if status:
                params["status"] = status

            logger.debug(f"Fetching offers: offset={offset}")
            data = self._make_request("offer", params)

            offers = data.get("offers", [])
            if not offers:
                break

            for offer_data in offers:
                yield self._parse_offer(offer_data)

            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

    def get_offer(self, offer_id: str) -> Optional[Offer]:
        """Get a specific offer by ID.

        Args:
            offer_id: eBay offer ID

        Returns:
            Offer or None if not found
        """
        try:
            data = self._make_request(f"offer/{offer_id}")
            return self._parse_offer(data)
        except requests.HTTPError as e:
            if e.response and e.response.status_code == 404:
                return None
            raise

    def _parse_offer(self, data: dict) -> Offer:
        """Parse an offer from API response.

        Args:
            data: Offer data from API

        Returns:
            Offer object
        """
        # Parse price
        price_data = data.get("pricingSummary", {}).get("price", {})
        price = Amount(
            value=Decimal(price_data.get("value", "0")),
            currency=price_data.get("currency", "USD"),
        )

        # Parse format
        format_str = data.get("format", "FIXED_PRICE")
        try:
            listing_format = ListingFormat(format_str)
        except ValueError:
            listing_format = ListingFormat.FIXED_PRICE

        # Parse status
        status_str = data.get("status", "ACTIVE")
        try:
            status = ListingStatus(status_str)
        except ValueError:
            status = ListingStatus.ACTIVE

        # Parse listing dates
        listing_start = None
        listing_end = None
        if data.get("listingStartDate"):
            listing_start = datetime.fromisoformat(
                data["listingStartDate"].replace("Z", "+00:00")
            )
        if data.get("listingEndDate"):
            listing_end = datetime.fromisoformat(
                data["listingEndDate"].replace("Z", "+00:00")
            )

        # Check for promoted listing
        listing_policies = data.get("listingPolicies", {})
        promoted = False
        promoted_rate = None
        # Note: Promoted listing info might be in a different endpoint

        return Offer(
            offer_id=data.get("offerId", ""),
            sku=data.get("sku", ""),
            item_id=data.get("listing", {}).get("listingId"),
            marketplace_id=data.get("marketplaceId", "EBAY_US"),
            format=listing_format,
            status=status,
            price=price,
            quantity=data.get("availableQuantity", 1),
            quantity_sold=data.get("quantitySold", 0),
            category_id=data.get("categoryId"),
            listing_start_date=listing_start,
            listing_end_date=listing_end,
            shipping_policy_id=listing_policies.get("shippingPolicyId"),
            return_policy_id=listing_policies.get("returnPolicyId"),
            payment_policy_id=listing_policies.get("paymentPolicyId"),
            promoted_listing=promoted,
            promoted_listing_rate=promoted_rate,
        )

    def get_offers_by_sku(self, sku: str) -> list[Offer]:
        """Get all offers for a specific SKU.

        Args:
            sku: Seller's SKU (we use item ID)

        Returns:
            List of Offer objects
        """
        params = {
            "sku": sku,
            "limit": 100,
        }

        data = self._make_request("offer", params)
        offers = []

        for offer_data in data.get("offers", []):
            offers.append(self._parse_offer(offer_data))

        return offers

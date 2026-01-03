"""eBay Browse API client for fetching public item data."""

import requests
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from src.ebay.auth import EbayAuth
from src.utils.logging import get_logger

logger = get_logger("ebay.browse")


class BrowseClient:
    """Client for eBay Browse API to fetch public item details.

    The Browse API provides read-only access to public listing data,
    including item titles, images, and descriptions - without requiring
    seller-specific scopes.
    """

    BASE_URL = "https://api.ebay.com/buy/browse/v1"

    def __init__(self, auth: EbayAuth) -> None:
        """Initialize Browse API client.

        Args:
            auth: EbayAuth instance for authentication
        """
        self.auth = auth

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def get_item(self, item_id: str) -> Optional[dict]:
        """Get public item details by item ID.

        Args:
            item_id: eBay item ID (e.g., "v1|123456789|0")

        Returns:
            Item data dict or None if not found
        """
        # Handle different item ID formats
        # The Browse API expects legacy item IDs or the v1| format
        if not item_id.startswith("v1|"):
            # Try as legacy ID
            url = f"{self.BASE_URL}/item/v1|{item_id}|0"
        else:
            url = f"{self.BASE_URL}/item/{item_id}"

        try:
            response = requests.get(
                url,
                headers=self.auth.get_rest_headers(),
                timeout=30,
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                # Item not found - try alternate format
                if not item_id.startswith("v1|"):
                    # Try without the v1| wrapper
                    alt_url = f"{self.BASE_URL}/item/v1|{item_id}|0"
                    alt_response = requests.get(
                        alt_url,
                        headers=self.auth.get_rest_headers(),
                        timeout=30,
                    )
                    if alt_response.status_code == 200:
                        return alt_response.json()
                logger.debug(f"Item {item_id} not found in Browse API")
                return None
            else:
                logger.warning(f"Browse API error {response.status_code} for item {item_id}")
                return None

        except requests.RequestException as e:
            logger.error(f"Browse API request failed: {e}")
            return None

    def get_item_title(self, item_id: str) -> Optional[str]:
        """Get just the title for an item.

        Args:
            item_id: eBay item ID

        Returns:
            Item title or None if not found
        """
        item = self.get_item(item_id)
        if item:
            return item.get("title")
        return None

    def get_item_details(self, item_id: str) -> Optional[dict]:
        """Get key details for an item.

        Args:
            item_id: eBay item ID

        Returns:
            Dict with title, image, category, condition or None
        """
        item = self.get_item(item_id)
        if not item:
            return None

        return {
            "title": item.get("title"),
            "image_url": item.get("image", {}).get("imageUrl"),
            "category": item.get("categoryPath"),
            "condition": item.get("condition"),
            "price": item.get("price", {}).get("value"),
        }

    def enrich_items_with_titles(self, items: dict) -> int:
        """Enrich a dict of items with titles from Browse API.

        Note: Browse API only works for ACTIVE listings. Once an item sells
        and the listing ends, it's removed from the public catalog and
        cannot be looked up. This method is most useful for enriching
        items that are still listed or were recently listed.

        Args:
            items: Dict of item_id -> SyncedItem

        Returns:
            Number of items enriched
        """
        enriched = 0
        attempted = 0

        for item_id, item in items.items():
            # Skip if already has a real title
            if item.title and not item.title.startswith("(") and item.title != item_id:
                continue

            attempted += 1
            title = self.get_item_title(item_id)
            if title:
                item.title = title
                enriched += 1
                logger.debug(f"Enriched item {item_id} with title: {title[:50]}...")

        if attempted > 0:
            logger.info(
                f"Browse API: enriched {enriched}/{attempted} items "
                f"(sold items may not be available in public catalog)"
            )

        return enriched

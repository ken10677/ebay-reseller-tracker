"""eBay Trading API client for legacy XML API access.

The Trading API provides additional data not available in RESTful APIs:
- View count (HitCount)
- Watch count (WatchCount)
- Question count
- Best offer details
- Full item specifics
- Description HTML
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from xml.etree import ElementTree as ET

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential

from src.ebay.auth import EbayAuth
from src.ebay.models import Amount, ListingDetails, ListingFormat
from src.utils.logging import get_logger

logger = get_logger("ebay.trading")

CALLS_PER_MINUTE = 500
ONE_MINUTE = 60


class TradingClient:
    """Client for eBay Trading API (legacy XML API).

    Provides access to listing metrics not available in RESTful APIs.
    Gracefully degrades if Trading API access is not configured.
    """

    BASE_URL = "https://api.ebay.com/ws/api.dll"

    def __init__(self, auth: EbayAuth) -> None:
        """Initialize the Trading API client.

        Args:
            auth: EbayAuth instance for authentication.
        """
        self.auth = auth
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if Trading API access is configured and working.

        Returns:
            True if Trading API is available, False otherwise.
        """
        if self._available is not None:
            return self._available

        if not self.auth.has_trading_api():
            logger.info("Trading API token not configured - metrics will be limited")
            self._available = False
            return False

        # Try a simple API call to verify access
        try:
            self._make_request("GeteBayOfficialTime", "<GeteBayOfficialTimeRequest/>")
            self._available = True
            logger.info("Trading API access verified")
            return True
        except Exception as e:
            logger.warning(f"Trading API access check failed: {e}")
            self._available = False
            return False

    @sleep_and_retry
    @limits(calls=CALLS_PER_MINUTE, period=ONE_MINUTE)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _make_request(self, call_name: str, request_body: str) -> ET.Element:
        """Make a rate-limited, retrying request to the Trading API.

        Args:
            call_name: API call name (e.g., 'GetItem')
            request_body: XML request body

        Returns:
            ElementTree Element of response

        Raises:
            requests.HTTPError: If request fails after retries
            ValueError: If Trading API is not configured
        """
        if not self.auth.has_trading_api():
            raise ValueError("Trading API token not configured")

        # Build full XML request
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<{call_name}Request xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{self.auth.trading_token}</eBayAuthToken>
    </RequesterCredentials>
    {request_body}
</{call_name}Request>"""

        response = requests.post(
            self.BASE_URL,
            headers=self.auth.get_trading_headers(call_name),
            data=xml_request.encode("utf-8"),
            timeout=30,
        )

        response.raise_for_status()

        # Parse XML response
        root = ET.fromstring(response.content)

        # Check for API errors
        ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}
        ack = root.find(".//ebay:Ack", ns)
        if ack is not None and ack.text == "Failure":
            errors = root.findall(".//ebay:Errors/ebay:LongMessage", ns)
            error_msgs = [e.text for e in errors if e.text]
            raise ValueError(f"eBay Trading API error: {'; '.join(error_msgs)}")

        return root

    def get_item(self, item_id: str) -> Optional[ListingDetails]:
        """Get detailed item information using GetItem call.

        Args:
            item_id: eBay item ID

        Returns:
            ListingDetails or None if item not found or API unavailable
        """
        if not self.is_available():
            return None

        try:
            request_body = f"""
    <ItemID>{item_id}</ItemID>
    <IncludeWatchCount>true</IncludeWatchCount>
    <DetailLevel>ReturnAll</DetailLevel>"""

            root = self._make_request("GetItem", request_body)
            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}

            item = root.find(".//ebay:Item", ns)
            if item is None:
                return None

            return self._parse_item(item, ns)

        except Exception as e:
            logger.warning(f"Failed to get item {item_id} from Trading API: {e}")
            return None

    def _parse_item(self, item: ET.Element, ns: dict) -> ListingDetails:
        """Parse item element from GetItem response.

        Args:
            item: XML Element for the item
            ns: XML namespace dict

        Returns:
            ListingDetails object
        """

        def get_text(path: str) -> Optional[str]:
            elem = item.find(path, ns)
            return elem.text if elem is not None else None

        def get_int(path: str, default: int = 0) -> int:
            text = get_text(path)
            return int(text) if text else default

        def get_decimal(path: str) -> Optional[Decimal]:
            text = get_text(path)
            return Decimal(text) if text else None

        def get_amount(path: str) -> Optional[Amount]:
            elem = item.find(path, ns)
            if elem is not None and elem.text:
                currency = elem.get("currencyID", "USD")
                return Amount(value=Decimal(elem.text), currency=currency)
            return None

        def get_datetime(path: str) -> Optional[datetime]:
            text = get_text(path)
            if text:
                try:
                    return datetime.fromisoformat(text.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        # Get category info
        category_id = get_text(".//ebay:PrimaryCategory/ebay:CategoryID")
        category_path_elem = item.find(".//ebay:PrimaryCategory/ebay:CategoryName", ns)
        category_name = category_path_elem.text if category_path_elem is not None else None

        # Get condition
        condition_id = get_text(".//ebay:ConditionID")
        condition_name = get_text(".//ebay:ConditionDisplayName")

        # Best offer info
        best_offer_enabled = get_text(".//ebay:BestOfferDetails/ebay:BestOfferEnabled") == "true"

        # Count item specifics
        item_specifics = item.findall(".//ebay:ItemSpecifics/ebay:NameValueList", ns)
        item_specifics_count = len(item_specifics)

        # Get description length
        description = get_text(".//ebay:Description") or ""
        description_length = len(description)

        # Count photos
        picture_urls = item.findall(".//ebay:PictureDetails/ebay:PictureURL", ns)
        photo_count = len(picture_urls)

        # Get shipping info
        shipping_service = get_text(".//ebay:ShippingDetails/ebay:ShippingServiceOptions/ebay:ShippingService")
        free_shipping_elem = item.find(".//ebay:ShippingDetails/ebay:ShippingServiceOptions/ebay:FreeShipping", ns)
        free_shipping = free_shipping_elem is not None and free_shipping_elem.text == "true"

        # Get return policy
        returns_accepted = get_text(".//ebay:ReturnPolicy/ebay:ReturnsAccepted") == "ReturnsAccepted"
        return_period = get_text(".//ebay:ReturnPolicy/ebay:ReturnsWithin")

        # Get listing format
        format_str = get_text(".//ebay:ListingType")
        if format_str == "FixedPriceItem":
            listing_format = ListingFormat.FIXED_PRICE
        elif format_str in ("Chinese", "Auction"):
            listing_format = ListingFormat.AUCTION
        else:
            listing_format = ListingFormat.FIXED_PRICE

        # Quantity info
        quantity = get_int(".//ebay:Quantity", 1)
        quantity_sold = get_int(".//ebay:SellingStatus/ebay:QuantitySold", 0)

        return ListingDetails(
            item_id=get_text(".//ebay:ItemID") or "",
            title=get_text(".//ebay:Title") or "Unknown",
            category_id=category_id,
            category_name=category_name,
            condition_id=condition_id,
            condition_name=condition_name,
            current_price=get_amount(".//ebay:SellingStatus/ebay:CurrentPrice"),
            start_price=get_amount(".//ebay:StartPrice"),
            best_offer_enabled=best_offer_enabled,
            best_offer_auto_accept=get_amount(".//ebay:BestOfferDetails/ebay:BestOfferAutoAcceptPrice"),
            best_offer_minimum=get_amount(".//ebay:BestOfferDetails/ebay:MinimumBestOfferPrice"),
            start_date=get_datetime(".//ebay:ListingDetails/ebay:StartTime"),
            end_date=get_datetime(".//ebay:ListingDetails/ebay:EndTime"),
            view_count=get_int(".//ebay:HitCount", 0),
            watch_count=get_int(".//ebay:WatchCount", 0),
            question_count=get_int(".//ebay:GetItFast", 0),  # Questions not directly available
            offer_count=0,  # Would need separate call
            description_length=description_length,
            photo_count=photo_count,
            item_specifics_count=item_specifics_count,
            free_shipping=free_shipping,
            shipping_service=shipping_service,
            returns_accepted=returns_accepted,
            return_period=return_period,
            listing_format=listing_format,
            quantity=quantity,
            quantity_sold=quantity_sold,
            quantity_available=quantity - quantity_sold,
        )

    def get_seller_list(
        self,
        start_date: datetime,
        end_date: datetime,
        include_watch_count: bool = True,
    ) -> list[ListingDetails]:
        """Get all seller's listings within a date range.

        More efficient than calling GetItem for each listing.

        Args:
            start_date: Start of date range
            end_date: End of date range
            include_watch_count: Whether to include watch counts

        Returns:
            List of ListingDetails objects
        """
        if not self.is_available():
            return []

        results = []
        page = 1

        try:
            while True:
                request_body = f"""
    <StartTimeFrom>{start_date.isoformat()}</StartTimeFrom>
    <StartTimeTo>{end_date.isoformat()}</StartTimeTo>
    <IncludeWatchCount>{str(include_watch_count).lower()}</IncludeWatchCount>
    <DetailLevel>ReturnAll</DetailLevel>
    <Pagination>
        <EntriesPerPage>100</EntriesPerPage>
        <PageNumber>{page}</PageNumber>
    </Pagination>"""

                root = self._make_request("GetSellerList", request_body)
                ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}

                items = root.findall(".//ebay:ItemArray/ebay:Item", ns)
                if not items:
                    break

                for item in items:
                    try:
                        results.append(self._parse_item(item, ns))
                    except Exception as e:
                        logger.warning(f"Failed to parse item: {e}")

                # Check pagination
                total_pages_elem = root.find(".//ebay:PaginationResult/ebay:TotalNumberOfPages", ns)
                total_pages = int(total_pages_elem.text) if total_pages_elem is not None else 1

                if page >= total_pages:
                    break
                page += 1

        except Exception as e:
            logger.warning(f"Failed to get seller list: {e}")

        return results

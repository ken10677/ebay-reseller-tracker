"""eBay Fulfillment API client for orders and shipping."""

from datetime import datetime, date
from decimal import Decimal
from typing import Generator, Optional

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential

from src.ebay.auth import EbayAuth
from src.ebay.models import (
    Amount,
    Order,
    OrderLineItem,
    OrderStatus,
    ShippingAddress,
)
from src.utils.logging import get_logger

logger = get_logger("ebay.fulfillment")

CALLS_PER_MINUTE = 500
ONE_MINUTE = 60


class FulfillmentClient:
    """Client for eBay Fulfillment API.

    Handles order retrieval and shipping information.
    """

    BASE_URL = "https://apiz.ebay.com/sell/fulfillment/v1"

    def __init__(self, auth: EbayAuth) -> None:
        """Initialize the Fulfillment API client.

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
        """Make a rate-limited, retrying request to the Fulfillment API.

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

        if response.status_code == 403:
            logger.error(f"Access denied (403) - token lacks required scopes")
            logger.error(f"Required scope: https://api.ebay.com/oauth/api_scope/sell.fulfillment")
            raise requests.HTTPError("eBay access denied - missing sell.fulfillment scope", response=response)

        if response.status_code == 404:
            # 404 can also mean access denied for this API
            error_text = response.text[:500]
            if "Resource not found" in error_text:
                logger.warning(f"Fulfillment API returned 404 - token may lack sell.fulfillment scope")
                logger.warning("Item titles will not be available. Consider getting OAuth token with proper scopes.")
            logger.debug(f"HTTP 404: {error_text}")

        if not response.ok:
            logger.debug(f"HTTP {response.status_code}: {response.text[:500]}")

        response.raise_for_status()
        return response.json()

    def get_orders(
        self,
        start_date: date,
        end_date: Optional[date] = None,
    ) -> Generator[Order, None, None]:
        """Get orders within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range (defaults to today)

        Yields:
            Order objects
        """
        if end_date is None:
            end_date = date.today()

        # Build date filter in eBay's format
        start_str = f"{start_date.isoformat()}T00:00:00Z"
        end_str = f"{end_date.isoformat()}T23:59:59Z"
        date_filter = f"creationdate:[{start_str}..{end_str}]"

        offset = 0
        limit = 50  # Max per page for orders

        while True:
            params = {
                "filter": date_filter,
                "limit": limit,
                "offset": offset,
            }

            logger.debug(f"Fetching orders: offset={offset}")
            data = self._make_request("order", params)

            orders = data.get("orders", [])
            if not orders:
                break

            for order_data in orders:
                yield self._parse_order(order_data)

            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

        logger.info(f"Retrieved orders from {start_date} to {end_date}")

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get a specific order by ID.

        Args:
            order_id: eBay order ID

        Returns:
            Order object or None if not found
        """
        try:
            data = self._make_request(f"order/{order_id}")
            return self._parse_order(data)
        except requests.HTTPError as e:
            if e.response and e.response.status_code == 404:
                logger.warning(f"Order not found: {order_id}")
                return None
            raise

    def _parse_order(self, data: dict) -> Order:
        """Parse an order from API response.

        Args:
            data: Order data from API

        Returns:
            Order object
        """
        # Parse line items
        line_items = []
        for item_data in data.get("lineItems", []):
            unit_price_data = item_data.get("lineItemCost", {})
            total_data = item_data.get("total", {})

            # Get shipping cost for this line item if available
            delivery_cost = item_data.get("deliveryCost", {})
            shipping_data = delivery_cost.get("shippingCost", {})

            line_items.append(
                OrderLineItem(
                    line_item_id=item_data.get("lineItemId", ""),
                    item_id=item_data.get("legacyItemId", ""),
                    title=item_data.get("title", "Unknown"),
                    sku=item_data.get("sku"),
                    quantity=item_data.get("quantity", 1),
                    unit_price=Amount(
                        value=Decimal(unit_price_data.get("value", "0")),
                        currency=unit_price_data.get("currency", "USD"),
                    ),
                    total_price=Amount(
                        value=Decimal(total_data.get("value", "0")),
                        currency=total_data.get("currency", "USD"),
                    ),
                    shipping_cost=Amount(
                        value=Decimal(shipping_data.get("value", "0")),
                        currency=shipping_data.get("currency", "USD"),
                    )
                    if shipping_data
                    else None,
                )
            )

        # Parse pricing summary
        pricing = data.get("pricingSummary", {})
        subtotal_data = pricing.get("priceSubtotal", {})
        delivery_data = pricing.get("deliveryCost", {})
        total_data = pricing.get("total", {})

        # Parse shipping address (zone info only, no PII)
        shipping_address = None
        fulfill_start = data.get("fulfillmentStartInstructions", [])
        if fulfill_start:
            ship_to = fulfill_start[0].get("shippingStep", {}).get("shipTo", {})
            contact_address = ship_to.get("contactAddress", {})
            if contact_address:
                shipping_address = ShippingAddress(
                    state_or_province=contact_address.get("stateOrProvince"),
                    postal_code=contact_address.get("postalCode"),
                    country=contact_address.get("countryCode", "US"),
                )

        # Parse dates
        creation_date_str = data.get("creationDate", "")
        creation_date = datetime.fromisoformat(creation_date_str.replace("Z", "+00:00"))

        paid_date = None
        payment_summary = data.get("paymentSummary", {})
        for payment in payment_summary.get("payments", []):
            if payment.get("paymentStatus") == "PAID":
                paid_str = payment.get("paymentDate", "")
                if paid_str:
                    paid_date = datetime.fromisoformat(paid_str.replace("Z", "+00:00"))
                break

        # Parse order status
        status_str = data.get("orderFulfillmentStatus", "ACTIVE")
        try:
            order_status = OrderStatus(status_str)
        except ValueError:
            order_status = OrderStatus.ACTIVE

        # Get buyer username
        buyer = data.get("buyer", {})
        buyer_username = buyer.get("username")

        return Order(
            order_id=data.get("orderId", ""),
            creation_date=creation_date,
            order_status=order_status,
            line_items=line_items,
            subtotal=Amount(
                value=Decimal(subtotal_data.get("value", "0")),
                currency=subtotal_data.get("currency", "USD"),
            ),
            shipping_cost=Amount(
                value=Decimal(delivery_data.get("value", "0")),
                currency=delivery_data.get("currency", "USD"),
            ),
            total=Amount(
                value=Decimal(total_data.get("value", "0")),
                currency=total_data.get("currency", "USD"),
            ),
            shipping_address=shipping_address,
            buyer_username=buyer_username,
            paid_date=paid_date,
        )

    def get_shipping_fulfillments(self, order_id: str) -> list[dict]:
        """Get shipping fulfillment info for an order.

        Args:
            order_id: eBay order ID

        Returns:
            List of shipping fulfillment records
        """
        try:
            data = self._make_request(f"order/{order_id}/shipping_fulfillment")
            return data.get("fulfillments", [])
        except requests.HTTPError as e:
            if e.response and e.response.status_code == 404:
                return []
            raise

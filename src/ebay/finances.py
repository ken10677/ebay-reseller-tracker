"""eBay Finances API client for transactions, payouts, and fees."""

from datetime import datetime, date
from decimal import Decimal
from typing import Generator, Optional

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential

from src.ebay.auth import EbayAuth
from src.ebay.models import (
    Amount,
    FeeBreakdown,
    Payout,
    Transaction,
    TransactionType,
)
from src.utils.logging import get_logger

logger = get_logger("ebay.finances")

# eBay API rate limits: 1000 calls per minute for Finances API
CALLS_PER_MINUTE = 500  # Stay well under limit
ONE_MINUTE = 60


class FinancesClient:
    """Client for eBay Finances API.

    Handles transactions, payouts, and fee data retrieval.
    """

    BASE_URL = "https://apiz.ebay.com/sell/finances/v1"

    def __init__(self, auth: EbayAuth) -> None:
        """Initialize the Finances API client.

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
        """Make a rate-limited, retrying request to the Finances API.

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

    def get_transactions(
        self,
        start_date: date,
        end_date: Optional[date] = None,
        transaction_type: Optional[str] = None,
    ) -> Generator[Transaction, None, None]:
        """Get transactions within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range (defaults to today)
            transaction_type: Optional filter by type (SALE, REFUND, etc.)

        Yields:
            Transaction objects
        """
        if end_date is None:
            end_date = date.today()

        # Build date filter in eBay's format
        start_str = f"{start_date.isoformat()}T00:00:00Z"
        end_str = f"{end_date.isoformat()}T23:59:59Z"
        date_filter = f"transactionDate:[{start_str}..{end_str}]"

        filters = [date_filter]
        if transaction_type:
            filters.append(f"transactionType:{{{transaction_type}}}")

        filter_str = ",".join(filters)

        offset = 0
        limit = 100  # Max per page

        while True:
            params = {
                "filter": filter_str,
                "limit": limit,
                "offset": offset,
            }

            logger.debug(f"Fetching transactions: offset={offset}")
            data = self._make_request("transaction", params)

            transactions = data.get("transactions", [])
            if not transactions:
                break

            for tx_data in transactions:
                yield self._parse_transaction(tx_data)

            # Check if there are more pages
            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

        logger.info(f"Retrieved {offset} transactions from {start_date} to {end_date}")

    def _parse_transaction(self, data: dict) -> Transaction:
        """Parse a transaction from API response.

        Args:
            data: Transaction data from API

        Returns:
            Transaction object
        """
        # Note on Finances API fields for SALE transactions:
        # - amount: Net to seller AFTER fees are deducted
        # - totalFeeBasisAmount: Gross sales (item + shipping) BEFORE fees
        # - ebayCollectedTaxAmount: Sales tax collected by eBay (not included in amount or feeBasis)
        tx_type = data.get("transactionType", "")

        # Log detailed info for reconciliation debugging
        if tx_type in ("SALE", "REFUND"):
            amount_val = data.get("amount", {}).get("value", "0")
            fee_basis_val = data.get("totalFeeBasisAmount", {}).get("value", "0") if "totalFeeBasisAmount" in data else "N/A"
            total_fee_val = data.get("totalFeeAmount", {}).get("value", "0") if "totalFeeAmount" in data else "N/A"
            logger.info(f"{tx_type}: amount=${amount_val}, feeBasis=${fee_basis_val}, totalFee=${total_fee_val}")

        # Parse amount (net to seller after fees)
        amount_data = data.get("amount", {})
        amount = Amount(
            value=Decimal(amount_data.get("value", "0")),
            currency=amount_data.get("currency", "USD"),
        )

        # Parse fee basis amount (gross item + shipping, before fees)
        # This is what eBay fees are calculated on
        fee_basis_amount = None
        if "totalFeeBasisAmount" in data:
            fee_basis_data = data["totalFeeBasisAmount"]
            fee_basis_amount = Amount(
                value=Decimal(fee_basis_data.get("value", "0")),
                currency=fee_basis_data.get("currency", "USD"),
            )

        # Parse total fee amount if present
        fee_amount = None
        if "totalFeeAmount" in data:
            fee_data = data["totalFeeAmount"]
            fee_amount = Amount(
                value=Decimal(fee_data.get("value", "0")),
                currency=fee_data.get("currency", "USD"),
            )

        # Parse fee breakdown from multiple possible locations
        fee_breakdown = []

        # Check orderLineItems for fees
        for line_item in data.get("orderLineItems", []):
            # Get marketplace fees
            for fee_data in line_item.get("marketplaceFees", []):
                fee_breakdown.append(
                    FeeBreakdown(
                        fee_type=fee_data.get("feeType", "OTHER"),
                        amount=Amount(
                            value=Decimal(fee_data.get("amount", {}).get("value", "0")),
                            currency=fee_data.get("amount", {}).get("currency", "USD"),
                        ),
                        description=fee_data.get("feeType"),
                    )
                )

            # Check for fees in feeBasisAmount structure
            for fee_data in line_item.get("fees", []):
                fee_breakdown.append(
                    FeeBreakdown(
                        fee_type=fee_data.get("feeType", "OTHER"),
                        amount=Amount(
                            value=Decimal(fee_data.get("amount", {}).get("value", "0")),
                            currency=fee_data.get("amount", {}).get("currency", "USD"),
                        ),
                        description=fee_data.get("feeType"),
                    )
                )

        # Also check top-level totalFeeAmount for any fees not in line items
        if "totalFeeAmount" in data and not fee_breakdown:
            total_fee = data["totalFeeAmount"]
            fee_breakdown.append(
                FeeBreakdown(
                    fee_type="TOTAL_FEE",
                    amount=Amount(
                        value=Decimal(total_fee.get("value", "0")),
                        currency=total_fee.get("currency", "USD"),
                    ),
                    description="Total fees",
                )
            )

        # Log fee types found for debugging
        if fee_breakdown:
            fee_types = [f.fee_type for f in fee_breakdown]
            logger.debug(f"Transaction fees found: {fee_types}")

        # Parse transaction type
        tx_type_str = data.get("transactionType", "OTHER")
        try:
            tx_type = TransactionType(tx_type_str)
        except ValueError:
            tx_type = TransactionType.OTHER

        # Parse date
        tx_date_str = data.get("transactionDate", "")
        tx_date = datetime.fromisoformat(tx_date_str.replace("Z", "+00:00"))

        # Get order ID from references
        order_id = None
        references = data.get("references", [])
        for ref in references:
            if ref.get("referenceType") == "ORDER_ID":
                order_id = ref.get("referenceId")
                break


        # Get item ID, title, and shipping from order line items
        # Note: Finances API doesn't include item titles - only financial data
        # Titles would need to come from Fulfillment API (requires OAuth with proper scopes)
        item_id = None
        item_title = None
        item_amount = None
        shipping_amount = None
        line_items = data.get("orderLineItems", [])
        if line_items:
            first_item = line_items[0]
            item_id = first_item.get("itemId")
            item_title = first_item.get("title")
            # Use lineItemId as fallback for item_id
            if not item_id:
                item_id = first_item.get("lineItemId")

            # Parse item amount (price without shipping)
            # The lineItemAmount or itemPrice field contains just the item price
            if "lineItemAmount" in first_item:
                li_amount = first_item["lineItemAmount"]
                item_amount = Amount(
                    value=Decimal(li_amount.get("value", "0")),
                    currency=li_amount.get("currency", "USD"),
                )

            # Parse shipping amount from deliveryCost
            if "deliveryCost" in first_item:
                dc = first_item["deliveryCost"]
                shipping_amount = Amount(
                    value=Decimal(dc.get("value", "0")),
                    currency=dc.get("currency", "USD"),
                )

        # Sum up shipping from all line items if there are multiple
        total_shipping = Decimal(0)
        total_item_amount = Decimal(0)
        for li in line_items:
            if "deliveryCost" in li:
                dc = li["deliveryCost"]
                total_shipping += Decimal(dc.get("value", "0"))
            if "lineItemAmount" in li:
                la = li["lineItemAmount"]
                total_item_amount += Decimal(la.get("value", "0"))

        # If we found shipping across all line items, use the total
        if total_shipping > 0:
            shipping_amount = Amount(value=total_shipping, currency="USD")
        if total_item_amount > 0:
            item_amount = Amount(value=total_item_amount, currency="USD")

        return Transaction(
            transaction_id=data.get("transactionId", ""),
            transaction_type=tx_type,
            transaction_date=tx_date,
            order_id=order_id,
            item_id=item_id,
            title=item_title,
            amount=amount,
            fee_basis_amount=fee_basis_amount,
            item_amount=item_amount,
            shipping_amount=shipping_amount,
            fee_amount=fee_amount,
            fee_breakdown=fee_breakdown,
            payout_id=data.get("payoutId"),
            description=data.get("transactionMemo"),
        )

    def get_transaction_by_order(self, order_id: str) -> list[Transaction]:
        """Get all transactions for a specific order.

        Args:
            order_id: eBay order ID

        Returns:
            List of transactions for the order
        """
        params = {
            "filter": f"orderId:{{{order_id}}}",
            "limit": 100,
        }

        data = self._make_request("transaction", params)
        transactions = []

        for tx_data in data.get("transactions", []):
            transactions.append(self._parse_transaction(tx_data))

        return transactions

    def get_payouts(
        self,
        start_date: date,
        end_date: Optional[date] = None,
    ) -> Generator[Payout, None, None]:
        """Get payouts within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range (defaults to today)

        Yields:
            Payout objects
        """
        if end_date is None:
            end_date = date.today()

        start_str = f"{start_date.isoformat()}T00:00:00Z"
        end_str = f"{end_date.isoformat()}T23:59:59Z"
        date_filter = f"payoutDate:[{start_str}..{end_str}]"

        offset = 0
        limit = 100

        while True:
            params = {
                "filter": date_filter,
                "limit": limit,
                "offset": offset,
            }

            data = self._make_request("payout", params)
            payouts = data.get("payouts", [])

            if not payouts:
                break

            for payout_data in payouts:
                amount_data = payout_data.get("amount", {})
                payout_date_str = payout_data.get("payoutDate", "")
                payout_date = datetime.fromisoformat(payout_date_str.replace("Z", "+00:00"))

                yield Payout(
                    payout_id=payout_data.get("payoutId", ""),
                    payout_date=payout_date,
                    amount=Amount(
                        value=Decimal(amount_data.get("value", "0")),
                        currency=amount_data.get("currency", "USD"),
                    ),
                    status=payout_data.get("payoutStatus", "UNKNOWN"),
                    transaction_count=payout_data.get("transactionCount", 0),
                )

            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

    def get_seller_funds_summary(self) -> dict:
        """Get summary of seller's available funds.

        Returns:
            Dict with available funds, processing funds, etc.
        """
        data = self._make_request("seller_funds_summary")
        return {
            "available_funds": data.get("availableFunds", {}),
            "funds_on_hold": data.get("fundsOnHold", {}),
            "processing_funds": data.get("processingFunds", {}),
            "total_funds": data.get("totalFunds", {}),
        }

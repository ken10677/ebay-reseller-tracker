"""Tests for eBay data models."""

from datetime import datetime
from decimal import Decimal

import pytest

from src.ebay.models import (
    Amount,
    FeeBreakdown,
    ListingDetails,
    ListingFormat,
    Order,
    OrderLineItem,
    OrderStatus,
    SyncedItem,
    Transaction,
    TransactionType,
)


class TestAmount:
    """Tests for Amount model."""

    def test_amount_creation(self) -> None:
        """Test creating an Amount."""
        amount = Amount(value=Decimal("19.99"), currency="USD")
        assert amount.value == Decimal("19.99")
        assert amount.currency == "USD"

    def test_amount_float(self) -> None:
        """Test converting Amount to float."""
        amount = Amount(value=Decimal("19.99"), currency="USD")
        assert float(amount) == 19.99

    def test_amount_str(self) -> None:
        """Test Amount string representation."""
        amount = Amount(value=Decimal("19.99"), currency="USD")
        assert str(amount) == "USD 19.99"


class TestTransaction:
    """Tests for Transaction model."""

    def test_transaction_creation(self) -> None:
        """Test creating a Transaction."""
        tx = Transaction(
            transaction_id="TX123",
            transaction_type=TransactionType.SALE,
            transaction_date=datetime(2025, 1, 15, 10, 30),
            order_id="ORD456",
            amount=Amount(value=Decimal("50.00"), currency="USD"),
        )

        assert tx.transaction_id == "TX123"
        assert tx.transaction_type == TransactionType.SALE
        assert tx.order_id == "ORD456"
        assert float(tx.amount) == 50.00

    def test_transaction_with_fees(self) -> None:
        """Test Transaction with fee breakdown."""
        fees = [
            FeeBreakdown(
                fee_type="FINAL_VALUE_FEE",
                amount=Amount(value=Decimal("5.00"), currency="USD"),
            ),
            FeeBreakdown(
                fee_type="SHIPPING_LABEL",
                amount=Amount(value=Decimal("4.50"), currency="USD"),
            ),
        ]

        tx = Transaction(
            transaction_id="TX789",
            transaction_type=TransactionType.SALE,
            transaction_date=datetime(2025, 1, 15),
            amount=Amount(value=Decimal("45.00"), currency="USD"),
            fee_breakdown=fees,
        )

        assert len(tx.fee_breakdown) == 2
        assert tx.fee_breakdown[0].fee_type == "FINAL_VALUE_FEE"


class TestOrder:
    """Tests for Order model."""

    def test_order_creation(self) -> None:
        """Test creating an Order."""
        line_items = [
            OrderLineItem(
                line_item_id="LI001",
                item_id="ITEM123",
                title="Vintage Camera",
                quantity=1,
                unit_price=Amount(value=Decimal("75.00"), currency="USD"),
                total_price=Amount(value=Decimal("75.00"), currency="USD"),
            )
        ]

        order = Order(
            order_id="ORD001",
            creation_date=datetime(2025, 1, 15, 14, 0),
            order_status=OrderStatus.COMPLETED,
            line_items=line_items,
            subtotal=Amount(value=Decimal("75.00"), currency="USD"),
            shipping_cost=Amount(value=Decimal("8.99"), currency="USD"),
            total=Amount(value=Decimal("83.99"), currency="USD"),
        )

        assert order.order_id == "ORD001"
        assert len(order.line_items) == 1
        assert order.line_items[0].title == "Vintage Camera"
        assert float(order.total) == 83.99


class TestListingDetails:
    """Tests for ListingDetails model."""

    def test_listing_creation(self) -> None:
        """Test creating ListingDetails."""
        listing = ListingDetails(
            item_id="123456789",
            title="Vintage Camera - Excellent Condition",
            category_id="625",
            category_name="Cameras > Film Cameras",
            condition_name="Used",
            current_price=Amount(value=Decimal("75.00"), currency="USD"),
            view_count=150,
            watch_count=12,
            photo_count=8,
            free_shipping=True,
        )

        assert listing.item_id == "123456789"
        assert listing.view_count == 150
        assert listing.watch_count == 12
        assert listing.free_shipping is True

    def test_listing_default_values(self) -> None:
        """Test ListingDetails default values."""
        listing = ListingDetails(
            item_id="123",
            title="Test Item",
        )

        assert listing.view_count == 0
        assert listing.watch_count == 0
        assert listing.best_offer_enabled is False
        assert listing.listing_format == ListingFormat.FIXED_PRICE


class TestSyncedItem:
    """Tests for SyncedItem model."""

    def test_synced_item_creation(self) -> None:
        """Test creating a SyncedItem."""
        item = SyncedItem(
            item_id="ITEM001",
            title="Vintage Camera",
            category_name="Cameras",
            cogs=Decimal("25.00"),
            list_price=Decimal("75.00"),
            final_sale_price=Decimal("70.00"),
            status="Sold",
        )

        assert item.item_id == "ITEM001"
        assert item.cogs == Decimal("25.00")
        assert item.final_sale_price == Decimal("70.00")

    def test_synced_item_defaults(self) -> None:
        """Test SyncedItem default values."""
        item = SyncedItem(
            item_id="ITEM002",
            title="Test Item",
        )

        assert item.status == "Active"
        assert item.views == 0
        assert item.watchers == 0
        assert item.times_relisted == 0
        assert item.quantity_listed == 1
        assert item.best_offer_enabled is False

    def test_synced_item_quantity_tracking(self) -> None:
        """Test multi-quantity item tracking."""
        item = SyncedItem(
            item_id="ITEM003",
            title="Bulk Item",
            quantity_listed=10,
            quantity_sold=3,
            quantity_available=7,
        )

        assert item.quantity_listed == 10
        assert item.quantity_sold == 3
        assert item.quantity_available == 7

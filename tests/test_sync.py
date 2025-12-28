"""Tests for sync logic."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
from src.sheets.formulas import DashboardFormulas
from src.sheets.sync import SheetSync


class TestDashboardFormulas:
    """Tests for Dashboard formulas."""

    def test_inventory_headers(self) -> None:
        """Test inventory headers are complete."""
        headers = DashboardFormulas.get_inventory_headers()

        assert len(headers) == 54  # All columns defined
        assert headers[0] == "Item ID"
        assert headers[8] == "COGS"
        assert "Net Profit" in headers
        assert "ROI %" in headers

    def test_expenses_headers(self) -> None:
        """Test expenses headers."""
        headers = DashboardFormulas.get_expenses_headers()

        assert "Date" in headers
        assert "Category" in headers
        assert "Amount" in headers
        assert len(headers) == 9

    def test_row_formulas(self) -> None:
        """Test calculated column formulas."""
        formulas = DashboardFormulas.get_inventory_row_formulas(5)
        cols = DashboardFormulas.INV_COLS

        # Check formulas reference correct row
        assert "5" in formulas[cols["days_listed"]]
        assert "5" in formulas[cols["net_profit"]]
        assert "5" in formulas[cols["roi_percent"]]

    def test_expense_categories(self) -> None:
        """Test predefined expense categories."""
        categories = DashboardFormulas.get_expense_categories()

        assert "Supplies (Shipping)" in categories
        assert "Software/Subscriptions" in categories
        assert len(categories) >= 5


class TestSheetSync:
    """Tests for SheetSync class."""

    @pytest.fixture
    def mock_sheets_client(self) -> MagicMock:
        """Create a mock Google Sheets client."""
        client = MagicMock()
        client.get_all_values.return_value = [
            DashboardFormulas.get_inventory_headers(),  # Header row
            ["ITEM001", "Test Item 1", "", "", "", "", "", "", "25.00"],
            ["ITEM002", "Test Item 2", "", "", "", "", "", "", "30.00"],
        ]
        client.get_worksheet.return_value = MagicMock()
        return client

    def test_load_existing_items(self, mock_sheets_client: MagicMock) -> None:
        """Test loading existing item IDs."""
        sync = SheetSync(mock_sheets_client)
        sync.load_existing_items()

        assert "ITEM001" in sync._item_id_to_row
        assert "ITEM002" in sync._item_id_to_row
        assert sync._item_id_to_row["ITEM001"] == 2
        assert sync._item_id_to_row["ITEM002"] == 3

    def test_update_item_from_listing(self, mock_sheets_client: MagicMock) -> None:
        """Test creating SyncedItem from ListingDetails."""
        sync = SheetSync(mock_sheets_client)

        listing = ListingDetails(
            item_id="123456",
            title="Vintage Camera",
            category_id="625",
            category_name="Cameras > Film",
            condition_name="Used",
            current_price=Amount(value=Decimal("75.00"), currency="USD"),
            view_count=150,
            watch_count=12,
            photo_count=8,
            free_shipping=True,
            listing_format=ListingFormat.FIXED_PRICE,
            quantity=1,
            quantity_sold=0,
            quantity_available=1,
        )

        item = sync.update_item_from_listing(listing)

        assert item.item_id == "123456"
        assert item.title == "Vintage Camera"
        assert item.category_name == "Cameras > Film"
        assert item.views == 150
        assert item.watchers == 12
        assert item.free_shipping is True
        assert item.status == "Active"

    def test_update_item_sold_status(self, mock_sheets_client: MagicMock) -> None:
        """Test status is set correctly for sold items."""
        sync = SheetSync(mock_sheets_client)

        listing = ListingDetails(
            item_id="123456",
            title="Sold Item",
            quantity=1,
            quantity_sold=1,
            quantity_available=0,
        )

        item = sync.update_item_from_listing(listing)
        assert item.status == "Sold"

    def test_update_item_from_order(self, mock_sheets_client: MagicMock) -> None:
        """Test updating item with order data."""
        sync = SheetSync(mock_sheets_client)
        sync._item_id_to_row = {}  # No existing items

        order = Order(
            order_id="ORD001",
            creation_date=datetime(2025, 1, 15, 14, 0),
            order_status=OrderStatus.COMPLETED,
            line_items=[
                OrderLineItem(
                    line_item_id="LI001",
                    item_id="ITEM123",
                    title="Vintage Camera",
                    quantity=1,
                    unit_price=Amount(value=Decimal("75.00"), currency="USD"),
                    total_price=Amount(value=Decimal("75.00"), currency="USD"),
                )
            ],
            subtotal=Amount(value=Decimal("75.00"), currency="USD"),
            shipping_cost=Amount(value=Decimal("8.99"), currency="USD"),
            total=Amount(value=Decimal("83.99"), currency="USD"),
        )

        transactions = [
            Transaction(
                transaction_id="TX001",
                transaction_type=TransactionType.SALE,
                transaction_date=datetime(2025, 1, 15),
                order_id="ORD001",
                amount=Amount(value=Decimal("83.99"), currency="USD"),
                fee_breakdown=[
                    FeeBreakdown(
                        fee_type="FINAL_VALUE_FEE",
                        amount=Amount(value=Decimal("9.75"), currency="USD"),
                    ),
                    FeeBreakdown(
                        fee_type="FINAL_VALUE_FEE_FIXED_PER_ORDER",
                        amount=Amount(value=Decimal("0.30"), currency="USD"),
                    ),
                ],
            ),
            Transaction(
                transaction_id="TX002",
                transaction_type=TransactionType.SHIPPING_LABEL,
                transaction_date=datetime(2025, 1, 15),
                order_id="ORD001",
                amount=Amount(value=Decimal("-5.50"), currency="USD"),
            ),
        ]

        item = sync.update_item_from_order("ITEM123", order, transactions)

        assert item is not None
        assert item.item_id == "ITEM123"
        assert item.status == "Sold"
        assert item.final_sale_price == Decimal("75.00")
        assert item.shipping_charged == Decimal("8.99")
        assert item.actual_shipping_cost == Decimal("5.50")
        assert item.final_value_fee == Decimal("9.75")
        assert item.fixed_per_order_fee == Decimal("0.30")

    def test_item_not_in_order(self, mock_sheets_client: MagicMock) -> None:
        """Test handling item not found in order."""
        sync = SheetSync(mock_sheets_client)

        order = Order(
            order_id="ORD001",
            creation_date=datetime(2025, 1, 15),
            order_status=OrderStatus.COMPLETED,
            line_items=[],
            subtotal=Amount(value=Decimal("0"), currency="USD"),
            shipping_cost=Amount(value=Decimal("0"), currency="USD"),
            total=Amount(value=Decimal("0"), currency="USD"),
        )

        item = sync.update_item_from_order("NONEXISTENT", order, [])
        assert item is None


class TestSyncedItemConversion:
    """Tests for SyncedItem to row conversion."""

    @pytest.fixture
    def mock_sheets_client(self) -> MagicMock:
        """Create a mock Google Sheets client."""
        client = MagicMock()
        client.get_all_values.return_value = [
            DashboardFormulas.get_inventory_headers(),
        ]
        return client

    def test_item_to_row_basic(self, mock_sheets_client: MagicMock) -> None:
        """Test converting basic SyncedItem to row."""
        sync = SheetSync(mock_sheets_client)

        item = SyncedItem(
            item_id="ITEM001",
            title="Test Item",
            status="Active",
            list_price=Decimal("50.00"),
        )

        row = sync._item_to_row(item, 2)

        assert row[0] == "ITEM001"
        assert row[1] == "Test Item"
        assert row[13] == "Active"
        assert row[14] == 50.0

    def test_item_to_row_with_sale(self, mock_sheets_client: MagicMock) -> None:
        """Test converting sold SyncedItem to row."""
        sync = SheetSync(mock_sheets_client)

        item = SyncedItem(
            item_id="ITEM002",
            title="Sold Item",
            status="Sold",
            cogs=Decimal("25.00"),
            final_sale_price=Decimal("75.00"),
            shipping_charged=Decimal("8.99"),
            actual_shipping_cost=Decimal("5.50"),
            final_value_fee=Decimal("9.75"),
            fixed_per_order_fee=Decimal("0.30"),
        )

        row = sync._item_to_row(item, 3)

        assert row[8] == 25.0  # COGS
        assert row[19] == 75.0  # Final sale price
        assert row[20] == 8.99  # Shipping charged
        assert row[21] == 5.50  # Actual shipping
        assert row[23] == 9.75  # FVF
        assert row[24] == 0.30  # Fixed fee

    def test_item_to_row_formulas(self, mock_sheets_client: MagicMock) -> None:
        """Test that calculated columns contain formulas."""
        sync = SheetSync(mock_sheets_client)

        item = SyncedItem(
            item_id="ITEM003",
            title="Test",
            status="Sold",
        )

        row = sync._item_to_row(item, 5)

        # These columns should contain formulas
        days_listed_idx = 12
        shipping_pl_idx = 22
        total_fees_idx = 28
        net_profit_idx = 31
        roi_idx = 32

        assert "=" in str(row[days_listed_idx])
        assert "=" in str(row[shipping_pl_idx])
        assert "=" in str(row[total_fees_idx])
        assert "=" in str(row[net_profit_idx])
        assert "=" in str(row[roi_idx])

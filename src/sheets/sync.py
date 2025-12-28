"""Sync logic for eBay data to Google Sheets."""

from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

import pytz

from src.ebay.models import (
    ListingDetails,
    Order,
    SyncedItem,
    Transaction,
    TransactionType,
)
from src.sheets.client import GoogleSheetsClient
from src.sheets.formulas import DashboardFormulas
from src.utils.logging import get_logger

logger = get_logger("sheets.sync")


class SheetSync:
    """Handles synchronization of eBay data to Google Sheets.

    Implements upsert logic to update existing rows and append new ones,
    while preserving manually-entered data.
    """

    # Columns that should be preserved (not overwritten) during sync
    MANUAL_COLUMNS = [
        "acquisition_date",
        "acquisition_source",
        "cogs",
        "notes",
    ]

    # Column indices (0-indexed) for manual columns
    MANUAL_COLUMN_INDICES = {
        "acquisition_date": 6,
        "acquisition_source": 7,
        "cogs": 8,
        "notes": 53,
    }

    def __init__(
        self,
        sheets_client: GoogleSheetsClient,
        timezone: str = "America/New_York",
    ) -> None:
        """Initialize sync manager.

        Args:
            sheets_client: Google Sheets client
            timezone: Timezone for date display
        """
        self.sheets = sheets_client
        self.tz = pytz.timezone(timezone)
        self._item_id_to_row: dict[str, int] = {}
        self._headers_set = False

    def setup_sheets(self) -> None:
        """Set up all worksheets with headers and formulas."""
        logger.info("Setting up worksheets...")

        # Set up worksheets
        self.sheets.setup_worksheets()

        # Set headers
        self.sheets.set_headers("Inventory", DashboardFormulas.get_inventory_headers())
        self.sheets.set_headers("Expenses", DashboardFormulas.get_expenses_headers())
        self.sheets.set_headers("Metrics Log", DashboardFormulas.get_metrics_log_headers())

        # Set up Dashboard
        self._setup_dashboard()

        # Set up data validation for Expenses categories
        self._setup_expense_validation()

        self._headers_set = True
        logger.info("Worksheet setup complete")

    def _setup_dashboard(self) -> None:
        """Set up Dashboard worksheet with formulas."""
        dashboard = self.sheets.get_worksheet("Dashboard")

        # Get layout
        layout = DashboardFormulas.get_dashboard_layout()

        # Update dashboard
        dashboard.update("A1", layout, value_input_option="USER_ENTERED")

        # Format title
        dashboard.format("A1", {
            "textFormat": {"bold": True, "fontSize": 14},
        })

        # Format section headers
        for row in [3, 23, 29, 35]:
            dashboard.format(f"A{row}", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            })

        # Format currency columns
        dashboard.format("B9:B14", {"numberFormat": {"type": "CURRENCY"}})
        dashboard.format("B20", {"numberFormat": {"type": "CURRENCY"}})
        dashboard.format("B26:B27", {"numberFormat": {"type": "CURRENCY"}})
        dashboard.format("B32:B33", {"numberFormat": {"type": "CURRENCY"}})

        # Format percentage columns
        dashboard.format("B7", {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}})
        dashboard.format("B16:B17", {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}})

        logger.info("Dashboard set up with formulas")

    def _setup_expense_validation(self) -> None:
        """Set up data validation for expense categories."""
        # Note: gspread data validation requires specific API calls
        # For now, users will enter categories manually
        # This could be enhanced with dropdown validation
        pass

    def load_existing_items(self) -> None:
        """Load existing item IDs and their row numbers."""
        logger.info("Loading existing inventory items...")

        values = self.sheets.get_all_values("Inventory")

        self._item_id_to_row = {}
        for i, row in enumerate(values[1:], start=2):  # Skip header row
            if row and row[0]:  # Item ID is first column
                self._item_id_to_row[row[0]] = i

        logger.info(f"Loaded {len(self._item_id_to_row)} existing items")

    def sync_item(
        self,
        item: SyncedItem,
        preserve_manual: bool = True,
    ) -> bool:
        """Sync a single item to the Inventory sheet.

        Args:
            item: SyncedItem to sync
            preserve_manual: Whether to preserve manually-entered columns

        Returns:
            True if item was updated, False if added
        """
        existing_row = self._item_id_to_row.get(item.item_id)

        if existing_row:
            # Update existing row
            if preserve_manual:
                # Get current manual values
                current_values = self.sheets.get_worksheet("Inventory").row_values(existing_row)
                for col_name, col_idx in self.MANUAL_COLUMN_INDICES.items():
                    if col_idx < len(current_values) and current_values[col_idx]:
                        setattr(item, col_name, current_values[col_idx])

            row_values = self._item_to_row(item, existing_row)
            self.sheets.update_row("Inventory", existing_row, row_values)
            logger.debug(f"Updated item {item.item_id} at row {existing_row}")
            return True
        else:
            # Append new row
            next_row = len(self._item_id_to_row) + 2  # +1 for header, +1 for next
            row_values = self._item_to_row(item, next_row)
            new_row = self.sheets.append_row("Inventory", row_values)
            self._item_id_to_row[item.item_id] = new_row
            logger.debug(f"Added item {item.item_id} at row {new_row}")
            return False

    def _item_to_row(self, item: SyncedItem, row: int) -> list[Any]:
        """Convert a SyncedItem to a row of values.

        Args:
            item: SyncedItem to convert
            row: Row number for formulas

        Returns:
            List of cell values
        """
        formulas = DashboardFormulas.get_inventory_row_formulas(row)
        cols = DashboardFormulas.INV_COLS

        def fmt_date(dt: Optional[datetime]) -> str:
            if dt:
                return dt.astimezone(self.tz).strftime("%Y-%m-%d")
            return ""

        def fmt_decimal(d: Optional[Decimal]) -> Any:
            if d is not None:
                return float(d)
            return ""

        def fmt_bool(b: bool) -> str:
            return "TRUE" if b else "FALSE"

        # Build row in column order
        row_values = [
            item.item_id,
            item.title,
            item.category_id or "",
            item.category_name or "",
            item.condition or "",
            item.brand or "",
            item.acquisition_date or "",
            item.acquisition_source or "",
            fmt_decimal(item.cogs) if item.cogs else "",
            fmt_date(item.list_date),
            fmt_date(item.end_date),
            fmt_date(item.sale_date),
            formulas.get(cols["days_listed"], ""),  # Formula
            item.status,
            fmt_decimal(item.list_price),
            fmt_bool(item.best_offer_enabled),
            fmt_decimal(item.best_offer_auto_accept),
            fmt_decimal(item.best_offer_minimum),
            item.offers_received,
            fmt_decimal(item.final_sale_price),
            fmt_decimal(item.shipping_charged),
            fmt_decimal(item.actual_shipping_cost),
            formulas.get(cols["shipping_profit_loss"], ""),  # Formula
            fmt_decimal(item.final_value_fee),
            fmt_decimal(item.fixed_per_order_fee),
            fmt_decimal(item.promoted_listing_fee),
            fmt_decimal(item.international_fee),
            fmt_decimal(item.other_fees),
            formulas.get(cols["total_fees"], ""),  # Formula
            formulas.get(cols["gross_revenue"], ""),  # Formula
            formulas.get(cols["net_from_ebay"], ""),  # Formula
            formulas.get(cols["net_profit"], ""),  # Formula
            formulas.get(cols["roi_percent"], ""),  # Formula
            formulas.get(cols["profit_margin_percent"], ""),  # Formula
            item.views,
            item.watchers,
            formulas.get(cols["view_to_sale_rate"], ""),  # Formula
            item.questions_asked,
            item.description_length,
            item.photo_count,
            item.item_specifics_count,
            fmt_bool(item.free_shipping),
            item.shipping_service or "",
            fmt_bool(item.returns_accepted),
            item.return_period or "",
            item.listing_format,
            fmt_bool(item.promoted_listing),
            fmt_decimal(item.promoted_listing_rate),
            item.times_relisted,
            item.original_item_id or "",
            item.quantity_listed,
            item.quantity_sold,
            item.quantity_available,
            item.notes or "",
        ]

        return row_values

    def sync_items_batch(self, items: list[SyncedItem]) -> tuple[int, int]:
        """Sync multiple items efficiently.

        Args:
            items: List of SyncedItems to sync

        Returns:
            Tuple of (updated_count, added_count)
        """
        updated = 0
        added = 0

        for item in items:
            if self.sync_item(item):
                updated += 1
            else:
                added += 1

        logger.info(f"Synced {len(items)} items: {updated} updated, {added} added")
        return updated, added

    def update_item_from_order(
        self,
        item_id: str,
        order: Order,
        transactions: list[Transaction],
    ) -> Optional[SyncedItem]:
        """Update an item with order and transaction data.

        Args:
            item_id: eBay item ID
            order: Order containing the item
            transactions: Transactions for the order

        Returns:
            Updated SyncedItem or None if item not found
        """
        # Find the line item
        line_item = None
        for li in order.line_items:
            if li.item_id == item_id:
                line_item = li
                break

        if not line_item:
            logger.warning(f"Item {item_id} not found in order {order.order_id}")
            return None

        # Get existing item data
        existing_row = self._item_id_to_row.get(item_id)
        item = SyncedItem(item_id=item_id, title=line_item.title)

        if existing_row:
            # Load existing data
            current = self.sheets.get_worksheet("Inventory").row_values(existing_row)
            # Preserve certain fields
            if len(current) > 6 and current[6]:
                item.acquisition_date = current[6]
            if len(current) > 7 and current[7]:
                item.acquisition_source = current[7]
            if len(current) > 8 and current[8]:
                try:
                    item.cogs = Decimal(str(current[8]))
                except (ValueError, TypeError):
                    pass
            if len(current) > 53 and current[53]:
                item.notes = current[53]

        # Update from order
        item.status = "Sold"
        item.sale_date = order.creation_date
        item.final_sale_price = line_item.total_price.value
        item.shipping_charged = Decimal(float(order.shipping_cost)) if order.shipping_cost else None
        item.quantity_sold = line_item.quantity

        # Process transactions for fees
        for tx in transactions:
            if tx.transaction_type == TransactionType.SHIPPING_LABEL:
                item.actual_shipping_cost = abs(tx.amount.value)

            for fee in tx.fee_breakdown:
                fee_value = abs(fee.amount.value)
                if "FINAL_VALUE_FEE" in fee.fee_type and "FIXED" not in fee.fee_type:
                    item.final_value_fee = (item.final_value_fee or Decimal(0)) + fee_value
                elif "FIXED_PER_ORDER" in fee.fee_type:
                    item.fixed_per_order_fee = (item.fixed_per_order_fee or Decimal(0)) + fee_value
                elif "AD_FEE" in fee.fee_type:
                    item.promoted_listing_fee = (item.promoted_listing_fee or Decimal(0)) + fee_value
                elif "INTERNATIONAL" in fee.fee_type:
                    item.international_fee = (item.international_fee or Decimal(0)) + fee_value
                else:
                    item.other_fees = (item.other_fees or Decimal(0)) + fee_value

        return item

    def update_item_from_listing(
        self,
        listing: ListingDetails,
    ) -> SyncedItem:
        """Create or update an item from listing details.

        Args:
            listing: ListingDetails from eBay

        Returns:
            SyncedItem with listing data
        """
        item = SyncedItem(
            item_id=listing.item_id,
            title=listing.title,
            category_id=listing.category_id,
            category_name=listing.category_name,
            condition=listing.condition_name,
            list_date=listing.start_date,
            end_date=listing.end_date,
            list_price=listing.current_price.value if listing.current_price else None,
            best_offer_enabled=listing.best_offer_enabled,
            best_offer_auto_accept=listing.best_offer_auto_accept.value if listing.best_offer_auto_accept else None,
            best_offer_minimum=listing.best_offer_minimum.value if listing.best_offer_minimum else None,
            views=listing.view_count,
            watchers=listing.watch_count,
            questions_asked=listing.question_count,
            offers_received=listing.offer_count,
            description_length=listing.description_length,
            photo_count=listing.photo_count,
            item_specifics_count=listing.item_specifics_count,
            free_shipping=listing.free_shipping,
            shipping_service=listing.shipping_service,
            returns_accepted=listing.returns_accepted,
            return_period=listing.return_period,
            listing_format="Fixed Price" if listing.listing_format == "FIXED_PRICE" else "Auction",
            quantity_listed=listing.quantity,
            quantity_sold=listing.quantity_sold,
            quantity_available=listing.quantity_available,
        )

        # Determine status
        if listing.quantity_sold > 0 and listing.quantity_available == 0:
            item.status = "Sold"
        elif listing.quantity_available == 0:
            item.status = "Ended Unsold"
        else:
            item.status = "Active"

        return item

    def log_daily_metrics(self) -> None:
        """Log daily metrics to the Metrics Log worksheet."""
        today = datetime.now(self.tz).strftime("%Y-%m-%d")

        # Get current values from Inventory
        values = self.sheets.get_all_values("Inventory")

        active_count = 0
        total_value = Decimal(0)
        sold_today = 0
        revenue_today = Decimal(0)
        profit_today = Decimal(0)

        for row in values[1:]:  # Skip header
            if len(row) < 14:
                continue

            status = row[13] if len(row) > 13 else ""
            cogs_str = row[8] if len(row) > 8 else ""
            sale_date = row[11] if len(row) > 11 else ""
            gross_str = row[29] if len(row) > 29 else ""
            profit_str = row[31] if len(row) > 31 else ""

            if status == "Active":
                active_count += 1
                if cogs_str:
                    try:
                        total_value += Decimal(cogs_str)
                    except (ValueError, TypeError):
                        pass

            if sale_date == today:
                sold_today += 1
                if gross_str:
                    try:
                        revenue_today += Decimal(gross_str)
                    except (ValueError, TypeError):
                        pass
                if profit_str:
                    try:
                        profit_today += Decimal(profit_str)
                    except (ValueError, TypeError):
                        pass

        # Append to metrics log
        self.sheets.append_row(
            "Metrics Log",
            [
                today,
                active_count,
                float(total_value),
                sold_today,
                float(revenue_today),
                float(profit_today),
            ],
        )

        logger.info(f"Logged daily metrics for {today}")

    def get_sync_summary(self) -> dict[str, Any]:
        """Get a summary of the current sheet state.

        Returns:
            Dict with summary statistics
        """
        values = self.sheets.get_all_values("Inventory")

        total = len(values) - 1  # Exclude header
        active = 0
        sold = 0
        total_revenue = Decimal(0)
        total_profit = Decimal(0)
        total_fees = Decimal(0)

        for row in values[1:]:
            if len(row) < 14:
                continue

            status = row[13] if len(row) > 13 else ""
            if status == "Active":
                active += 1
            elif status == "Sold":
                sold += 1

                # Parse numeric values
                if len(row) > 29 and row[29]:
                    try:
                        total_revenue += Decimal(row[29])
                    except (ValueError, TypeError):
                        pass
                if len(row) > 28 and row[28]:
                    try:
                        total_fees += Decimal(row[28])
                    except (ValueError, TypeError):
                        pass
                if len(row) > 31 and row[31]:
                    try:
                        total_profit += Decimal(row[31])
                    except (ValueError, TypeError):
                        pass

        return {
            "total_items": total,
            "active_listings": active,
            "sold_items": sold,
            "sell_through_rate": (sold / total * 100) if total > 0 else 0,
            "total_revenue": float(total_revenue),
            "total_fees": float(total_fees),
            "total_profit": float(total_profit),
            "average_roi": (float(total_profit) / float(total_revenue) * 100)
            if total_revenue > 0
            else 0,
        }

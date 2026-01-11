"""Sync logic for eBay data to Google Sheets."""

import decimal
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

    # Column indices (0-indexed) for manual columns - updated for simplified structure
    MANUAL_COLUMN_INDICES = {
        "acquisition_date": 3,   # Column D
        "acquisition_source": 4, # Column E
        "cogs": 5,               # Column F
        "notes": 17,             # Column R
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
                        value = current_values[col_idx]
                        # Special handling for COGS - convert to Decimal
                        if col_name == "cogs":
                            try:
                                cogs_str = str(value).replace("$", "").replace(",", "").strip()
                                value = Decimal(cogs_str)
                            except (ValueError, TypeError, decimal.InvalidOperation):
                                value = None
                        if value is not None:
                            setattr(item, col_name, value)

            row_values = self._item_to_row(item, existing_row)
            self.sheets.update_row("Inventory", existing_row, row_values)
            logger.debug(f"Updated item {item.item_id} at row {existing_row}")
            return True
        else:
            # Append new row - get actual row count from sheet to avoid gaps/duplicates
            all_values = self.sheets.get_all_values("Inventory")
            next_row = len(all_values) + 1  # Next row after all existing data
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
            List of cell values (18 columns for simplified structure)
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

        # Combine all eBay fees into one field
        ebay_fees = Decimal(0)
        if item.final_value_fee:
            ebay_fees += item.final_value_fee
        if item.fixed_per_order_fee:
            ebay_fees += item.fixed_per_order_fee
        if item.international_fee:
            ebay_fees += item.international_fee
        if item.other_fees:
            ebay_fees += item.other_fees

        # Build row in column order (18 columns: A-R)
        row_values = [
            item.item_id,                                    # A: Item ID
            item.title,                                      # B: Title
            item.status,                                     # C: Status
            item.acquisition_date or "",                     # D: Acquisition Date
            item.acquisition_source or "",                   # E: Acquisition Source
            fmt_decimal(item.cogs) if item.cogs else "",     # F: COGS
            fmt_date(item.list_date),                        # G: List Date
            fmt_date(item.sale_date),                        # H: Sale Date
            formulas.get(cols["days_listed"], ""),           # I: Days Listed (formula)
            fmt_decimal(item.list_price),                    # J: List Price
            fmt_decimal(item.final_sale_price),              # K: Final Sale Price
            fmt_decimal(item.actual_shipping_cost),          # L: Shipping Cost
            fmt_decimal(ebay_fees) if ebay_fees else "",     # M: eBay Fees
            fmt_decimal(item.promoted_listing_fee),          # N: Ad Fees
            formulas.get(cols["total_costs"], ""),           # O: Total Costs (formula)
            formulas.get(cols["net_from_ebay"], ""),         # P: Net from eBay (formula)
            formulas.get(cols["net_profit"], ""),            # Q: Net Profit (formula)
            item.notes or "",                                # R: Notes
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

        # Column indices for simplified structure (manual columns)
        COL_ACQ_DATE = 3     # D - Acquisition Date
        COL_ACQ_SOURCE = 4   # E - Acquisition Source
        COL_COGS = 5         # F - COGS
        COL_NOTES = 17       # R - Notes

        if existing_row:
            # Load existing data
            current = self.sheets.get_worksheet("Inventory").row_values(existing_row)
            # Preserve certain fields
            if len(current) > COL_ACQ_DATE and current[COL_ACQ_DATE]:
                item.acquisition_date = current[COL_ACQ_DATE]
            if len(current) > COL_ACQ_SOURCE and current[COL_ACQ_SOURCE]:
                item.acquisition_source = current[COL_ACQ_SOURCE]
            if len(current) > COL_COGS and current[COL_COGS]:
                try:
                    # Strip currency symbols and commas from COGS value
                    cogs_str = str(current[COL_COGS]).replace("$", "").replace(",", "").strip()
                    item.cogs = Decimal(cogs_str)
                except (ValueError, TypeError, decimal.InvalidOperation):
                    pass
            if len(current) > COL_NOTES and current[COL_NOTES]:
                item.notes = current[COL_NOTES]

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

        # Check if we already logged metrics for today (prevent duplicates)
        metrics_values = self.sheets.get_all_values("Metrics Log")
        for row in metrics_values[1:]:  # Skip header
            if row and row[0] == today:
                logger.info(f"Metrics already logged for {today} - skipping")
                return

        # Get current values from Inventory
        values = self.sheets.get_all_values("Inventory")

        # Column indices for simplified structure
        COL_STATUS = 2       # C - Status
        COL_COGS = 5         # F - COGS
        COL_SALE_DATE = 7    # H - Sale Date
        COL_SALE_PRICE = 10  # K - Final Sale Price
        COL_NET_PROFIT = 16  # Q - Net Profit

        active_count = 0
        total_value = Decimal(0)
        sold_today = 0
        revenue_today = Decimal(0)
        profit_today = Decimal(0)

        for row in values[1:]:  # Skip header
            if len(row) < 3:
                continue

            status = row[COL_STATUS] if len(row) > COL_STATUS else ""
            cogs_str = row[COL_COGS] if len(row) > COL_COGS else ""
            sale_date = row[COL_SALE_DATE] if len(row) > COL_SALE_DATE else ""
            sale_price_str = row[COL_SALE_PRICE] if len(row) > COL_SALE_PRICE else ""
            profit_str = row[COL_NET_PROFIT] if len(row) > COL_NET_PROFIT else ""

            if status == "Active":
                active_count += 1
                if cogs_str:
                    try:
                        total_value += Decimal(str(cogs_str).replace("$", "").replace(",", ""))
                    except (ValueError, TypeError):
                        pass

            if sale_date == today:
                sold_today += 1
                if sale_price_str:
                    try:
                        revenue_today += Decimal(str(sale_price_str).replace("$", "").replace(",", ""))
                    except (ValueError, TypeError):
                        pass
                if profit_str:
                    try:
                        profit_today += Decimal(str(profit_str).replace("$", "").replace(",", ""))
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
        """Get a comprehensive summary of the current sheet state.

        Returns:
            Dict with detailed summary statistics including:
            - Item counts (total, sold, active)
            - Financial totals (revenue, fees, COGS, profit)
        """
        values = self.sheets.get_all_values("Inventory")

        # Column indices (0-indexed) based on simplified structure
        COL = {
            "status": 2,              # C - Status
            "cogs": 5,                # F - COGS
            "final_sale_price": 10,   # K - Final Sale Price
            "actual_shipping_cost": 11,  # L - Shipping Cost
            "ebay_fees": 12,          # M - eBay Fees
            "ad_fees": 13,            # N - Ad Fees
            "net_from_ebay": 15,      # P - Net from eBay (formula)
            "net_profit": 16,         # Q - Net Profit (formula)
        }

        def parse_decimal(row: list, col_idx: int) -> Optional[Decimal]:
            """Safely parse a decimal from a row."""
            if col_idx < len(row) and row[col_idx]:
                try:
                    return Decimal(str(row[col_idx]).replace("$", "").replace(",", ""))
                except (ValueError, TypeError, decimal.InvalidOperation):
                    pass
            return None

        # Initialize counters
        total = len(values) - 1  # Exclude header
        active = 0
        sold = 0
        refunded = 0

        # Financial totals
        total_final_sale_price = Decimal(0)
        total_shipping_cost = Decimal(0)
        total_cogs_sold = Decimal(0)
        total_cogs_active = Decimal(0)
        total_ebay_fees = Decimal(0)
        total_ad_fees = Decimal(0)
        total_net_from_ebay = Decimal(0)
        total_net_profit = Decimal(0)

        items_with_cogs = 0
        items_with_profit = 0

        for row in values[1:]:
            if len(row) < 3:
                continue

            status = row[COL["status"]] if COL["status"] < len(row) else ""

            if status == "Active":
                active += 1
                cogs = parse_decimal(row, COL["cogs"])
                if cogs:
                    total_cogs_active += cogs
            elif status == "Refunded":
                refunded += 1
            elif status == "Sold":
                sold += 1

                final_sale = parse_decimal(row, COL["final_sale_price"])
                shipping_cost = parse_decimal(row, COL["actual_shipping_cost"])
                cogs = parse_decimal(row, COL["cogs"])
                ebay_fees = parse_decimal(row, COL["ebay_fees"])
                ad_fees = parse_decimal(row, COL["ad_fees"])
                net_ebay = parse_decimal(row, COL["net_from_ebay"])
                net_profit = parse_decimal(row, COL["net_profit"])

                if final_sale:
                    total_final_sale_price += final_sale
                if shipping_cost:
                    total_shipping_cost += shipping_cost
                if cogs:
                    total_cogs_sold += cogs
                    items_with_cogs += 1
                if ebay_fees:
                    total_ebay_fees += ebay_fees
                if ad_fees:
                    total_ad_fees += ad_fees
                if net_ebay:
                    total_net_from_ebay += net_ebay
                if net_profit:
                    total_net_profit += net_profit
                    items_with_profit += 1

        # Get expenses from Expenses sheet
        total_expenses = Decimal(0)
        try:
            expense_values = self.sheets.get_all_values("Expenses")
            for row in expense_values[1:]:
                if len(row) > 5 and row[5]:
                    try:
                        total_expenses += Decimal(str(row[5]).replace("$", "").replace(",", ""))
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

        total_fees = total_ebay_fees + total_ad_fees

        return {
            # Item counts
            "total_items": total,
            "active_listings": active,
            "sold_items": sold,
            "refunded_items": refunded,
            "sell_through_rate": (sold / total * 100) if total > 0 else 0,

            # Revenue
            "total_final_sale_price": float(total_final_sale_price),

            # Costs
            "total_cogs_sold": float(total_cogs_sold),
            "total_cogs_active": float(total_cogs_active),
            "total_shipping_cost": float(total_shipping_cost),

            # Fees
            "total_fees": float(total_fees),
            "total_ebay_fees": float(total_ebay_fees),
            "total_ad_fees": float(total_ad_fees),

            # Other expenses
            "total_expenses": float(total_expenses),

            # Profit
            "total_net_from_ebay": float(total_net_from_ebay),
            "total_net_profit": float(total_net_profit),

            # Stats
            "items_with_cogs": items_with_cogs,
            "items_with_profit": items_with_profit,

            # Legacy fields for compatibility
            "total_revenue": float(total_final_sale_price),
            "total_profit": float(total_net_profit),
        }

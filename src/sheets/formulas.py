"""Google Sheets formula definitions for Dashboard and calculated columns."""

from typing import Any


class DashboardFormulas:
    """Formulas for the Dashboard worksheet.

    All formulas reference the Inventory and Expenses worksheets.
    Simplified to 18 essential columns for profitability tracking.
    """

    # Inventory column references (1-indexed for Sheets)
    # Simplified structure: 18 columns (A-R)
    INV_COLS = {
        "item_id": "A",           # Unique identifier
        "title": "B",             # Item name (manual or API)
        "status": "C",            # Active/Sold/Refunded
        "acquisition_date": "D",  # When purchased (manual)
        "acquisition_source": "E", # Where purchased (manual)
        "cogs": "F",              # Cost of goods sold (manual)
        "list_date": "G",         # When listed
        "sale_date": "H",         # When sold
        "days_listed": "I",       # Formula: days between list and sale
        "list_price": "J",        # Asking price
        "final_sale_price": "K",  # Actual sale price
        "actual_shipping_cost": "L",  # Shipping label cost
        "ebay_fees": "M",         # All marketplace fees combined
        "ad_fees": "N",           # Promoted listing fees
        "total_costs": "O",       # Formula: shipping + fees + ad
        "net_from_ebay": "P",     # Formula: sale - costs
        "net_profit": "Q",        # Formula: net - COGS
        "notes": "R",             # Manual notes
    }

    @classmethod
    def get_inventory_headers(cls) -> list[str]:
        """Get headers for the Inventory worksheet.

        Simplified to 18 essential columns for profitability tracking.
        """
        return [
            "Item ID",
            "Title",
            "Status",
            "Acquisition Date",
            "Acquisition Source",
            "COGS",
            "List Date",
            "Sale Date",
            "Days Listed",
            "List Price",
            "Final Sale Price",
            "Shipping Cost",
            "eBay Fees",
            "Ad Fees",
            "Total Costs",
            "Net from eBay",
            "Net Profit",
            "Notes",
        ]

    @classmethod
    def get_expenses_headers(cls) -> list[str]:
        """Get headers for the Expenses worksheet."""
        return [
            "Date",
            "Category",
            "Subcategory",
            "Vendor",
            "Description",
            "Amount",
            "Tax Deductible",
            "Receipt Link",
            "Notes",
        ]

    @classmethod
    def get_metrics_log_headers(cls) -> list[str]:
        """Get headers for the Metrics Log worksheet."""
        return [
            "Date",
            "Active Listings",
            "Total Value",
            "Items Sold (Day)",
            "Revenue (Day)",
            "Profit (Day)",
        ]

    @classmethod
    def get_inventory_row_formulas(cls, row: int) -> dict[str, str]:
        """Get formulas for calculated columns in an Inventory row.

        Args:
            row: Row number (1-indexed)

        Returns:
            Dict mapping column letter to formula
        """
        c = cls.INV_COLS
        return {
            # Days Listed = Sale Date - List Date (or today if still active)
            c["days_listed"]: f'=IF({c["sale_date"]}{row}<>"",{c["sale_date"]}{row}-{c["list_date"]}{row},IF({c["list_date"]}{row}<>"",TODAY()-{c["list_date"]}{row},""))',
            # Total Costs = Shipping + eBay Fees + Ad Fees
            c["total_costs"]: f'=IF(OR({c["actual_shipping_cost"]}{row}<>"",{c["ebay_fees"]}{row}<>"",{c["ad_fees"]}{row}<>""),SUM(IF({c["actual_shipping_cost"]}{row}<>"",{c["actual_shipping_cost"]}{row},0),IF({c["ebay_fees"]}{row}<>"",{c["ebay_fees"]}{row},0),IF({c["ad_fees"]}{row}<>"",{c["ad_fees"]}{row},0)),"")',
            # Net from eBay = Final Sale Price - Total Costs
            c["net_from_ebay"]: f'=IF({c["final_sale_price"]}{row}<>"",{c["final_sale_price"]}{row}-IF({c["total_costs"]}{row}<>"",{c["total_costs"]}{row},0),"")',
            # Net Profit = Net from eBay - COGS
            c["net_profit"]: f'=IF(AND({c["net_from_ebay"]}{row}<>"",{c["cogs"]}{row}<>""),{c["net_from_ebay"]}{row}-{c["cogs"]}{row},"")',
        }

    @classmethod
    def get_dashboard_layout(cls) -> list[list[Any]]:
        """Get the Dashboard layout with labels and formulas.

        Returns:
            2D list representing the Dashboard content
        """
        c = cls.INV_COLS
        inv = "Inventory"
        exp = "Expenses"

        # Helper for SUMIF/COUNTIF on status
        def sold_sum(col: str) -> str:
            return f'=SUMIF(\'{inv}\'!{c["status"]}:{c["status"]},"Sold",\'{inv}\'!{col}:{col})'

        def active_sum(col: str) -> str:
            return f'=SUMIF(\'{inv}\'!{c["status"]}:{c["status"]},"Active",\'{inv}\'!{col}:{col})'

        layout = [
            # Title
            ["EBAY RESELLER TRACKER DASHBOARD", "", "", ""],
            ["", "", "", ""],
            # Overall Performance
            ["=== OVERALL PERFORMANCE (ALL TIME) ===", "", "", ""],
            ["", "", "", ""],
            ["Total Items Listed", f'=COUNTA(\'{inv}\'!{c["item_id"]}:{c["item_id"]})-1', "", ""],
            ["Total Items Sold", f'=COUNTIF(\'{inv}\'!{c["status"]}:{c["status"]},"Sold")', "", ""],
            ["Sell-Through Rate (%)", f'=IF(B5>0,B6/B5*100,0)', "", ""],
            ["", "", "", ""],
            ["Total Revenue", sold_sum(c["final_sale_price"]), "", ""],
            ["Total COGS", sold_sum(c["cogs"]), "", ""],
            ["Total eBay Fees", sold_sum(c["ebay_fees"]), "", ""],
            ["Total Ad Fees", sold_sum(c["ad_fees"]), "", ""],
            ["Total Shipping Costs", sold_sum(c["actual_shipping_cost"]), "", ""],
            ["Total Misc Expenses", f'=SUM(\'{exp}\'!F:F)', "", ""],
            ["Total Net Profit", sold_sum(c["net_profit"]), "", ""],
            ["", "", "", ""],
            ["Average Days to Sell", f'=AVERAGEIF(\'{inv}\'!{c["status"]}:{c["status"]},"Sold",\'{inv}\'!{c["days_listed"]}:{c["days_listed"]})', "", ""],
            ["", "", "", ""],
            ["Total Inventory Value (COGS)", active_sum(c["cogs"]), "", ""],
            ["Active Listings", f'=COUNTIF(\'{inv}\'!{c["status"]}:{c["status"]},"Active")', "", ""],
            ["", "", "", ""],
            # This Month section
            ["=== THIS MONTH ===", "", "", ""],
            ["", "", "", ""],
            ["Items Sold (This Month)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(MONTH(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=MONTH(TODAY()))*(YEAR(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=YEAR(TODAY())))', "", ""],
            ["Revenue (This Month)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(MONTH(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=MONTH(TODAY()))*(YEAR(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=YEAR(TODAY()))*(\'{inv}\'!{c["final_sale_price"]}:{c["final_sale_price"]}))', "", ""],
            ["Profit (This Month)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(MONTH(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=MONTH(TODAY()))*(YEAR(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=YEAR(TODAY()))*(\'{inv}\'!{c["net_profit"]}:{c["net_profit"]}))', "", ""],
            ["", "", "", ""],
            # Last 30 Days section
            ["=== LAST 30 DAYS ===", "", "", ""],
            ["", "", "", ""],
            ["Items Sold (30 Days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]}>=TODAY()-30))', "", ""],
            ["Revenue (30 Days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]}>=TODAY()-30)*(\'{inv}\'!{c["final_sale_price"]}:{c["final_sale_price"]}))', "", ""],
            ["Profit (30 Days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]}>=TODAY()-30)*(\'{inv}\'!{c["net_profit"]}:{c["net_profit"]}))', "", ""],
            ["", "", "", ""],
            # Warning Flags
            ["=== WARNING FLAGS ===", "", "", ""],
            ["", "", "", ""],
            ["Stale Inventory (60+ days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Active")*(\'{inv}\'!{c["days_listed"]}:{c["days_listed"]}>=60))', "", ""],
            ["Items with Negative Profit", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(\'{inv}\'!{c["net_profit"]}:{c["net_profit"]}<0))', "", ""],
        ]

        return layout

    @classmethod
    def get_expense_categories(cls) -> list[str]:
        """Get predefined expense categories for dropdown."""
        return [
            "Supplies (Shipping)",
            "Supplies (Packaging)",
            "Software/Subscriptions",
            "Storage/Rent",
            "Equipment",
            "Inventory (Bulk Lot)",
            "Other",
        ]

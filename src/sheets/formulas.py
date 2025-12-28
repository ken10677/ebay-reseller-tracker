"""Google Sheets formula definitions for Dashboard and calculated columns."""

from typing import Any


class DashboardFormulas:
    """Formulas for the Dashboard worksheet.

    All formulas reference the Inventory and Expenses worksheets.
    """

    # Inventory column references (1-indexed for Sheets)
    INV_COLS = {
        "item_id": "A",
        "title": "B",
        "category_id": "C",
        "category_name": "D",
        "condition": "E",
        "brand": "F",
        "acquisition_date": "G",
        "acquisition_source": "H",
        "cogs": "I",
        "list_date": "J",
        "end_date": "K",
        "sale_date": "L",
        "days_listed": "M",
        "status": "N",
        "list_price": "O",
        "best_offer_enabled": "P",
        "best_offer_auto_accept": "Q",
        "best_offer_minimum": "R",
        "offers_received": "S",
        "final_sale_price": "T",
        "shipping_charged": "U",
        "actual_shipping_cost": "V",
        "shipping_profit_loss": "W",
        "final_value_fee": "X",
        "fixed_per_order_fee": "Y",
        "promoted_listing_fee": "Z",
        "international_fee": "AA",
        "other_fees": "AB",
        "total_fees": "AC",
        "gross_revenue": "AD",
        "net_from_ebay": "AE",
        "net_profit": "AF",
        "roi_percent": "AG",
        "profit_margin_percent": "AH",
        "views": "AI",
        "watchers": "AJ",
        "view_to_sale_rate": "AK",
        "questions_asked": "AL",
        "description_length": "AM",
        "photo_count": "AN",
        "item_specifics_count": "AO",
        "free_shipping": "AP",
        "shipping_service": "AQ",
        "returns_accepted": "AR",
        "return_period": "AS",
        "listing_format": "AT",
        "promoted_listing": "AU",
        "promoted_listing_rate": "AV",
        "times_relisted": "AW",
        "original_item_id": "AX",
        "quantity_listed": "AY",
        "quantity_sold": "AZ",
        "quantity_available": "BA",
        "notes": "BB",
    }

    @classmethod
    def get_inventory_headers(cls) -> list[str]:
        """Get headers for the Inventory worksheet."""
        return [
            "Item ID",
            "Title",
            "Category ID",
            "Category Name",
            "Condition",
            "Brand",
            "Acquisition Date",
            "Acquisition Source",
            "COGS",
            "List Date",
            "End Date",
            "Sale Date",
            "Days Listed",
            "Status",
            "List Price",
            "Best Offer Enabled",
            "Best Offer Auto-Accept",
            "Best Offer Minimum",
            "Offers Received",
            "Final Sale Price",
            "Shipping Charged",
            "Actual Shipping Cost",
            "Shipping Profit/Loss",
            "Final Value Fee",
            "Fixed Per-Order Fee",
            "Promoted Listing Fee",
            "International Fee",
            "Other Fees",
            "Total Fees",
            "Gross Revenue",
            "Net from eBay",
            "Net Profit",
            "ROI %",
            "Profit Margin %",
            "Views",
            "Watchers",
            "View-to-Sale Rate",
            "Questions Asked",
            "Description Length",
            "Photo Count",
            "Item Specifics Count",
            "Free Shipping",
            "Shipping Service",
            "Returns Accepted",
            "Return Period",
            "Listing Format",
            "Promoted Listing",
            "Promoted Listing %",
            "Times Relisted",
            "Original Item ID",
            "Quantity Listed",
            "Quantity Sold",
            "Quantity Available",
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
            # Days Listed = End/Sale Date - List Date
            c["days_listed"]: f'=IF(OR({c["end_date"]}{row}<>"",{c["sale_date"]}{row}<>""),IF({c["sale_date"]}{row}<>"",{c["sale_date"]}{row}-{c["list_date"]}{row},{c["end_date"]}{row}-{c["list_date"]}{row}),IF({c["list_date"]}{row}<>"",TODAY()-{c["list_date"]}{row},""))',
            # Shipping Profit/Loss = Shipping Charged - Actual Shipping Cost
            c["shipping_profit_loss"]: f'=IF(AND({c["shipping_charged"]}{row}<>"",{c["actual_shipping_cost"]}{row}<>""),{c["shipping_charged"]}{row}-{c["actual_shipping_cost"]}{row},"")',
            # Total Fees = Sum of all fee columns
            c["total_fees"]: f'=IF({c["final_value_fee"]}{row}<>"",SUM({c["final_value_fee"]}{row}:{c["other_fees"]}{row}),"")',
            # Gross Revenue = Final Sale Price + Shipping Charged
            c["gross_revenue"]: f'=IF({c["final_sale_price"]}{row}<>"",{c["final_sale_price"]}{row}+IF({c["shipping_charged"]}{row}<>"",{c["shipping_charged"]}{row},0),"")',
            # Net from eBay = Gross Revenue - Total Fees - Actual Shipping Cost
            c["net_from_ebay"]: f'=IF({c["gross_revenue"]}{row}<>"",{c["gross_revenue"]}{row}-IF({c["total_fees"]}{row}<>"",{c["total_fees"]}{row},0)-IF({c["actual_shipping_cost"]}{row}<>"",{c["actual_shipping_cost"]}{row},0),"")',
            # Net Profit = Net from eBay - COGS
            c["net_profit"]: f'=IF(AND({c["net_from_ebay"]}{row}<>"",{c["cogs"]}{row}<>""),{c["net_from_ebay"]}{row}-{c["cogs"]}{row},"")',
            # ROI % = (Net Profit / COGS) * 100
            c["roi_percent"]: f'=IF(AND({c["net_profit"]}{row}<>"",{c["cogs"]}{row}<>"",{c["cogs"]}{row}<>0),({c["net_profit"]}{row}/{c["cogs"]}{row})*100,"")',
            # Profit Margin % = (Net Profit / Gross Revenue) * 100
            c["profit_margin_percent"]: f'=IF(AND({c["net_profit"]}{row}<>"",{c["gross_revenue"]}{row}<>"",{c["gross_revenue"]}{row}<>0),({c["net_profit"]}{row}/{c["gross_revenue"]}{row})*100,"")',
            # View-to-Sale Rate = 1 / Views (if sold)
            c["view_to_sale_rate"]: f'=IF(AND({c["status"]}{row}="Sold",{c["views"]}{row}<>"",{c["views"]}{row}>0),1/{c["views"]}{row},"")',
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
            ["Total Gross Revenue", sold_sum(c["gross_revenue"]), "", ""],
            ["Total COGS", sold_sum(c["cogs"]), "", ""],
            ["Total eBay Fees", sold_sum(c["total_fees"]), "", ""],
            ["Total Shipping Costs (Net)", f'=-{sold_sum(c["shipping_profit_loss"]).replace("=", "")}', "", ""],
            ["Total Misc Expenses", f'=SUM(\'{exp}\'!F:F)', "", ""],
            ["Total Net Profit", f'=B9-B10-B11+B12-B13', "", ""],
            ["", "", "", ""],
            ["Average ROI (%)", f'=AVERAGEIF(\'{inv}\'!{c["status"]}:{c["status"]},"Sold",\'{inv}\'!{c["roi_percent"]}:{c["roi_percent"]})', "", ""],
            ["Average Profit Margin (%)", f'=AVERAGEIF(\'{inv}\'!{c["status"]}:{c["status"]},"Sold",\'{inv}\'!{c["profit_margin_percent"]}:{c["profit_margin_percent"]})', "", ""],
            ["Average Days to Sell", f'=AVERAGEIF(\'{inv}\'!{c["status"]}:{c["status"]},"Sold",\'{inv}\'!{c["days_listed"]}:{c["days_listed"]})', "", ""],
            ["", "", "", ""],
            ["Total Inventory Value (COGS)", active_sum(c["cogs"]), "", ""],
            ["Active Listings", f'=COUNTIF(\'{inv}\'!{c["status"]}:{c["status"]},"Active")', "", ""],
            ["", "", "", ""],
            # This Month section
            ["=== THIS MONTH ===", "", "", ""],
            ["", "", "", ""],
            ["Items Sold (This Month)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(MONTH(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=MONTH(TODAY()))*(YEAR(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=YEAR(TODAY())))', "", ""],
            ["Revenue (This Month)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(MONTH(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=MONTH(TODAY()))*(YEAR(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=YEAR(TODAY()))*(\'{inv}\'!{c["gross_revenue"]}:{c["gross_revenue"]}))', "", ""],
            ["Profit (This Month)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(MONTH(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=MONTH(TODAY()))*(YEAR(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]})=YEAR(TODAY()))*(\'{inv}\'!{c["net_profit"]}:{c["net_profit"]}))', "", ""],
            ["", "", "", ""],
            # Last 30 Days section
            ["=== LAST 30 DAYS ===", "", "", ""],
            ["", "", "", ""],
            ["Items Sold (30 Days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]}>=TODAY()-30))', "", ""],
            ["Revenue (30 Days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]}>=TODAY()-30)*(\'{inv}\'!{c["gross_revenue"]}:{c["gross_revenue"]}))', "", ""],
            ["Profit (30 Days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(\'{inv}\'!{c["sale_date"]}:{c["sale_date"]}>=TODAY()-30)*(\'{inv}\'!{c["net_profit"]}:{c["net_profit"]}))', "", ""],
            ["", "", "", ""],
            # Warning Flags
            ["=== WARNING FLAGS ===", "", "", ""],
            ["", "", "", ""],
            ["Stale Inventory (60+ days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Active")*(\'{inv}\'!{c["days_listed"]}:{c["days_listed"]}>=60))', "", ""],
            ["Items with Negative Profit", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Sold")*(\'{inv}\'!{c["net_profit"]}:{c["net_profit"]}<0))', "", ""],
            ["Items with 0 Views (14+ days)", f'=SUMPRODUCT((\'{inv}\'!{c["status"]}:{c["status"]}="Active")*(\'{inv}\'!{c["views"]}:{c["views"]}=0)*(\'{inv}\'!{c["days_listed"]}:{c["days_listed"]}>=14))', "", ""],
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

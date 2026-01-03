"""Main entry point for eBay Reseller Tracker sync."""

import argparse
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional

import pytz

from src.ebay.auth import EbayAuth
from src.ebay.browse import BrowseClient
from src.ebay.finances import FinancesClient
from src.ebay.fulfillment import FulfillmentClient
from src.ebay.inventory import InventoryClient
from src.ebay.trading import TradingClient
from src.ebay.models import SyncedItem, TransactionType
from src.sheets.client import GoogleSheetsClient
from src.sheets.sync import SheetSync
from src.utils.config import Config
from src.utils.email import EmailNotifier
from src.utils.logging import setup_logging, get_logger


def main() -> int:
    """Run the eBay to Google Sheets sync.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="eBay Reseller Tracker Sync")
    parser.add_argument(
        "--clear-inventory",
        action="store_true",
        help="Clear the Inventory sheet before syncing (removes duplicates)",
    )
    args = parser.parse_args()

    # Load configuration
    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Make sure you have set the required environment variables.")
        print("See .env.example for reference.")
        return 1

    # Set up logging
    setup_logging(config.log_level)
    logger = get_logger("main")

    logger.info("=" * 50)
    logger.info("eBay Reseller Tracker Sync Starting")
    logger.info("=" * 50)

    tz = pytz.timezone(config.timezone)
    now = datetime.now(tz)
    logger.info(f"Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # Initialize eBay clients
    logger.info("Initializing eBay API clients...")
    auth = EbayAuth(
        user_token=config.ebay_user_token,
        refresh_token=config.ebay_refresh_token,
        client_id=config.ebay_client_id,
        client_secret=config.ebay_client_secret,
        trading_token=config.ebay_trading_token,
    )

    # Check auth mode and validate/refresh token
    if auth.can_auto_refresh():
        logger.info("Auto-refresh enabled - getting fresh token...")
        if not auth.ensure_valid_token():
            logger.error("Failed to obtain valid eBay token!")
            logger.error("Check your EBAY_REFRESH_TOKEN, EBAY_CLIENT_ID, and EBAY_CLIENT_SECRET")
            return 1
    else:
        logger.info("Using provided user token (no auto-refresh)")
        if not auth.validate_token():
            logger.error("eBay token validation failed!")
            logger.error("Please refresh your eBay OAuth token, or set up auto-refresh.")
            return 1

    finances = FinancesClient(auth)
    fulfillment = FulfillmentClient(auth)
    inventory = InventoryClient(auth)
    trading = TradingClient(auth)
    browse = BrowseClient(auth)

    # Check Trading API availability
    trading_available = trading.is_available()
    if trading_available:
        logger.info("Trading API available - full metrics enabled")
    else:
        logger.info("Trading API not available - using limited metrics")

    # Initialize Google Sheets client
    logger.info("Initializing Google Sheets client...")
    if not config.has_google_credentials():
        logger.error("Google credentials not configured!")
        logger.error("Set GOOGLE_CREDENTIALS_PATH or GOOGLE_CREDENTIALS_JSON")
        return 1

    try:
        sheets = GoogleSheetsClient(
            credentials_path=config.google_credentials_path,
            credentials_json=config.google_credentials_json,
            sheet_id=config.google_sheet_id,
        )
    except Exception as e:
        logger.error(f"Failed to initialize Google Sheets: {e}")
        return 1

    # Initialize sync
    sync = SheetSync(sheets, config.timezone)

    # Set up sheets if needed
    try:
        sync.setup_sheets()
    except Exception as e:
        logger.error(f"Failed to set up worksheets: {e}")
        return 1

    # Clear inventory if requested (to remove duplicates)
    if args.clear_inventory:
        logger.warning("Clearing Inventory sheet to remove duplicates...")
        cleared = sheets.clear_worksheet_data("Inventory", keep_headers=True)
        logger.info(f"Cleared {cleared} rows from Inventory sheet")

    # Load existing items
    sync.load_existing_items()

    # Determine sync date range
    # For incremental sync, we could track last sync time
    # For now, sync from configured start date
    start_date = config.sync_start_date
    end_date = date.today()

    logger.info(f"Sync date range: {start_date} to {end_date}")

    # Track statistics
    stats = {
        "new_transactions": 0,
        "updated_listings": 0,
        "new_orders": 0,
        "items_synced": 0,
    }

    # Step 1: Get all orders in date range
    logger.info("Fetching orders...")
    orders_by_item: dict[str, list] = {}
    order_count = 0

    try:
        for order in fulfillment.get_orders(start_date, end_date):
            order_count += 1
            for line_item in order.line_items:
                item_id = line_item.item_id
                if item_id not in orders_by_item:
                    orders_by_item[item_id] = []
                orders_by_item[item_id].append(order)
    except Exception as e:
        logger.error(f"Failed to fetch orders: {e}")
        # Continue with what we have

    logger.info(f"Found {order_count} orders")
    stats["new_orders"] = order_count

    # Step 2: Get transactions for fees and sales data
    logger.info("Fetching transactions...")
    transactions_by_order: dict[str, list] = {}
    transactions_by_item: dict[str, list] = {}
    tx_count = 0
    sale_transactions = []

    # Also track NON_SALE_CHARGE transactions for promoted listing fees
    non_sale_charges = []
    # Track SHIPPING_LABEL transactions separately
    shipping_label_txs = []

    try:
        for tx in finances.get_transactions(start_date, end_date):
            tx_count += 1
            if tx.order_id:
                if tx.order_id not in transactions_by_order:
                    transactions_by_order[tx.order_id] = []
                transactions_by_order[tx.order_id].append(tx)
            if tx.item_id:
                if tx.item_id not in transactions_by_item:
                    transactions_by_item[tx.item_id] = []
                transactions_by_item[tx.item_id].append(tx)
            # Track SALE transactions for creating items
            if tx.transaction_type == TransactionType.SALE:
                sale_transactions.append(tx)
                logger.debug(f"SALE: order={tx.order_id}, item={tx.item_id}, amount=${tx.amount.value}")
            # Track NON_SALE_CHARGE for promoted listing fees
            elif tx.transaction_type == TransactionType.NON_SALE_CHARGE:
                non_sale_charges.append(tx)
                logger.debug(f"NON_SALE_CHARGE: order={tx.order_id}, item={tx.item_id}, amount=${tx.amount.value}, desc={tx.description}")
            # Track SHIPPING_LABEL transactions
            elif tx.transaction_type == TransactionType.SHIPPING_LABEL:
                shipping_label_txs.append(tx)
                logger.debug(f"SHIPPING_LABEL: order={tx.order_id}, item={tx.item_id}, amount=${tx.amount.value}")
    except Exception as e:
        logger.error(f"Failed to fetch transactions: {e}")

    logger.info(f"Found {tx_count} transactions ({len(sale_transactions)} sales, {len(non_sale_charges)} ad fees, {len(shipping_label_txs)} shipping labels)")
    stats["new_transactions"] = tx_count

    # Step 3: Get active listings
    logger.info("Fetching active listings...")
    items_to_sync: dict[str, SyncedItem] = {}

    try:
        # Get from Trading API if available (has more details)
        if trading_available:
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())
            listings = trading.get_seller_list(start_dt, end_dt)

            for listing in listings:
                item = sync.update_item_from_listing(listing)
                items_to_sync[item.item_id] = item
                stats["updated_listings"] += 1

        # Also get from Inventory API for any missing items
        for offer in inventory.get_offers():
            if offer.item_id and offer.item_id not in items_to_sync:
                # Create basic item from offer
                item = SyncedItem(
                    item_id=offer.item_id,
                    title=offer.sku,  # May need to get title elsewhere
                    list_price=offer.price.value,
                    listing_format="Fixed Price" if offer.format == "FIXED_PRICE" else "Auction",
                    status="Active" if offer.status == "ACTIVE" else "Ended",
                    quantity_listed=offer.quantity,
                    quantity_sold=offer.quantity_sold,
                    list_date=offer.listing_start_date,
                    end_date=offer.listing_end_date,
                )
                items_to_sync[item.item_id] = item

    except Exception as e:
        logger.error(f"Failed to fetch listings: {e}")

    # Step 4: Update items with order/transaction data
    # Handle multiple orders per item by aggregating data
    logger.info("Processing sold items...")
    for item_id, orders in orders_by_item.items():
        # Sort orders by date to get the most recent as primary
        sorted_orders = sorted(orders, key=lambda o: o.creation_date or datetime.min)

        for i, order in enumerate(sorted_orders):
            # Get transactions for this order
            order_transactions = transactions_by_order.get(order.order_id, [])

            # Update item with order data
            updated_item = sync.update_item_from_order(
                item_id, order, order_transactions
            )

            if updated_item:
                # Merge with existing item data if we have it
                if item_id in items_to_sync:
                    existing = items_to_sync[item_id]
                    # Preserve listing details, AGGREGATE sale details for multiple orders
                    existing.status = updated_item.status

                    # Use most recent sale date
                    if not existing.sale_date or (updated_item.sale_date and updated_item.sale_date > existing.sale_date):
                        existing.sale_date = updated_item.sale_date

                    # AGGREGATE financial values (sum them up for multiple sales)
                    if updated_item.final_sale_price:
                        existing.final_sale_price = (existing.final_sale_price or Decimal(0)) + updated_item.final_sale_price
                    if updated_item.shipping_charged:
                        existing.shipping_charged = (existing.shipping_charged or Decimal(0)) + updated_item.shipping_charged
                    if updated_item.actual_shipping_cost:
                        existing.actual_shipping_cost = (existing.actual_shipping_cost or Decimal(0)) + updated_item.actual_shipping_cost
                    if updated_item.final_value_fee:
                        existing.final_value_fee = (existing.final_value_fee or Decimal(0)) + updated_item.final_value_fee
                    if updated_item.fixed_per_order_fee:
                        existing.fixed_per_order_fee = (existing.fixed_per_order_fee or Decimal(0)) + updated_item.fixed_per_order_fee
                    if updated_item.promoted_listing_fee:
                        existing.promoted_listing_fee = (existing.promoted_listing_fee or Decimal(0)) + updated_item.promoted_listing_fee
                    if updated_item.international_fee:
                        existing.international_fee = (existing.international_fee or Decimal(0)) + updated_item.international_fee
                    if updated_item.other_fees:
                        existing.other_fees = (existing.other_fees or Decimal(0)) + updated_item.other_fees
                    # Aggregate quantity sold
                    existing.quantity_sold = (existing.quantity_sold or 0) + (updated_item.quantity_sold or 0)
                else:
                    items_to_sync[item_id] = updated_item

    # Step 4b: Create items from transactions if orders API failed
    # This ensures we capture sales even without the Fulfillment API
    # Initialize order_id -> item_id lookup for matching fees/shipping later
    order_to_item: dict[str, str] = {}

    if not orders_by_item and sale_transactions:
        logger.info(f"Creating items from {len(sale_transactions)} sale transactions...")

        # Track which transactions we've processed to avoid duplicates
        processed_tx_ids = set()

        for tx in sale_transactions:
            # Skip if we already processed this transaction
            if tx.transaction_id in processed_tx_ids:
                logger.debug(f"Skipping duplicate transaction {tx.transaction_id}")
                continue
            processed_tx_ids.add(tx.transaction_id)

            # Prefer item_id over order_id over transaction_id for consistency
            item_id = tx.item_id or tx.order_id or tx.transaction_id
            if not item_id or item_id in items_to_sync:
                continue

            # Get all transactions for this item to calculate fees
            item_txs = transactions_by_item.get(tx.item_id, []) if tx.item_id else [tx]

            # Calculate fees from related transactions
            final_value_fee = Decimal(0)
            fixed_fee = Decimal(0)
            ad_fee = Decimal(0)
            shipping_cost = Decimal(0)
            other_fees = Decimal(0)

            for related_tx in item_txs:
                for fee in related_tx.fee_breakdown:
                    fee_val = abs(fee.amount.value)
                    if "FINAL_VALUE" in fee.fee_type and "FIXED" not in fee.fee_type:
                        final_value_fee += fee_val
                    elif "FIXED" in fee.fee_type:
                        fixed_fee += fee_val
                    elif "AD_FEE" in fee.fee_type:
                        ad_fee += fee_val
                    else:
                        other_fees += fee_val

                if related_tx.transaction_type == TransactionType.SHIPPING_LABEL:
                    shipping_cost += abs(related_tx.amount.value)

            # Use title from transaction line items, fallback to description
            # Note: Finances API doesn't include item titles - manual entry may be needed
            item_title = tx.title or tx.description or "(Enter title manually)"

            item = SyncedItem(
                item_id=item_id,
                title=item_title,
                status="Sold",
                sale_date=tx.transaction_date,
                final_sale_price=tx.amount.value,
                final_value_fee=final_value_fee if final_value_fee else None,
                fixed_per_order_fee=fixed_fee if fixed_fee else None,
                promoted_listing_fee=ad_fee if ad_fee else None,
                actual_shipping_cost=shipping_cost if shipping_cost else None,
                other_fees=other_fees if other_fees else None,
            )
            items_to_sync[item_id] = item
            logger.debug(f"Created item key={item_id}, order_id={tx.order_id}")

            # Build order_id -> item_id lookup for matching fees later
            if tx.order_id:
                order_to_item[tx.order_id] = item_id

        logger.info(f"Created {len(items_to_sync)} items from transactions")

    # Step 4c: Apply promoted listing fees from NON_SALE_CHARGE transactions
    if non_sale_charges:
        logger.info(f"Processing {len(non_sale_charges)} promoted listing fee transactions...")
        ad_fees_applied = 0

        # Also add from orders_by_item if we have Fulfillment API data
        for item_id, orders in orders_by_item.items():
            for order in orders:
                if order.order_id not in order_to_item:
                    order_to_item[order.order_id] = item_id

        logger.debug(f"Order-to-item lookup has {len(order_to_item)} mappings")

        for tx in non_sale_charges:
            # NON_SALE_CHARGE for ad fees should have an item_id or order_id
            item_id = tx.item_id
            order_id = tx.order_id

            # The amount on NON_SALE_CHARGE is the fee (negative value)
            ad_fee_amount = abs(tx.amount.value)

            # Try to find the item to apply this fee to
            target_item = None

            # First try direct item_id match
            if item_id and item_id in items_to_sync:
                target_item = items_to_sync[item_id]
            # Use our order_id -> item_id lookup
            elif order_id and order_id in order_to_item:
                lookup_item_id = order_to_item[order_id]
                if lookup_item_id in items_to_sync:
                    target_item = items_to_sync[lookup_item_id]
            # Try to find by order_id (items may be keyed by order_id as fallback)
            elif order_id and order_id in items_to_sync:
                target_item = items_to_sync[order_id]
            # Try to find by order_id in sale transactions
            elif order_id:
                # Look for a SALE transaction with this order_id
                for sale_tx in sale_transactions:
                    if sale_tx.order_id == order_id:
                        # The item may be keyed by item_id, order_id, or transaction_id
                        possible_keys = [sale_tx.item_id, sale_tx.order_id, sale_tx.transaction_id]
                        for key in possible_keys:
                            if key and key in items_to_sync:
                                target_item = items_to_sync[key]
                                break
                        if target_item:
                            break

            if target_item:
                # Add to existing promoted_listing_fee or set it
                current_fee = target_item.promoted_listing_fee or Decimal(0)
                target_item.promoted_listing_fee = current_fee + ad_fee_amount
                target_item.promoted_listing = True
                ad_fees_applied += 1
                logger.debug(f"Applied ${ad_fee_amount} ad fee to item {target_item.item_id}")
            else:
                logger.debug(f"Could not match ad fee for order {order_id} to any item")

        logger.info(f"Applied {ad_fees_applied} promoted listing fees to items")

    # Step 4d: Apply SHIPPING_LABEL transactions to items
    if shipping_label_txs:
        logger.info(f"Processing {len(shipping_label_txs)} shipping label transactions...")
        shipping_applied = 0

        for tx in shipping_label_txs:
            order_id = tx.order_id
            item_id = tx.item_id
            shipping_cost = abs(tx.amount.value)

            # Try to find the item to apply shipping cost to
            target_item = None

            # First try direct item_id match
            if item_id and item_id in items_to_sync:
                target_item = items_to_sync[item_id]
            # Use order_to_item lookup
            elif order_id and order_id in order_to_item:
                lookup_item_id = order_to_item[order_id]
                if lookup_item_id in items_to_sync:
                    target_item = items_to_sync[lookup_item_id]
            # Try order_id as key
            elif order_id and order_id in items_to_sync:
                target_item = items_to_sync[order_id]
            # Search sale transactions for matching order
            elif order_id:
                for sale_tx in sale_transactions:
                    if sale_tx.order_id == order_id:
                        possible_keys = [sale_tx.item_id, sale_tx.order_id, sale_tx.transaction_id]
                        for key in possible_keys:
                            if key and key in items_to_sync:
                                target_item = items_to_sync[key]
                                break
                        if target_item:
                            break

            if target_item:
                current_cost = target_item.actual_shipping_cost or Decimal(0)
                target_item.actual_shipping_cost = current_cost + shipping_cost
                shipping_applied += 1
                logger.debug(f"Applied ${shipping_cost} shipping cost to item {target_item.item_id}")
            else:
                logger.debug(f"Could not match shipping label for order {order_id} to any item")

        logger.info(f"Applied {shipping_applied} shipping label costs to items")

    # Step 4e: Enrich items with titles from Browse API (public data)
    # This helps when we don't have Fulfillment API access for order details
    logger.info("Enriching items with titles from Browse API...")
    try:
        enriched_count = browse.enrich_items_with_titles(items_to_sync)
        if enriched_count:
            logger.info(f"Enriched {enriched_count} items with titles from public data")
    except Exception as e:
        logger.warning(f"Failed to enrich titles from Browse API: {e}")

    # Step 5: Sync to Google Sheets
    logger.info("Syncing to Google Sheets...")
    items_list = list(items_to_sync.values())
    updated, added = sync.sync_items_batch(items_list)
    stats["items_synced"] = updated + added

    # Step 6: Log daily metrics
    sync.log_daily_metrics()

    # Get summary
    summary = sync.get_sync_summary()

    # Print summary
    logger.info("")
    logger.info("=" * 50)
    logger.info("eBay Reseller Tracker Sync Complete")
    logger.info("=" * 50)
    logger.info(f"Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"Date Range: {start_date} to {end_date}")
    logger.info("")
    logger.info(f"New Transactions: {stats['new_transactions']}")
    logger.info(f"Updated Listings: {stats['updated_listings']}")
    logger.info(f"New Orders: {stats['new_orders']}")
    logger.info(f"Items Synced: {stats['items_synced']}")
    logger.info("")
    logger.info("Quick Summary:")
    logger.info(f"  Total Sold: {summary['sold_items']} items")
    logger.info(f"  Sell-Through: {summary['sell_through_rate']:.1f}%")
    logger.info(f"  Total Revenue: ${summary['total_revenue']:.2f}")
    logger.info(f"  Total Fees: ${summary['total_fees']:.2f}")
    logger.info(f"  Total Profit: ${summary['total_profit']:.2f}")
    logger.info("")
    logger.info(f"Active Listings: {summary['active_listings']}")
    logger.info("")

    # Token status
    token_status = auth.get_token_status_message()
    if "expires" in token_status.lower() or "invalid" in token_status.lower():
        logger.warning(token_status)
    else:
        logger.info(token_status)

    logger.info("")
    logger.info(f"Sheet updated: {sheets.get_sheet_url()}")
    logger.info("=" * 50)

    # Step 7: Send email notification
    if config.has_email_configured():
        logger.info("Sending email notification...")
        email = EmailNotifier(
            smtp_host=config.email_smtp_host,
            smtp_port=config.email_smtp_port,
            sender=config.email_sender,
            password=config.email_password,
            recipient=config.email_recipient,
        )
        if email.send_sync_summary(stats, summary, sheets.get_sheet_url()):
            logger.info("Email notification sent successfully")
        else:
            logger.warning("Failed to send email notification")
    else:
        logger.info("Email notifications not configured - skipping")

    return 0


if __name__ == "__main__":
    sys.exit(main())

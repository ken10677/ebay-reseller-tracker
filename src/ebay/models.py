"""Pydantic models for eBay API data structures."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    """Types of eBay transactions."""

    SALE = "SALE"
    REFUND = "REFUND"
    CREDIT = "CREDIT"
    DISPUTE = "DISPUTE"
    SHIPPING_LABEL = "SHIPPING_LABEL"
    TRANSFER = "TRANSFER"
    NON_SALE_CHARGE = "NON_SALE_CHARGE"
    OTHER = "OTHER"


class FeeType(str, Enum):
    """Types of eBay fees."""

    FINAL_VALUE_FEE = "FINAL_VALUE_FEE"
    FINAL_VALUE_FEE_FIXED_PER_ORDER = "FINAL_VALUE_FEE_FIXED_PER_ORDER"
    SHIPPING_LABEL = "SHIPPING_LABEL"
    AD_FEE = "AD_FEE"
    INTERNATIONAL_FEE = "INTERNATIONAL_FEE"
    REGULATORY_OPERATING_FEE = "REGULATORY_OPERATING_FEE"
    OTHER = "OTHER"


class OrderStatus(str, Enum):
    """Order fulfillment status."""

    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    INACTIVE = "INACTIVE"


class ListingStatus(str, Enum):
    """Listing status."""

    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    SOLD = "SOLD"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class ListingFormat(str, Enum):
    """Listing format/type."""

    FIXED_PRICE = "FIXED_PRICE"
    AUCTION = "AUCTION"


class Amount(BaseModel):
    """Monetary amount with currency."""

    value: Decimal = Field(..., description="Amount value")
    currency: str = Field("USD", description="Currency code")

    def __float__(self) -> float:
        return float(self.value)

    def __str__(self) -> str:
        return f"{self.currency} {self.value:.2f}"


class FeeBreakdown(BaseModel):
    """Breakdown of a single fee."""

    fee_type: str = Field(..., description="Type of fee")
    amount: Amount = Field(..., description="Fee amount")
    description: Optional[str] = Field(None, description="Fee description")


class Transaction(BaseModel):
    """eBay financial transaction.

    Note on amount fields for SALE transactions:
    - amount: Net to seller AFTER eBay fees are deducted
    - fee_basis_amount: Gross sales (item + shipping) BEFORE fees - this is what fees are calculated on
    - The difference (fee_basis - amount) equals total eBay fees
    """

    transaction_id: str = Field(..., description="Unique transaction ID")
    transaction_type: TransactionType = Field(..., description="Type of transaction")
    transaction_date: datetime = Field(..., description="When transaction occurred")
    order_id: Optional[str] = Field(None, description="Associated order ID")
    item_id: Optional[str] = Field(None, description="Associated item/listing ID")
    title: Optional[str] = Field(None, description="Item title from line items")
    amount: Amount = Field(..., description="Net amount to seller (after fees deducted)")
    fee_basis_amount: Optional[Amount] = Field(None, description="Gross amount (item + shipping) before fees")
    item_amount: Optional[Amount] = Field(None, description="Item price (without shipping)")
    shipping_amount: Optional[Amount] = Field(None, description="Shipping charged to buyer")
    fee_amount: Optional[Amount] = Field(None, description="Total fees for this transaction")
    fee_breakdown: list[FeeBreakdown] = Field(
        default_factory=list, description="Detailed fee breakdown"
    )
    payout_id: Optional[str] = Field(None, description="Associated payout ID")
    description: Optional[str] = Field(None, description="Transaction description")

    class Config:
        use_enum_values = True


class Payout(BaseModel):
    """eBay payout to bank account."""

    payout_id: str = Field(..., description="Unique payout ID")
    payout_date: datetime = Field(..., description="When payout was initiated")
    amount: Amount = Field(..., description="Payout amount")
    status: str = Field(..., description="Payout status")
    transaction_count: int = Field(0, description="Number of transactions in payout")


class ShippingAddress(BaseModel):
    """Shipping address (zone info only, no PII)."""

    state_or_province: Optional[str] = Field(None, description="State/province code")
    postal_code: Optional[str] = Field(None, description="Postal code (for zone calculation)")
    country: str = Field("US", description="Country code")


class OrderLineItem(BaseModel):
    """Individual item within an order."""

    line_item_id: str = Field(..., description="Unique line item ID")
    item_id: str = Field(..., description="eBay item/listing ID")
    title: str = Field(..., description="Item title")
    sku: Optional[str] = Field(None, description="Seller's SKU")
    quantity: int = Field(1, description="Quantity purchased")
    unit_price: Amount = Field(..., description="Price per unit")
    total_price: Amount = Field(..., description="Total price for line item")
    shipping_cost: Optional[Amount] = Field(None, description="Shipping cost for this item")


class Order(BaseModel):
    """eBay order containing one or more items."""

    order_id: str = Field(..., description="Unique order ID")
    creation_date: datetime = Field(..., description="When order was placed")
    order_status: OrderStatus = Field(..., description="Current order status")
    line_items: list[OrderLineItem] = Field(
        default_factory=list, description="Items in the order"
    )
    subtotal: Amount = Field(..., description="Item subtotal before shipping")
    shipping_cost: Amount = Field(..., description="Total shipping charged to buyer")
    total: Amount = Field(..., description="Order total")
    shipping_address: Optional[ShippingAddress] = Field(
        None, description="Shipping destination (zone info only)"
    )
    buyer_username: Optional[str] = Field(None, description="Buyer's username")
    paid_date: Optional[datetime] = Field(None, description="When payment was received")
    shipped_date: Optional[datetime] = Field(None, description="When item was shipped")

    class Config:
        use_enum_values = True


class InventoryItem(BaseModel):
    """Item in seller's inventory."""

    sku: str = Field(..., description="Seller's SKU (we use item ID)")
    condition: Optional[str] = Field(None, description="Item condition")
    condition_description: Optional[str] = Field(None, description="Detailed condition notes")
    availability: Optional[int] = Field(None, description="Available quantity")
    product_title: Optional[str] = Field(None, description="Product title")
    product_description: Optional[str] = Field(None, description="Product description")
    aspects: dict[str, list[str]] = Field(
        default_factory=dict, description="Item specifics/aspects"
    )


class Offer(BaseModel):
    """Active listing/offer details."""

    offer_id: str = Field(..., description="Unique offer ID")
    sku: str = Field(..., description="Associated inventory item SKU")
    item_id: Optional[str] = Field(None, description="eBay listing ID")
    marketplace_id: str = Field("EBAY_US", description="Marketplace")
    format: ListingFormat = Field(ListingFormat.FIXED_PRICE, description="Listing format")
    status: ListingStatus = Field(..., description="Listing status")
    price: Amount = Field(..., description="Listed price")
    quantity: int = Field(1, description="Quantity available")
    quantity_sold: int = Field(0, description="Quantity sold")
    category_id: Optional[str] = Field(None, description="eBay category ID")
    listing_start_date: Optional[datetime] = Field(None, description="When listing started")
    listing_end_date: Optional[datetime] = Field(None, description="When listing ends/ended")

    # Listing policies
    shipping_policy_id: Optional[str] = Field(None)
    return_policy_id: Optional[str] = Field(None)
    payment_policy_id: Optional[str] = Field(None)

    # Promoted listing
    promoted_listing: bool = Field(False, description="Is this a promoted listing?")
    promoted_listing_rate: Optional[Decimal] = Field(
        None, description="Promoted listing ad rate %"
    )

    class Config:
        use_enum_values = True


class ListingDetails(BaseModel):
    """Extended listing details from Trading API."""

    item_id: str = Field(..., description="eBay item ID")
    title: str = Field(..., description="Listing title")
    category_id: Optional[str] = Field(None, description="Primary category ID")
    category_name: Optional[str] = Field(None, description="Primary category path")
    condition_id: Optional[str] = Field(None, description="Condition ID")
    condition_name: Optional[str] = Field(None, description="Condition display name")

    # Pricing
    current_price: Optional[Amount] = Field(None, description="Current/buy-it-now price")
    start_price: Optional[Amount] = Field(None, description="Starting price (auctions)")
    best_offer_enabled: bool = Field(False, description="Best offer enabled?")
    best_offer_auto_accept: Optional[Amount] = Field(None, description="Auto-accept threshold")
    best_offer_minimum: Optional[Amount] = Field(None, description="Auto-decline threshold")

    # Listing dates
    start_date: Optional[datetime] = Field(None, description="Listing start date")
    end_date: Optional[datetime] = Field(None, description="Listing end date")

    # Performance metrics (from Trading API)
    view_count: int = Field(0, description="Total views/hits")
    watch_count: int = Field(0, description="Current watchers")
    question_count: int = Field(0, description="Questions asked")
    offer_count: int = Field(0, description="Best offers received")

    # Listing details
    description_length: int = Field(0, description="Description character count")
    photo_count: int = Field(0, description="Number of photos")
    item_specifics_count: int = Field(0, description="Number of item specifics filled")

    # Shipping
    free_shipping: bool = Field(False, description="Free shipping offered?")
    shipping_service: Optional[str] = Field(None, description="Primary shipping service")

    # Returns
    returns_accepted: bool = Field(False, description="Returns accepted?")
    return_period: Optional[str] = Field(None, description="Return period")

    # Other
    listing_format: ListingFormat = Field(
        ListingFormat.FIXED_PRICE, description="Listing format"
    )
    quantity: int = Field(1, description="Total quantity listed")
    quantity_sold: int = Field(0, description="Quantity sold")
    quantity_available: int = Field(1, description="Quantity remaining")

    class Config:
        use_enum_values = True


class SyncedItem(BaseModel):
    """Consolidated item data for syncing to Google Sheets."""

    # Identifiers
    item_id: str = Field(..., description="eBay Item ID (unique identifier)")
    title: str = Field(..., description="Listing title")

    # Category
    category_id: Optional[str] = None
    category_name: Optional[str] = None

    # Condition
    condition: Optional[str] = None
    brand: Optional[str] = None

    # Manual input fields (preserved during sync)
    acquisition_date: Optional[str] = None
    acquisition_source: Optional[str] = None
    cogs: Optional[Decimal] = None

    # Listing dates
    list_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sale_date: Optional[datetime] = None
    days_listed: Optional[int] = None

    # Status
    status: str = "Active"  # Active, Sold, Ended Unsold, Relisted

    # Pricing
    list_price: Optional[Decimal] = None
    best_offer_enabled: bool = False
    best_offer_auto_accept: Optional[Decimal] = None
    best_offer_minimum: Optional[Decimal] = None
    offers_received: int = 0
    final_sale_price: Optional[Decimal] = None

    # Shipping
    shipping_charged: Optional[Decimal] = None
    actual_shipping_cost: Optional[Decimal] = None
    shipping_profit_loss: Optional[Decimal] = None

    # Fees
    final_value_fee: Optional[Decimal] = None
    fixed_per_order_fee: Optional[Decimal] = None
    promoted_listing_fee: Optional[Decimal] = None
    international_fee: Optional[Decimal] = None
    other_fees: Optional[Decimal] = None
    total_fees: Optional[Decimal] = None

    # Profit calculations
    gross_revenue: Optional[Decimal] = None
    net_from_ebay: Optional[Decimal] = None
    net_profit: Optional[Decimal] = None
    roi_percent: Optional[Decimal] = None
    profit_margin_percent: Optional[Decimal] = None

    # Performance metrics
    views: int = 0
    watchers: int = 0
    view_to_sale_rate: Optional[Decimal] = None
    questions_asked: int = 0

    # Listing quality
    description_length: int = 0
    photo_count: int = 0
    item_specifics_count: int = 0

    # Shipping settings
    free_shipping: bool = False
    shipping_service: Optional[str] = None

    # Return settings
    returns_accepted: bool = False
    return_period: Optional[str] = None

    # Listing settings
    listing_format: str = "Fixed Price"
    promoted_listing: bool = False
    promoted_listing_rate: Optional[Decimal] = None

    # Relisting tracking
    times_relisted: int = 0
    original_item_id: Optional[str] = None

    # Multi-quantity support
    quantity_listed: int = 1
    quantity_sold: int = 0
    quantity_available: int = 1

    # Notes (preserved during sync)
    notes: Optional[str] = None

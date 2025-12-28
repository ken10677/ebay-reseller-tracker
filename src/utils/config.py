"""Configuration management using environment variables."""

import os
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Application configuration loaded from environment variables."""

    # eBay API
    ebay_user_token: str = Field(..., description="eBay OAuth 2.0 User Token")
    ebay_trading_token: Optional[str] = Field(
        None, description="eBay Trading API token (optional, for legacy API)"
    )

    # Google Sheets
    google_credentials_path: Optional[str] = Field(
        None, description="Path to Google Cloud Service Account credentials JSON"
    )
    google_credentials_json: Optional[str] = Field(
        None, description="Google credentials JSON content (for GitHub Actions)"
    )
    google_sheet_id: Optional[str] = Field(None, description="Google Sheet ID")
    create_new_sheet: bool = Field(False, description="Create new sheet if ID not provided")

    # Logging
    log_level: str = Field("INFO", description="Logging level")

    # Timezone
    timezone: str = Field("America/New_York", description="Timezone for date display")

    # Sync settings
    sync_start_date: date = Field(
        default_factory=lambda: date(2025, 11, 1),
        description="Start date for historical data pull",
    )

    # eBay API Base URLs
    ebay_finances_base_url: str = "https://apiz.ebay.com/sell/finances/v1"
    ebay_fulfillment_base_url: str = "https://apiz.ebay.com/sell/fulfillment/v1"
    ebay_inventory_base_url: str = "https://apiz.ebay.com/sell/inventory/v1"
    ebay_analytics_base_url: str = "https://apiz.ebay.com/sell/analytics/v1"
    ebay_trading_base_url: str = "https://api.ebay.com/ws/api.dll"

    @field_validator("sync_start_date", mode="before")
    @classmethod
    def parse_date(cls, v: str | date) -> date:
        """Parse date from string if needed."""
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return date.fromisoformat(v)
        raise ValueError(f"Invalid date format: {v}")

    @classmethod
    def from_env(cls, env_path: Optional[Path] = None) -> "Config":
        """Load configuration from environment variables.

        Args:
            env_path: Optional path to .env file. If not provided, looks in current directory.

        Returns:
            Config instance with values from environment.

        Raises:
            ValueError: If required environment variables are missing.
        """
        # Load .env file if it exists
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()

        # Get required values
        ebay_token = os.getenv("EBAY_USER_TOKEN")
        if not ebay_token:
            raise ValueError("EBAY_USER_TOKEN environment variable is required")

        # Get optional values with defaults
        return cls(
            ebay_user_token=ebay_token,
            ebay_trading_token=os.getenv("EBAY_TRADING_TOKEN"),
            google_credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH"),
            google_credentials_json=os.getenv("GOOGLE_CREDENTIALS_JSON"),
            google_sheet_id=os.getenv("GOOGLE_SHEET_ID"),
            create_new_sheet=os.getenv("CREATE_NEW_SHEET", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            timezone=os.getenv("TIMEZONE", "America/New_York"),
            sync_start_date=os.getenv("SYNC_START_DATE", "2025-11-01"),
        )

    def has_google_credentials(self) -> bool:
        """Check if Google credentials are configured."""
        return bool(self.google_credentials_path or self.google_credentials_json)

    def has_trading_api(self) -> bool:
        """Check if Trading API access is configured."""
        return bool(self.ebay_trading_token)

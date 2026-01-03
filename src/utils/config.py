"""Configuration management using environment variables."""

import os
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Application configuration loaded from environment variables."""

    # eBay API - User Token (short-lived, 2 hours)
    ebay_user_token: Optional[str] = Field(
        None, description="eBay OAuth 2.0 User Token (optional if using refresh token)"
    )

    # eBay API - Refresh Token (long-lived, 18 months) - RECOMMENDED
    ebay_refresh_token: Optional[str] = Field(
        None, description="eBay OAuth 2.0 Refresh Token for auto-renewal"
    )
    ebay_client_id: Optional[str] = Field(
        None, description="eBay App Client ID (required for token refresh)"
    )
    ebay_client_secret: Optional[str] = Field(
        None, description="eBay App Client Secret (required for token refresh)"
    )

    # eBay Trading API (legacy)
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

    # Email notifications
    email_smtp_host: str = Field("smtp.gmail.com", description="SMTP server host")
    email_smtp_port: int = Field(587, description="SMTP server port")
    email_sender: Optional[str] = Field(None, description="Sender email address")
    email_password: Optional[str] = Field(None, description="Sender email password")
    email_recipient: Optional[str] = Field(None, description="Recipient email address")

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

        # Check for eBay credentials - need either user token OR refresh token setup
        ebay_user_token = os.getenv("EBAY_USER_TOKEN")
        ebay_refresh_token = os.getenv("EBAY_REFRESH_TOKEN")
        ebay_client_id = os.getenv("EBAY_CLIENT_ID")
        ebay_client_secret = os.getenv("EBAY_CLIENT_SECRET")

        has_refresh_setup = all([ebay_refresh_token, ebay_client_id, ebay_client_secret])

        if not ebay_user_token and not has_refresh_setup:
            raise ValueError(
                "eBay credentials required. Provide either:\n"
                "  - EBAY_USER_TOKEN (expires in 2 hours), or\n"
                "  - EBAY_REFRESH_TOKEN + EBAY_CLIENT_ID + EBAY_CLIENT_SECRET (recommended, auto-refreshes)"
            )

        return cls(
            ebay_user_token=ebay_user_token,
            ebay_refresh_token=ebay_refresh_token,
            ebay_client_id=ebay_client_id,
            ebay_client_secret=ebay_client_secret,
            ebay_trading_token=os.getenv("EBAY_TRADING_TOKEN"),
            google_credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH"),
            google_credentials_json=os.getenv("GOOGLE_CREDENTIALS_JSON"),
            google_sheet_id=os.getenv("GOOGLE_SHEET_ID"),
            create_new_sheet=os.getenv("CREATE_NEW_SHEET", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            timezone=os.getenv("TIMEZONE", "America/New_York"),
            sync_start_date=os.getenv("SYNC_START_DATE", "2025-11-01"),
            email_smtp_host=os.getenv("EMAIL_SMTP_HOST") or "smtp.gmail.com",
            email_smtp_port=int(os.getenv("EMAIL_SMTP_PORT") or "587"),
            email_sender=os.getenv("EMAIL_SENDER"),
            email_password=os.getenv("EMAIL_PASSWORD"),
            email_recipient=os.getenv("EMAIL_RECIPIENT"),
        )

    def has_google_credentials(self) -> bool:
        """Check if Google credentials are configured."""
        return bool(self.google_credentials_path or self.google_credentials_json)

    def has_trading_api(self) -> bool:
        """Check if Trading API access is configured."""
        return bool(self.ebay_trading_token)

    def has_email_configured(self) -> bool:
        """Check if email notifications are configured."""
        return all([self.email_sender, self.email_password, self.email_recipient])

    def can_auto_refresh(self) -> bool:
        """Check if automatic token refresh is configured."""
        return all([self.ebay_refresh_token, self.ebay_client_id, self.ebay_client_secret])

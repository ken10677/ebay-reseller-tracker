"""eBay API authentication handling."""

from datetime import datetime, timedelta
from typing import Optional

import requests

from src.utils.logging import get_logger

logger = get_logger("ebay.auth")


class EbayAuth:
    """Handles eBay API authentication.

    Currently supports OAuth 2.0 User Tokens (Bearer tokens).
    Token refresh automation is a future enhancement.
    """

    def __init__(
        self,
        user_token: str,
        trading_token: Optional[str] = None,
    ) -> None:
        """Initialize eBay authentication.

        Args:
            user_token: OAuth 2.0 User Token for RESTful APIs
            trading_token: Auth'n'Auth token for Trading API (optional)
        """
        self.user_token = user_token
        self.trading_token = trading_token
        self._token_expiry: Optional[datetime] = None

    def get_rest_headers(self) -> dict[str, str]:
        """Get headers for RESTful API calls.

        Returns:
            Headers dict with Authorization bearer token.
        """
        return {
            "Authorization": f"Bearer {self.user_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_trading_headers(self, call_name: str) -> dict[str, str]:
        """Get headers for Trading API (legacy XML) calls.

        Args:
            call_name: The Trading API call name (e.g., 'GetItem')

        Returns:
            Headers dict for Trading API requests.
        """
        if not self.trading_token:
            raise ValueError("Trading API token not configured")

        return {
            "X-EBAY-API-SITEID": "0",  # US site
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": call_name,
            "Content-Type": "text/xml",
        }

    def has_trading_api(self) -> bool:
        """Check if Trading API access is available."""
        return bool(self.trading_token)

    def validate_token(self) -> bool:
        """Validate that the user token is working.

        Makes a simple API call to verify the token is valid.

        Returns:
            True if token is valid, False otherwise.
        """
        try:
            response = requests.get(
                "https://apiz.ebay.com/sell/finances/v1/seller_funds_summary",
                headers=self.get_rest_headers(),
                timeout=30,
            )

            if response.status_code == 200:
                logger.info("eBay token validated successfully")
                return True
            elif response.status_code == 401:
                logger.error("eBay token is expired or invalid")
                return False
            else:
                logger.warning(f"Token validation returned status {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.error(f"Token validation request failed: {e}")
            return False

    def check_token_expiry(self) -> Optional[int]:
        """Check approximate days until token expiry.

        Note: This is a rough estimate. eBay tokens typically expire after
        18 months, but the exact expiry isn't easily determined without
        the refresh token flow.

        Returns:
            Estimated days until expiry, or None if unknown.
        """
        # For now, we can't determine exact expiry without the OAuth flow
        # This could be enhanced to track when the token was last refreshed
        return None

    def get_token_status_message(self) -> str:
        """Get a human-readable token status message.

        Returns:
            Status message about token health.
        """
        if self.validate_token():
            expiry_days = self.check_token_expiry()
            if expiry_days and expiry_days < 30:
                return f"⚠️ Token valid but expires in ~{expiry_days} days - refresh soon!"
            return "✓ Token is valid"
        return "✗ Token is expired or invalid - please refresh"

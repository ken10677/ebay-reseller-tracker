"""eBay API authentication handling with automatic token refresh."""

import base64
from datetime import datetime, timedelta
from typing import Optional

import requests

from src.utils.logging import get_logger

logger = get_logger("ebay.auth")


class EbayAuth:
    """Handles eBay API authentication with automatic token refresh.

    Supports OAuth 2.0 with refresh tokens for automatic renewal.
    User tokens expire after 2 hours, but refresh tokens last 18 months.
    """

    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"

    def __init__(
        self,
        user_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        trading_token: Optional[str] = None,
    ) -> None:
        """Initialize eBay authentication.

        For automatic refresh, provide refresh_token + client_id + client_secret.
        For manual token management, provide just user_token.

        Args:
            user_token: OAuth 2.0 User Token for RESTful APIs (expires in 2 hours)
            refresh_token: OAuth 2.0 Refresh Token (expires in 18 months)
            client_id: eBay App Client ID (for token refresh)
            client_secret: eBay App Client Secret (for token refresh)
            trading_token: Auth'n'Auth token for Trading API (optional)
        """
        self.user_token = user_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.trading_token = trading_token
        self._token_expiry: Optional[datetime] = None
        self._can_refresh = all([refresh_token, client_id, client_secret])

        if self._can_refresh:
            logger.info("Token refresh enabled - tokens will auto-renew")
        elif user_token:
            logger.info("Using provided user token (no auto-refresh)")
        else:
            logger.warning("No authentication configured!")

    def _get_basic_auth_header(self) -> str:
        """Get Base64-encoded client credentials for OAuth.

        Returns:
            Base64 encoded client_id:client_secret
        """
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def refresh_user_token(self) -> bool:
        """Refresh the user token using the refresh token.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        if not self._can_refresh:
            logger.error("Cannot refresh: missing refresh_token, client_id, or client_secret")
            return False

        logger.info("Refreshing eBay user token...")

        try:
            response = requests.post(
                self.TOKEN_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": self._get_basic_auth_header(),
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "scope": "https://api.ebay.com/oauth/api_scope/sell.finances "
                    "https://api.ebay.com/oauth/api_scope/sell.fulfillment "
                    "https://api.ebay.com/oauth/api_scope/sell.inventory "
                    "https://api.ebay.com/oauth/api_scope/sell.analytics",
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                self.user_token = data["access_token"]
                expires_in = data.get("expires_in", 7200)  # Default 2 hours
                self._token_expiry = datetime.now() + timedelta(seconds=expires_in)

                logger.info(f"Token refreshed successfully, expires in {expires_in} seconds")
                return True
            else:
                logger.error(f"Token refresh failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"Token refresh request failed: {e}")
            return False

    def ensure_valid_token(self) -> bool:
        """Ensure we have a valid user token, refreshing if needed.

        Returns:
            True if we have a valid token, False otherwise.
        """
        # If we have a token expiry and it's still valid, we're good
        if self._token_expiry and datetime.now() < self._token_expiry - timedelta(minutes=5):
            return True

        # Try to validate existing token
        if self.user_token and self.validate_token():
            return True

        # Try to refresh
        if self._can_refresh:
            if self.refresh_user_token():
                return True

        return False

    def get_rest_headers(self) -> dict[str, str]:
        """Get headers for RESTful API calls.

        Automatically refreshes token if needed and possible.

        Returns:
            Headers dict with Authorization bearer token.
        """
        # Try to ensure we have a valid token
        if self._can_refresh:
            self.ensure_valid_token()

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

    def can_auto_refresh(self) -> bool:
        """Check if automatic token refresh is configured."""
        return self._can_refresh

    def validate_token(self) -> bool:
        """Validate that the user token is working.

        Makes a simple API call to verify the token is valid.

        Returns:
            True if token is valid, False otherwise.
        """
        if not self.user_token:
            return False

        try:
            response = requests.get(
                "https://apiz.ebay.com/sell/finances/v1/seller_funds_summary",
                headers={
                    "Authorization": f"Bearer {self.user_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if response.status_code == 200:
                logger.info("eBay token validated successfully")
                return True
            elif response.status_code == 401:
                logger.warning("eBay token is expired or invalid")
                return False
            else:
                logger.warning(f"Token validation returned status {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.error(f"Token validation request failed: {e}")
            return False

    def get_token_status_message(self) -> str:
        """Get a human-readable token status message.

        Returns:
            Status message about token health.
        """
        if self._can_refresh:
            if self.ensure_valid_token():
                return "Token valid (auto-refresh enabled)"
            return "Token refresh failed - check credentials"

        if self.validate_token():
            return "Token valid (manual refresh required when it expires)"

        return "Token is expired or invalid - please refresh manually"

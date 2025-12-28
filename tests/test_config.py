"""Tests for configuration module."""

import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.config import Config


class TestConfig:
    """Tests for Config class."""

    def test_config_creation(self) -> None:
        """Test creating Config directly."""
        config = Config(
            ebay_user_token="test_token",
            google_credentials_path="/path/to/creds.json",
            google_sheet_id="sheet_id_123",
        )

        assert config.ebay_user_token == "test_token"
        assert config.google_credentials_path == "/path/to/creds.json"
        assert config.google_sheet_id == "sheet_id_123"

    def test_config_defaults(self) -> None:
        """Test Config default values."""
        config = Config(ebay_user_token="test_token")

        assert config.log_level == "INFO"
        assert config.timezone == "America/New_York"
        assert config.sync_start_date == date(2025, 11, 1)
        assert config.create_new_sheet is False

    def test_config_from_env(self) -> None:
        """Test loading Config from environment."""
        env_vars = {
            "EBAY_USER_TOKEN": "env_token",
            "GOOGLE_CREDENTIALS_PATH": "/env/path/creds.json",
            "GOOGLE_SHEET_ID": "env_sheet_id",
            "LOG_LEVEL": "DEBUG",
            "TIMEZONE": "America/Los_Angeles",
            "SYNC_START_DATE": "2025-06-01",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = Config.from_env()

        assert config.ebay_user_token == "env_token"
        assert config.google_credentials_path == "/env/path/creds.json"
        assert config.log_level == "DEBUG"
        assert config.timezone == "America/Los_Angeles"
        assert config.sync_start_date == date(2025, 6, 1)

    def test_config_missing_token(self) -> None:
        """Test that missing token raises error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="EBAY_USER_TOKEN"):
                Config.from_env()

    def test_config_has_google_credentials(self) -> None:
        """Test has_google_credentials method."""
        # With path
        config = Config(
            ebay_user_token="token",
            google_credentials_path="/path/creds.json",
        )
        assert config.has_google_credentials() is True

        # With JSON
        config = Config(
            ebay_user_token="token",
            google_credentials_json='{"key": "value"}',
        )
        assert config.has_google_credentials() is True

        # Without either
        config = Config(ebay_user_token="token")
        assert config.has_google_credentials() is False

    def test_config_has_trading_api(self) -> None:
        """Test has_trading_api method."""
        # With trading token
        config = Config(
            ebay_user_token="token",
            ebay_trading_token="trading_token",
        )
        assert config.has_trading_api() is True

        # Without trading token
        config = Config(ebay_user_token="token")
        assert config.has_trading_api() is False

    def test_config_date_parsing(self) -> None:
        """Test sync_start_date parsing."""
        # String date
        config = Config(
            ebay_user_token="token",
            sync_start_date="2025-12-25",
        )
        assert config.sync_start_date == date(2025, 12, 25)

        # Date object
        config = Config(
            ebay_user_token="token",
            sync_start_date=date(2025, 1, 1),
        )
        assert config.sync_start_date == date(2025, 1, 1)

    def test_config_api_urls(self) -> None:
        """Test API URL defaults."""
        config = Config(ebay_user_token="token")

        assert "apiz.ebay.com" in config.ebay_finances_base_url
        assert "apiz.ebay.com" in config.ebay_fulfillment_base_url
        assert "api.ebay.com/ws/api.dll" in config.ebay_trading_base_url

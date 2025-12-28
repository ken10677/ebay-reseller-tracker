"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture(autouse=True)
def reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset environment variables for each test."""
    # Remove any eBay/Google env vars that might interfere
    for key in list(vars().keys()):
        if key.startswith(("EBAY_", "GOOGLE_")):
            monkeypatch.delenv(key, raising=False)

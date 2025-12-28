"""Logging configuration for the application."""

import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO") -> None:
    """Set up logging configuration for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("gspread").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name. If None, returns the root logger.

    Returns:
        Logger instance.
    """
    if name:
        return logging.getLogger(f"ebay_tracker.{name}")
    return logging.getLogger("ebay_tracker")

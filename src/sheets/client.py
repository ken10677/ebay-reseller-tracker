"""Google Sheets client for reading and writing data."""

import json
import base64
import tempfile
from pathlib import Path
from typing import Any, Optional

import gspread
from google.oauth2.service_account import Credentials

from src.utils.logging import get_logger

logger = get_logger("sheets.client")

# Scopes required for full Sheets access
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsClient:
    """Client for Google Sheets API operations.

    Handles authentication, sheet creation, and data operations.
    """

    SHEET_NAME = "eBay Reseller Tracker"

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        credentials_json: Optional[str] = None,
        sheet_id: Optional[str] = None,
    ) -> None:
        """Initialize Google Sheets client.

        Args:
            credentials_path: Path to service account JSON file
            credentials_json: Base64-encoded credentials JSON (for GitHub Actions)
            sheet_id: Existing sheet ID to use

        Raises:
            ValueError: If no credentials provided
        """
        self.sheet_id = sheet_id
        self._client: Optional[gspread.Client] = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None

        # Handle credentials
        if credentials_json:
            # Decode base64 credentials (for GitHub Actions)
            try:
                decoded = base64.b64decode(credentials_json)
                self._credentials_dict = json.loads(decoded)
            except Exception:
                # Try as plain JSON string
                self._credentials_dict = json.loads(credentials_json)
            self._credentials_path = None
        elif credentials_path:
            self._credentials_path = Path(credentials_path)
            self._credentials_dict = None
        else:
            raise ValueError("Either credentials_path or credentials_json required")

    def _get_client(self) -> gspread.Client:
        """Get or create authenticated gspread client.

        Returns:
            Authenticated gspread client
        """
        if self._client is not None:
            return self._client

        if self._credentials_dict:
            # Create temp file for credentials
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(self._credentials_dict, f)
                temp_path = f.name

            creds = Credentials.from_service_account_file(temp_path, scopes=SCOPES)
            Path(temp_path).unlink()  # Clean up temp file
        else:
            creds = Credentials.from_service_account_file(
                str(self._credentials_path), scopes=SCOPES
            )

        self._client = gspread.authorize(creds)
        logger.info("Google Sheets client authenticated")
        return self._client

    def get_spreadsheet(self) -> gspread.Spreadsheet:
        """Get or create the spreadsheet.

        Returns:
            gspread Spreadsheet object
        """
        if self._spreadsheet is not None:
            return self._spreadsheet

        client = self._get_client()

        if self.sheet_id:
            # Open existing sheet
            try:
                self._spreadsheet = client.open_by_key(self.sheet_id)
                logger.info(f"Opened existing spreadsheet: {self._spreadsheet.title}")
            except gspread.SpreadsheetNotFound:
                raise ValueError(
                    f"Spreadsheet with ID {self.sheet_id} not found. "
                    "Make sure you've shared it with the service account email."
                )
        else:
            # Create new sheet
            self._spreadsheet = client.create(self.SHEET_NAME)
            self.sheet_id = self._spreadsheet.id
            logger.info(f"Created new spreadsheet: {self.SHEET_NAME}")
            logger.info(f"Sheet ID: {self.sheet_id}")
            logger.info(
                f"Sheet URL: https://docs.google.com/spreadsheets/d/{self.sheet_id}"
            )

        return self._spreadsheet

    def get_worksheet(self, title: str) -> gspread.Worksheet:
        """Get or create a worksheet by title.

        Args:
            title: Worksheet title

        Returns:
            gspread Worksheet object
        """
        spreadsheet = self.get_spreadsheet()

        try:
            worksheet = spreadsheet.worksheet(title)
            logger.debug(f"Found existing worksheet: {title}")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=50)
            logger.info(f"Created new worksheet: {title}")

        return worksheet

    def setup_worksheets(self) -> dict[str, gspread.Worksheet]:
        """Set up all required worksheets with headers.

        Returns:
            Dict mapping worksheet names to worksheet objects
        """
        worksheets = {}

        # Create Inventory worksheet
        inventory = self.get_worksheet("Inventory")
        worksheets["inventory"] = inventory

        # Create Expenses worksheet
        expenses = self.get_worksheet("Expenses")
        worksheets["expenses"] = expenses

        # Create Dashboard worksheet
        dashboard = self.get_worksheet("Dashboard")
        worksheets["dashboard"] = dashboard

        # Create Metrics Log worksheet
        metrics_log = self.get_worksheet("Metrics Log")
        worksheets["metrics_log"] = metrics_log

        # Delete default "Sheet1" if it exists
        spreadsheet = self.get_spreadsheet()
        try:
            sheet1 = spreadsheet.worksheet("Sheet1")
            spreadsheet.del_worksheet(sheet1)
            logger.debug("Deleted default Sheet1")
        except gspread.WorksheetNotFound:
            pass

        logger.info("All worksheets set up")
        return worksheets

    def get_all_values(self, worksheet_name: str) -> list[list[str]]:
        """Get all values from a worksheet.

        Args:
            worksheet_name: Name of the worksheet

        Returns:
            2D list of cell values
        """
        worksheet = self.get_worksheet(worksheet_name)
        return worksheet.get_all_values()

    def get_column_values(self, worksheet_name: str, column: int) -> list[str]:
        """Get all values from a specific column.

        Args:
            worksheet_name: Name of the worksheet
            column: Column number (1-indexed)

        Returns:
            List of cell values
        """
        worksheet = self.get_worksheet(worksheet_name)
        return worksheet.col_values(column)

    def find_row_by_value(
        self, worksheet_name: str, column: int, value: str
    ) -> Optional[int]:
        """Find the row number containing a value in a specific column.

        Args:
            worksheet_name: Name of the worksheet
            column: Column number (1-indexed)
            value: Value to search for

        Returns:
            Row number (1-indexed) or None if not found
        """
        worksheet = self.get_worksheet(worksheet_name)
        try:
            cell = worksheet.find(value, in_column=column)
            return cell.row if cell else None
        except gspread.CellNotFound:
            return None

    def update_row(
        self,
        worksheet_name: str,
        row: int,
        values: list[Any],
        start_col: int = 1,
    ) -> None:
        """Update a row with values.

        Args:
            worksheet_name: Name of the worksheet
            row: Row number (1-indexed)
            values: List of values to write
            start_col: Starting column (1-indexed)
        """
        worksheet = self.get_worksheet(worksheet_name)
        end_col = start_col + len(values) - 1

        # Convert column numbers to letters
        start_letter = self._col_to_letter(start_col)
        end_letter = self._col_to_letter(end_col)

        range_str = f"{start_letter}{row}:{end_letter}{row}"
        worksheet.update(range_str, [values], value_input_option="USER_ENTERED")

    def append_row(self, worksheet_name: str, values: list[Any]) -> int:
        """Append a row to the worksheet.

        Args:
            worksheet_name: Name of the worksheet
            values: List of values to write

        Returns:
            Row number of the appended row
        """
        worksheet = self.get_worksheet(worksheet_name)
        worksheet.append_row(values, value_input_option="USER_ENTERED")

        # Get the new row number
        return len(worksheet.get_all_values())

    def batch_update(
        self,
        worksheet_name: str,
        updates: list[dict[str, Any]],
    ) -> None:
        """Perform batch updates for efficiency.

        Args:
            worksheet_name: Name of the worksheet
            updates: List of updates, each with 'range' and 'values' keys
        """
        worksheet = self.get_worksheet(worksheet_name)
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")

    def set_headers(self, worksheet_name: str, headers: list[str]) -> None:
        """Set the header row for a worksheet.

        Args:
            worksheet_name: Name of the worksheet
            headers: List of header strings
        """
        worksheet = self.get_worksheet(worksheet_name)

        # Check if headers already exist
        existing = worksheet.row_values(1)
        if existing == headers:
            logger.debug(f"Headers already set for {worksheet_name}")
            return

        # Update header row
        self.update_row(worksheet_name, 1, headers)

        # Format header row (bold, frozen)
        worksheet.format("1:1", {"textFormat": {"bold": True}})
        worksheet.freeze(rows=1)

        logger.info(f"Set headers for {worksheet_name}")

    def get_sheet_url(self) -> str:
        """Get the URL of the spreadsheet.

        Returns:
            Google Sheets URL
        """
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}"

    @staticmethod
    def _col_to_letter(col: int) -> str:
        """Convert column number to letter(s).

        Args:
            col: Column number (1-indexed)

        Returns:
            Column letter(s) (A, B, ..., Z, AA, AB, ...)
        """
        result = ""
        while col > 0:
            col, remainder = divmod(col - 1, 26)
            result = chr(65 + remainder) + result
        return result

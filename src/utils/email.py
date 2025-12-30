"""Email notification utilities for eBay Reseller Tracker."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from src.utils.logging import get_logger

logger = get_logger("utils.email")


class EmailNotifier:
    """Send email notifications for sync events.

    Uses SMTP to send email notifications. Configure via environment variables:
    - EMAIL_SMTP_HOST: SMTP server host (default: smtp.gmail.com)
    - EMAIL_SMTP_PORT: SMTP server port (default: 587)
    - EMAIL_SENDER: Sender email address
    - EMAIL_PASSWORD: Sender email password or app password
    - EMAIL_RECIPIENT: Recipient email address
    """

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        sender: Optional[str] = None,
        password: Optional[str] = None,
        recipient: Optional[str] = None,
    ) -> None:
        """Initialize email notifier.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            sender: Sender email address
            password: Sender email password
            recipient: Recipient email address
        """
        self.smtp_host = smtp_host or os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.sender = sender or os.getenv("EMAIL_SENDER")
        self.password = password or os.getenv("EMAIL_PASSWORD")
        self.recipient = recipient or os.getenv("EMAIL_RECIPIENT")

    def is_configured(self) -> bool:
        """Check if email notifications are properly configured.

        Returns:
            True if all required settings are present
        """
        return all([self.sender, self.password, self.recipient])

    def send_email(
        self,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """Send an email notification.

        Args:
            subject: Email subject line
            body: Plain text email body
            html_body: Optional HTML email body

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.warning("Email not configured - skipping notification")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = self.recipient

            # Attach plain text version
            msg.attach(MIMEText(body, "plain"))

            # Attach HTML version if provided
            if html_body:
                msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.send_message(msg)

            logger.info(f"Email sent: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_sync_summary(
        self,
        stats: dict,
        summary: dict,
        sheet_url: str,
    ) -> bool:
        """Send a sync summary email.

        Args:
            stats: Sync statistics dict
            summary: Sheet summary dict
            sheet_url: URL to the Google Sheet

        Returns:
            True if email was sent successfully
        """
        subject = f"eBay Sync Complete - {summary.get('sold_items', 0)} Sales, ${summary.get('total_profit', 0):.2f} Profit"

        body = f"""eBay Reseller Tracker - Daily Sync Complete

SYNC STATISTICS
---------------
New Transactions: {stats.get('new_transactions', 0)}
New Orders: {stats.get('new_orders', 0)}
Updated Listings: {stats.get('updated_listings', 0)}
Items Synced: {stats.get('items_synced', 0)}

SUMMARY
-------
Total Sold: {summary.get('sold_items', 0)} items
Active Listings: {summary.get('active_listings', 0)}
Sell-Through Rate: {summary.get('sell_through_rate', 0):.1f}%

FINANCIALS
----------
Total Revenue: ${summary.get('total_revenue', 0):.2f}
Total Fees: ${summary.get('total_fees', 0):.2f}
Total Profit: ${summary.get('total_profit', 0):.2f}
Average ROI: {summary.get('average_roi', 0):.1f}%

View full details: {sheet_url}

---
eBay Reseller Tracker
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #0064d2; color: white; padding: 20px; text-align: center; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 5px; }}
        .section h3 {{ margin-top: 0; color: #0064d2; }}
        .stat {{ display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #ddd; }}
        .stat:last-child {{ border-bottom: none; }}
        .highlight {{ font-size: 24px; font-weight: bold; color: #28a745; }}
        .btn {{ display: inline-block; background: #0064d2; color: white; padding: 10px 20px;
                text-decoration: none; border-radius: 5px; margin-top: 15px; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>eBay Sync Complete</h1>
        </div>

        <div class="section">
            <h3>Today's Highlights</h3>
            <p class="highlight">${summary.get('total_profit', 0):.2f} Profit</p>
            <div class="stat"><span>Items Sold:</span><strong>{summary.get('sold_items', 0)}</strong></div>
            <div class="stat"><span>Revenue:</span><strong>${summary.get('total_revenue', 0):.2f}</strong></div>
            <div class="stat"><span>Fees:</span><strong>${summary.get('total_fees', 0):.2f}</strong></div>
        </div>

        <div class="section">
            <h3>Sync Statistics</h3>
            <div class="stat"><span>New Transactions:</span><strong>{stats.get('new_transactions', 0)}</strong></div>
            <div class="stat"><span>New Orders:</span><strong>{stats.get('new_orders', 0)}</strong></div>
            <div class="stat"><span>Updated Listings:</span><strong>{stats.get('updated_listings', 0)}</strong></div>
            <div class="stat"><span>Items Synced:</span><strong>{stats.get('items_synced', 0)}</strong></div>
        </div>

        <div class="section">
            <h3>Inventory Status</h3>
            <div class="stat"><span>Active Listings:</span><strong>{summary.get('active_listings', 0)}</strong></div>
            <div class="stat"><span>Sell-Through Rate:</span><strong>{summary.get('sell_through_rate', 0):.1f}%</strong></div>
            <div class="stat"><span>Average ROI:</span><strong>{summary.get('average_roi', 0):.1f}%</strong></div>
        </div>

        <div style="text-align: center;">
            <a href="{sheet_url}" class="btn">View Full Report</a>
        </div>

        <div class="footer">
            <p>eBay Reseller Tracker - Automated Daily Sync</p>
        </div>
    </div>
</body>
</html>
"""

        return self.send_email(subject, body, html_body)

    def send_error_notification(
        self,
        error_message: str,
        details: Optional[str] = None,
    ) -> bool:
        """Send an error notification email.

        Args:
            error_message: Main error message
            details: Additional error details

        Returns:
            True if email was sent successfully
        """
        subject = "eBay Sync FAILED - Action Required"

        body = f"""eBay Reseller Tracker - Sync Failed!

ERROR
-----
{error_message}

{f"DETAILS{chr(10)}-------{chr(10)}{details}" if details else ""}

COMMON CAUSES
-------------
- eBay OAuth token expired (refresh at https://developer.ebay.com)
- Google Sheets API quota exceeded
- Network/API temporary outage

Please check the logs for more information.

---
eBay Reseller Tracker
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 5px; }}
        .section h3 {{ margin-top: 0; color: #dc3545; }}
        .error-box {{ background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Sync Failed!</h1>
        </div>

        <div class="error-box">
            <strong>Error:</strong> {error_message}
        </div>

        {f'<div class="section"><h3>Details</h3><pre>{details}</pre></div>' if details else ''}

        <div class="section">
            <h3>Common Causes</h3>
            <ul>
                <li>eBay OAuth token expired</li>
                <li>Google Sheets API quota exceeded</li>
                <li>Network/API temporary outage</li>
            </ul>
        </div>

        <div class="footer">
            <p>eBay Reseller Tracker - Automated Daily Sync</p>
        </div>
    </div>
</body>
</html>
"""

        return self.send_email(subject, body, html_body)

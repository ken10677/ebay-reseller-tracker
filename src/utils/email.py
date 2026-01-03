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
        """Send a comprehensive sync summary email.

        Args:
            stats: Sync statistics dict
            summary: Sheet summary dict with detailed financials
            sheet_url: URL to the Google Sheet

        Returns:
            True if email was sent successfully
        """
        # Format net from eBay (profit before COGS) for the highlight box
        net_from_ebay = summary.get('total_net_from_ebay', 0)
        net_indicator = "+" if net_from_ebay >= 0 else ""

        # Net profit (after COGS) for the bottom line section
        net_profit = summary.get('total_net_profit', 0) or summary.get('total_profit', 0)
        profit_indicator = "+" if net_profit >= 0 else ""

        subject = f"eBay Digest: {summary.get('sold_items', 0)} Sales | ${summary.get('total_gross_revenue', 0) or summary.get('total_revenue', 0):.2f} Revenue"

        # Build plain text body
        body = f"""eBay Reseller Tracker - All-Time Summary
{'=' * 50}

INVENTORY STATUS
----------------
Total Items Sold: {summary.get('sold_items', 0)}
Active Listings: {summary.get('active_listings', 0)}
Sell-Through Rate: {summary.get('sell_through_rate', 0):.1f}%

MONEY IN (All Time)
-------------------
Item Sales: ${summary.get('total_final_sale_price', 0):.2f}
Shipping Charged: ${summary.get('total_shipping_charged', 0):.2f}
-----------------------------------------
TOTAL REVENUE: ${summary.get('total_gross_revenue', 0) or summary.get('total_revenue', 0):.2f}

MONEY OUT (All Time)
--------------------
eBay Fees:
  Final Value Fees: ${summary.get('total_final_value_fee', 0):.2f}
  Fixed Per-Order: ${summary.get('total_fixed_fee', 0):.2f}
  Promoted Listings: ${summary.get('total_promoted_fee', 0):.2f}
  International: ${summary.get('total_international_fee', 0):.2f}
  Other Fees: ${summary.get('total_other_fees', 0):.2f}
  -----------------------
  TOTAL FEES: ${summary.get('total_fees', 0):.2f}

Shipping Costs: ${summary.get('total_shipping_cost', 0):.2f}
COGS (Items Sold): ${summary.get('total_cogs_sold', 0):.2f}
Other Expenses: ${summary.get('total_expenses', 0):.2f}

BOTTOM LINE
-----------
NET FROM EBAY: {net_indicator}${net_from_ebay:.2f}
  (Revenue - Fees - Shipping)
NET PROFIT: {profit_indicator}${net_profit:.2f}
  (After COGS, requires item cost data)

ROI PERFORMANCE
---------------
Median ROI: {summary.get('median_roi', 0):.1f}% (typical return per item)
Average ROI: {summary.get('average_roi', 0):.1f}%
Items with COGS data: {summary.get('items_with_cogs', 0)}/{summary.get('sold_items', 0)}

INVENTORY VALUE
---------------
Active Inventory (at cost): ${summary.get('total_cogs_active', 0):.2f}

Today's Sync: {stats.get('items_synced', 0)} items synced

View full details: {sheet_url}

---
eBay Reseller Tracker
"""

        # Build HTML body
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5; color: #333; margin: 0; padding: 0; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; }}
        .header {{ background: linear-gradient(135deg, #0064d2 0%, #003366 100%); color: white; padding: 30px 20px; text-align: center; }}
        .header h1 {{ margin: 0 0 5px 0; font-size: 24px; }}
        .header .subtitle {{ opacity: 0.9; font-size: 14px; }}
        .section {{ padding: 20px; border-bottom: 1px solid #eee; }}
        .section:last-of-type {{ border-bottom: none; }}
        .section-title {{ font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: #666; margin-bottom: 15px; }}
        .stat-row {{ display: flex; justify-content: space-between; padding: 8px 0; }}
        .stat-row.indent {{ padding-left: 20px; font-size: 14px; color: #666; }}
        .stat-row.total {{ font-weight: 600; border-top: 1px solid #ddd; margin-top: 5px; padding-top: 10px; }}
        .stat-label {{ color: #555; }}
        .stat-value {{ font-weight: 500; }}
        .highlight-box {{ background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%); color: white; padding: 25px; text-align: center; margin: 20px; border-radius: 10px; }}
        .highlight-box.negative {{ background: linear-gradient(135deg, #dc3545 0%, #bd2130 100%); }}
        .highlight-box .amount {{ font-size: 36px; font-weight: bold; margin-bottom: 5px; }}
        .highlight-box .label {{ font-size: 14px; opacity: 0.9; }}
        .roi-box {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        .roi-stat {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; }}
        .roi-stat .value {{ font-size: 24px; font-weight: bold; color: #0064d2; }}
        .roi-stat .label {{ font-size: 12px; color: #666; }}
        .btn {{ display: inline-block; background: #0064d2; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: 500; }}
        .btn:hover {{ background: #0052a3; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; background: #f8f9fa; }}
        .inventory-badge {{ display: inline-block; background: #e3f2fd; color: #0064d2; padding: 5px 12px; border-radius: 20px; font-size: 14px; margin: 5px; }}
        .divider {{ height: 1px; background: #eee; margin: 15px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>eBay Sales Digest</h1>
            <div class="subtitle">All-Time Summary</div>
        </div>

        <!-- Net from eBay Highlight (Revenue - Fees - Shipping, before COGS) -->
        <div class="highlight-box{' negative' if net_from_ebay < 0 else ''}">
            <div class="amount">{net_indicator}${abs(net_from_ebay):.2f}</div>
            <div class="label">Net from eBay</div>
            <div style="font-size: 11px; opacity: 0.8; margin-top: 5px;">Revenue - Fees - Shipping</div>
        </div>

        <!-- Quick Stats -->
        <div class="section" style="text-align: center; padding: 15px;">
            <span class="inventory-badge">{summary.get('sold_items', 0)} Items Sold</span>
            <span class="inventory-badge">{summary.get('active_listings', 0)} Active</span>
            <span class="inventory-badge">{summary.get('sell_through_rate', 0):.0f}% Sell-Through</span>
        </div>

        <!-- Money In -->
        <div class="section">
            <div class="section-title">Money In</div>
            <div class="stat-row">
                <span class="stat-label">Item Sales</span>
                <span class="stat-value">${summary.get('total_final_sale_price', 0):.2f}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Shipping Charged</span>
                <span class="stat-value">${summary.get('total_shipping_charged', 0):.2f}</span>
            </div>
            <div class="stat-row total">
                <span class="stat-label">TOTAL REVENUE</span>
                <span class="stat-value" style="color: #28a745;">${summary.get('total_gross_revenue', 0) or summary.get('total_revenue', 0):.2f}</span>
            </div>
        </div>

        <!-- Money Out -->
        <div class="section">
            <div class="section-title">Money Out</div>

            <div class="stat-row">
                <span class="stat-label">eBay Fees</span>
                <span class="stat-value">${summary.get('total_fees', 0):.2f}</span>
            </div>
            <div class="stat-row indent">
                <span class="stat-label">Final Value Fees</span>
                <span class="stat-value">${summary.get('total_final_value_fee', 0):.2f}</span>
            </div>
            <div class="stat-row indent">
                <span class="stat-label">Fixed Per-Order</span>
                <span class="stat-value">${summary.get('total_fixed_fee', 0):.2f}</span>
            </div>
            <div class="stat-row indent">
                <span class="stat-label">Promoted Listings</span>
                <span class="stat-value">${summary.get('total_promoted_fee', 0):.2f}</span>
            </div>

            <div class="divider"></div>

            <div class="stat-row">
                <span class="stat-label">Shipping Costs</span>
                <span class="stat-value">${summary.get('total_shipping_cost', 0):.2f}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Cost of Goods Sold</span>
                <span class="stat-value">${summary.get('total_cogs_sold', 0):.2f}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Other Expenses</span>
                <span class="stat-value">${summary.get('total_expenses', 0):.2f}</span>
            </div>
        </div>

        <!-- Bottom Line (Net Profit after COGS) -->
        <div class="section" style="background: #f8f9fa;">
            <div class="section-title">Bottom Line (After COGS)</div>
            <div class="stat-row total" style="border-top: none; padding-top: 0;">
                <span class="stat-label">Net Profit</span>
                <span class="stat-value" style="color: {'#28a745' if net_profit >= 0 else '#dc3545'};">{profit_indicator}${abs(net_profit):.2f}</span>
            </div>
            <div style="font-size: 12px; color: #666; text-align: center; margin-top: 10px;">
                Based on {summary.get('items_with_cogs', 0)} of {summary.get('sold_items', 0)} items with COGS data entered
            </div>
        </div>

        <!-- ROI Performance -->
        <div class="section">
            <div class="section-title">ROI Performance</div>
            <div class="roi-box">
                <div class="roi-stat">
                    <div>
                        <div class="value">{summary.get('median_roi', 0):.1f}%</div>
                        <div class="label">Median ROI (typical return)</div>
                    </div>
                    <div style="text-align: right;">
                        <div class="value">{summary.get('average_roi', 0):.1f}%</div>
                        <div class="label">Average ROI</div>
                    </div>
                </div>
            </div>
            <div style="font-size: 12px; color: #666; text-align: center;">
                Based on {summary.get('items_with_cogs', 0)} of {summary.get('sold_items', 0)} items with COGS data
            </div>
        </div>

        <!-- Inventory Value -->
        <div class="section">
            <div class="section-title">Active Inventory</div>
            <div class="stat-row">
                <span class="stat-label">Inventory Value (at cost)</span>
                <span class="stat-value">${summary.get('total_cogs_active', 0):.2f}</span>
            </div>
        </div>

        <!-- CTA -->
        <div class="section" style="text-align: center;">
            <a href="{sheet_url}" class="btn">View Full Report</a>
            <div style="margin-top: 10px; font-size: 12px; color: #666;">
                Today's sync: {stats.get('items_synced', 0)} items updated
            </div>
        </div>

        <div class="footer">
            eBay Reseller Tracker - Automated Daily Sync
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

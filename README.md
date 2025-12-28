# eBay Reseller Tracker

A comprehensive Python-based system for tracking eBay reselling profitability. Automatically pulls data from eBay APIs, stores everything in Google Sheets for easy access, and calculates true profit per item.

## Features

- **Automatic Data Sync**: Pulls transactions, orders, and listing data from eBay APIs
- **Google Sheets Integration**: All data stored in an accessible spreadsheet
- **Profit Calculations**: True profit per item including COGS, fees, and shipping
- **Performance Metrics**: Track views, watchers, and listing quality
- **Dashboard**: Summary of business health with key metrics
- **Scheduled Runs**: GitHub Actions workflow for daily automated syncs

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/ebay-reseller-tracker.git
cd ebay-reseller-tracker
```

### 2. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Configure Environment

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values (see Configuration section below).

### 4. Run the Sync

```bash
python -m src.main
```

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `EBAY_USER_TOKEN` | Your eBay OAuth 2.0 User Token |
| `GOOGLE_CREDENTIALS_PATH` | Path to Google service account JSON file |
| `GOOGLE_SHEET_ID` | ID of your Google Sheet (from URL) |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EBAY_TRADING_TOKEN` | - | Trading API token for extended metrics |
| `GOOGLE_CREDENTIALS_JSON` | - | Base64-encoded credentials (for CI/CD) |
| `CREATE_NEW_SHEET` | `false` | Create new sheet if ID not provided |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING) |
| `TIMEZONE` | `America/New_York` | Timezone for dates |
| `SYNC_START_DATE` | `2025-11-01` | Start date for historical data |

## Setup Guide

### eBay API Setup

1. **Get Developer Account**: Sign up at [developer.ebay.com](https://developer.ebay.com)

2. **Create Application**:
   - Go to "My Account" → "Application Keys"
   - Create a new keyset for Production

3. **Get OAuth Token**:
   - Go to "User Tokens" in your app settings
   - Generate an OAuth User Token
   - Select these scopes:
     - `https://api.ebay.com/oauth/api_scope/sell.finances`
     - `https://api.ebay.com/oauth/api_scope/sell.fulfillment`
     - `https://api.ebay.com/oauth/api_scope/sell.inventory`
     - `https://api.ebay.com/oauth/api_scope/sell.analytics`

4. **Copy Token**: Save the User Token to your `.env` file

> **Note**: Tokens expire after ~18 months. The sync will warn you when refresh is needed.

### Google Sheets API Setup

1. **Create Google Cloud Project**:
   - Go to [console.cloud.google.com](https://console.cloud.google.com)
   - Create a new project

2. **Enable APIs**:
   - Enable "Google Sheets API"
   - Enable "Google Drive API"

3. **Create Service Account**:
   - Go to "IAM & Admin" → "Service Accounts"
   - Create a new service account
   - Download the JSON key file

4. **Share Your Sheet**:
   - Create a new Google Sheet (or use existing)
   - Share it with the service account email (found in the JSON file)
   - Give "Editor" access

5. **Get Sheet ID**:
   - Open your Google Sheet
   - Copy the ID from the URL: `docs.google.com/spreadsheets/d/{THIS_IS_THE_ID}/edit`

### GitHub Actions Setup

To run the sync automatically:

1. **Add Repository Secrets**:
   Go to Settings → Secrets and variables → Actions → New repository secret

   | Secret Name | Value |
   |-------------|-------|
   | `EBAY_USER_TOKEN` | Your eBay OAuth token |
   | `EBAY_TRADING_TOKEN` | (Optional) Trading API token |
   | `GOOGLE_CREDENTIALS_JSON` | Base64-encoded service account JSON* |
   | `GOOGLE_SHEET_ID` | Your Google Sheet ID |

   *To base64 encode: `base64 -w 0 credentials.json`

2. **Enable Workflow**:
   - Go to Actions tab
   - Enable workflows for this repository

The sync runs daily at 6 AM UTC (1 AM EST). You can also trigger manually.

## Google Sheets Structure

### Inventory Tab

The main tracking sheet with one row per listing:

| Column | Source | Description |
|--------|--------|-------------|
| Item ID | eBay | Unique listing identifier |
| Title | eBay | Listing title |
| COGS | Manual | What you paid for the item |
| Final Sale Price | eBay | What it sold for |
| Total Fees | Calculated | Sum of all eBay fees |
| Net Profit | Calculated | Your actual profit |
| ROI % | Calculated | Return on investment |
| Views | eBay | Hit count |
| Watchers | eBay | Watch count |
| ... | | (50+ columns total) |

### Expenses Tab

Track non-eBay business expenses:

| Column | Description |
|--------|-------------|
| Date | When expense occurred |
| Category | Supplies, Software, etc. |
| Amount | Cost |
| Tax Deductible | TRUE/FALSE |

### Dashboard Tab

Auto-calculated summary metrics:

- Total items listed/sold
- Sell-through rate
- Total revenue, fees, profit
- Average ROI and margin
- This month's performance
- Warning flags (stale inventory, losses)

### Metrics Log Tab

Daily snapshot for trend analysis.

## Manual Data Entry

Some fields need manual input:

1. **COGS (Cost of Goods Sold)**: Enter what you paid for each item
2. **Acquisition Date**: When you bought the item
3. **Acquisition Source**: Where you bought it (Goodwill, garage sale, etc.)
4. **Notes**: Your observations

These fields are preserved during sync and not overwritten.

## API Rate Limits

The sync respects eBay's API rate limits:
- 500 calls/minute (staying well under the 1000 limit)
- Automatic retries with exponential backoff
- Pagination for large result sets

## Troubleshooting

### "eBay token expired or invalid"

Your OAuth token has expired. To refresh:
1. Go to [developer.ebay.com](https://developer.ebay.com)
2. Navigate to your app's User Tokens
3. Generate a new token
4. Update your `.env` or GitHub secret

### "Spreadsheet not found"

Make sure you've:
1. Shared the sheet with your service account email
2. Used the correct Sheet ID
3. Given "Editor" access

### "Google credentials not configured"

Check that either:
- `GOOGLE_CREDENTIALS_PATH` points to a valid JSON file, or
- `GOOGLE_CREDENTIALS_JSON` contains valid base64-encoded JSON

### Rate limit errors

The sync includes rate limiting, but if you hit limits:
- Wait a few minutes and retry
- Check if other apps are using the same API credentials

## Development

### Running Tests

```bash
pytest
```

### Code Quality

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/
```

## Future Enhancements

- [ ] Automatic token refresh using refresh token flow
- [ ] Comp pricing tool (look up similar sold items)
- [ ] Photo quality scoring
- [ ] Automated relisting of ended items
- [ ] Notification system (Discord/email alerts)
- [ ] Mobile-friendly COGS input form
- [ ] Predictive model for "will this sell?"

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

Contributions welcome! Please open an issue first to discuss changes.

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/ebay-reseller-tracker/issues)
- **eBay API Docs**: [developer.ebay.com/docs](https://developer.ebay.com/docs)
- **Google Sheets API**: [developers.google.com/sheets](https://developers.google.com/sheets/api)

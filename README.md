# Smartlead Bounced Emails API

Fetches all bounced emails from the last 7 days from your Smartlead account.

## What It Does

- Fetches all campaigns from your Smartlead account
- Extracts bounced emails from the last 7 days
- Returns: email address, from email, email message, campaign ID, campaign name, sent time
- Runs automatically every day at 3 AM UTC
- Stores data in SQLite for quick retrieval

## Deployment on Railway

### Step 1: Get Your Smartlead API Key

1. Go to https://app.smartlead.ai/app/settings/profile
2. Copy your API key

### Step 2: Create New Railway Project

1. Go to https://railway.app
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Connect your GitHub account if not already connected
5. Select your repository

### Step 3: Configure Environment Variable

1. In Railway project settings, go to "Variables"
2. Add environment variable:
   - **Variable**: `SMARTLEAD_API_KEY`
   - **Value**: Your Smartlead API key from Step 1

### Step 4: Deploy

Railway will automatically:
- Detect the `Procfile`
- Install dependencies from `requirements.txt`
- Start the FastAPI application
- Assign a public URL

## API Endpoints

Once deployed, your Railway app will provide these endpoints:

### `GET /`
Health check
```bash
curl https://your-app.railway.app/
```

### `GET /bounced-emails`
Get bounced emails from last 7 days
```bash
curl https://your-app.railway.app/bounced-emails
```

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "email_address": "[email protected]",
      "from_email": "[email protected]",
      "email_message": "<p>Your email content</p>",
      "email_subject": "Subject line",
      "campaign_id": 12345,
      "campaign_name": "Campaign Name",
      "email_status": "bounced",
      "sent_time": "2024-12-08T10:30:00Z",
      "sequence_number": 1
    }
  ],
  "fetched_at": "2024-12-09T03:00:00",
  "total_bounced": 42
}
```

### `GET /refresh` or `POST /refresh`
Manually trigger data fetch
```bash
curl https://your-app.railway.app/refresh
```

### `GET /logs`
View fetch history (default: last 10 entries)
```bash
curl https://your-app.railway.app/logs?limit=20
```

### `GET /schedule-info`
View scheduled job information
```bash
curl https://your-app.railway.app/schedule-info
```

## Scheduled Updates

The service automatically fetches new data **daily at 3:00 AM UTC**.

To change the schedule, edit the cron expression in `bounced_emails.py`:
```python
CronTrigger(hour=3, minute=0)  # Change hour/minute as needed
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export SMARTLEAD_API_KEY="your_api_key_here"

# Run locally
uvicorn bounced_emails:app --reload

# Visit http://localhost:8000
```

## Files Structure

```
.
├── bounced_emails.py    # Main application
├── requirements.txt     # Python dependencies
├── Procfile            # Railway deployment config
├── .gitignore          # Ignored files
└── README.md           # This file
```

## Next Steps

Use the `/bounced-emails` endpoint in your automation workflows to:
- Sync with your CRM
- Trigger alerts for high bounce rates
- Remove bounced emails from your lists
- Generate bounce rate reports

## Support

The data includes all fields needed for analysis:
- Email addresses that bounced
- Which campaigns they came from
- Email content that was sent
- When they were sent
- Sequence number in the campaign

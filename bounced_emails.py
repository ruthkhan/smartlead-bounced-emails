from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import httpx
import sqlite3
import json
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize scheduler
scheduler = AsyncIOScheduler()

# Database setup
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('bounced_emails.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bounced_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            message TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

async def fetch_bounced_emails():
    """
    Fetch bounced emails from the last 7 days from SmartLead API.
    
    Returns:
    - email_address (from_email)
    - email_message
    - campaign_id
    - campaign_name
    - email_status (bounced)
    - sent_time
    """
    logger.info("Starting SmartLead bounced emails fetch job...")
    
    try:
        api_key = os.getenv('SMARTLEAD_API_KEY', 'YOUR_API_KEY_HERE')
        
        if api_key == 'YOUR_API_KEY_HERE':
            raise ValueError("Please set your SmartLead API key in the SMARTLEAD_API_KEY environment variable")
        
        base_url = "https://server.smartlead.ai/api/v1"
        
        # Calculate 7 days ago
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # ========================================
            # Step 1: Get all campaigns
            # ========================================
            logger.info("Fetching all campaigns...")
            url = f"{base_url}/campaigns?api_key={api_key}"
            response = await client.get(url)
            response.raise_for_status()
            campaigns = response.json()
            
            logger.info(f"Found {len(campaigns)} campaigns")
            
            # ========================================
            # Step 2: For each campaign, fetch bounced emails
            # ========================================
            all_bounced_emails = []
            
            for campaign in campaigns:
                campaign_id = campaign.get('id')
                campaign_name = campaign.get('name')
                
                logger.info(f"Fetching bounced emails for campaign: {campaign_name} (ID: {campaign_id})")
                
                # Fetch bounced emails with pagination
                offset = 0
                limit = 100
                
                while True:
                    url = f"{base_url}/campaigns/{campaign_id}/statistics"
                    params = {
                        'api_key': api_key,
                        'email_status': 'bounced',
                        'offset': offset,
                        'limit': limit
                    }
                    
                    try:
                        response = await client.get(url, params=params)
                        response.raise_for_status()
                        result = response.json()
                        
                        # Handle both array response and object with 'data' key
                        if isinstance(result, dict) and 'data' in result:
                            emails = result['data']
                        elif isinstance(result, list):
                            emails = result
                        else:
                            logger.warning(f"Unexpected response format for campaign {campaign_id}: {type(result)}")
                            break
                        
                        if not emails or len(emails) == 0:
                            break
                        
                        # Filter emails from last 7 days
                        for email in emails:
                            sent_time_str = email.get('sent_time')
                            
                            if not sent_time_str:
                                continue
                            
                            try:
                                # Parse sent_time
                                sent_time = datetime.fromisoformat(sent_time_str.replace('Z', '+00:00'))
                                
                                # Only include emails from last 7 days
                                if sent_time >= seven_days_ago:
                                    all_bounced_emails.append({
                                        'email_address': email.get('lead_email'),
                                        'from_email': email.get('from_email'),
                                        'email_message': email.get('email_message'),
                                        'email_subject': email.get('email_subject'),
                                        'campaign_id': campaign_id,
                                        'campaign_name': campaign_name,
                                        'email_status': 'bounced',
                                        'sent_time': sent_time_str,
                                        'sequence_number': email.get('sequence_number'),
                                        'is_bounced': email.get('is_bounced', True)
                                    })
                            except (ValueError, AttributeError) as e:
                                logger.warning(f"Could not parse sent_time: {sent_time_str} - {str(e)}")
                                continue
                        
                        # Check if we need to paginate
                        if len(emails) < limit:
                            break
                        
                        offset += limit
                        
                    except Exception as e:
                        logger.warning(f"Error fetching bounced emails for campaign {campaign_id}: {str(e)}")
                        break
                
                logger.info(f"Found {len([e for e in all_bounced_emails if e['campaign_id'] == campaign_id])} bounced emails in campaign {campaign_name}")
        
        logger.info(f"Total bounced emails from last 7 days: {len(all_bounced_emails)}")
        
        # Store in database
        conn = sqlite3.connect('bounced_emails.db')
        cursor = conn.cursor()
        
        # Clear old data (keep only latest)
        cursor.execute('DELETE FROM bounced_emails')
        
        # Insert new data
        cursor.execute(
            'INSERT INTO bounced_emails (data) VALUES (?)',
            (json.dumps(all_bounced_emails),)
        )
        
        # Log successful fetch
        cursor.execute(
            'INSERT INTO fetch_log (status, message) VALUES (?, ?)',
            ('success', f'Successfully fetched {len(all_bounced_emails)} bounced emails from {len(campaigns)} campaigns')
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Successfully stored {len(all_bounced_emails)} bounced emails")
        return {
            "status": "success",
            "total_campaigns": len(campaigns),
            "total_bounced_emails": len(all_bounced_emails),
            "date_range": f"Last 7 days (since {seven_days_ago.isoformat()})"
        }
        
    except Exception as e:
        logger.error(f"Error fetching bounced emails: {str(e)}")
        
        # Log error
        conn = sqlite3.connect('bounced_emails.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO fetch_log (status, message) VALUES (?, ?)',
            ('error', str(e))
        )
        conn.commit()
        conn.close()
        
        return {"status": "error", "message": str(e)}

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    
    try:
        # Schedule daily job at 3 AM UTC
        scheduler.add_job(
            fetch_bounced_emails,
            CronTrigger(hour=3, minute=0),
            id='daily_bounced_fetch',
            replace_existing=True
        )
        scheduler.start()
        logger.info("Scheduler started - daily job at 3:00 AM UTC")
    except Exception as e:
        logger.error(f"Scheduler initialization failed: {e}")
    
    yield
    
    # Shutdown
    try:
        scheduler.shutdown()
        logger.info("Scheduler shut down")
    except Exception as e:
        logger.error(f"Scheduler shutdown failed: {e}")

# Initialize FastAPI app
app = FastAPI(
    title="Smartlead Bounced Emails API",
    description="Fetch bounced emails from last 7 days",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "service": "Smartlead Bounced Emails API",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/bounced-emails")
async def get_bounced_emails():
    """
    Get bounced emails from the last 7 days.
    Returns: email_address, from_email, email_message, campaign_id, campaign_name, email_status
    """
    try:
        conn = sqlite3.connect('bounced_emails.db')
        cursor = conn.cursor()
        cursor.execute('SELECT data, created_at FROM bounced_emails ORDER BY created_at DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        
        if result:
            data = json.loads(result[0])
            return {
                "status": "success",
                "data": data,
                "fetched_at": result[1],
                "total_bounced": len(data) if isinstance(data, list) else 0
            }
        else:
            return {
                "status": "no_data",
                "message": "No data available yet. Run /refresh to fetch data."
            }
    
    except Exception as e:
        logger.error(f"Error retrieving bounced emails: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/refresh")
@app.post("/refresh")
async def manual_refresh():
    """
    Manually trigger bounced emails fetch.
    Works with both GET and POST requests.
    """
    result = await fetch_bounced_emails()
    return result

@app.get("/logs")
async def get_logs(limit: int = 10):
    """
    Get fetch logs to monitor the service.
    """
    try:
        conn = sqlite3.connect('bounced_emails.db')
        cursor = conn.cursor()
        cursor.execute(
            'SELECT status, message, fetched_at FROM fetch_log ORDER BY fetched_at DESC LIMIT ?',
            (limit,)
        )
        logs = cursor.fetchall()
        conn.close()
        
        return {
            "logs": [
                {
                    "status": log[0],
                    "message": log[1],
                    "timestamp": log[2]
                }
                for log in logs
            ]
        }
    
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schedule-info")
async def schedule_info():
    """Get information about scheduled jobs"""
    jobs = scheduler.get_jobs()
    return {
        "scheduled_jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
            for job in jobs
        ]
    }

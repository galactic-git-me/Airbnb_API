import asyncio
from datetime import datetime, timedelta
import functools
import json
import logging
import os
import random
import subprocess
import threading
import time
import pytz
import ipaddress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from rich.console import Console

console = Console()

# Setup logging to output to a file
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("log.log"),
        logging.StreamHandler()  # Still log to console as well
    ]
)
logger = logging.getLogger("Airbnb API")

# Hospitable IP Whitelisting
HOSPITABLE_IP_RANGE = ipaddress.ip_network("38.80.170.0/24")

def is_hospitable_ip(ip_str: str) -> bool:
    if ip_str in ["127.0.0.1", "::1", "localhost"]:
        return True
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip in HOSPITABLE_IP_RANGE or ip.is_private
    except ValueError:
        return False

app = FastAPI()

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '14mPOQyJn2SrVQVCq853Jw3VDYuwUymqsuy7m371svgU'
SHEET_NAME = 'API_RAWRAW'
SHEET_NAME_CRM = 'CRM - API'

# Load credentials from the service account JSON file or Environment Variable
SERVICE_ACCOUNT_FILE = 'serviceaccount.json'

if 'GOOGLE_APPLICATION_CREDENTIALS_JSON' in os.environ:
    # Use JSON string directly from Environment Variable
    creds_json = json.loads(os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON'])
    credentials = service_account.Credentials.from_service_account_info(
        creds_json, scopes=SCOPES)
else:
    # Fallback to file
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# Global sheet ID cache
sheet_id_cache = {}

async def get_sheet_id(sheet, spreadsheet_id, sheet_name):
    """Get the gid (sheetId) for a given sheet name, with caching"""
    if sheet_name in sheet_id_cache:
        return sheet_id_cache[sheet_name]
    
    try:
        metadata = await execute_with_backoff(sheet.get(spreadsheetId=spreadsheet_id))
        for s in metadata.get('sheets', []):
            props = s.get('properties', {})
            if props.get('title') == sheet_name:
                gid = props.get('sheetId')
                sheet_id_cache[sheet_name] = gid
                return gid
    except Exception as e:
        logger.error(f"Error fetching sheet ID for {sheet_name}: {e}")
    
    return None

async def sync_crm_dimensions(sheet, spreadsheet_id):
    """
    Ensures CRM - API has at least as many rows as API_RAWRAW by copying 
    down the last containing data row.
    """
    # Fetch data to determine row counts
    raw_values = await get_sheet_data_with_cache(sheet, spreadsheet_id, SHEET_NAME)
    crm_values = await get_sheet_data_with_cache(sheet, spreadsheet_id, SHEET_NAME_CRM)
    
    # We want to find the last row in CRM that actually has an ID in column A
    last_crm_data_row = 0
    for i, row in enumerate(crm_values):
        if row and len(row) > 0 and str(row[0]).strip():
            last_crm_data_row = i + 1
            
    raw_total_rows = len(raw_values)
    
    # If CRM is behind, copy down the last valid row
    if last_crm_data_row < raw_total_rows and last_crm_data_row > 0:
        logger.info(f"Syncing CRM rows: last data at {last_crm_data_row}, target {raw_total_rows}")
        
        crm_sheet_id = await get_sheet_id(sheet, spreadsheet_id, SHEET_NAME_CRM)
        if crm_sheet_id is None:
            logger.error(f"Could not find sheet ID for {SHEET_NAME_CRM}")
            return

        # Prepare batch update to copy formulas down
        # We copy from the last row with data to all subsequent rows up to raw_total_rows
        batch_update_request = {
            'requests': [
                {
                    'copyPaste': {
                        'source': {
                            'sheetId': crm_sheet_id,
                            'startRowIndex': last_crm_data_row - 1,
                            'endRowIndex': last_crm_data_row,
                            'startColumnIndex': 0,
                            'endColumnIndex': 50 # Cover typical CRM columns
                        },
                        'destination': {
                            'sheetId': crm_sheet_id,
                            'startRowIndex': last_crm_data_row,
                            'endRowIndex': raw_total_rows,
                            'startColumnIndex': 0,
                            'endColumnIndex': 50
                        },
                        'pasteType': 'PASTE_NORMAL'
                    }
                }
            ]
        }
        
        await execute_with_backoff(
            sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=batch_update_request)
        )
        logger.info(f"Successfully extended {SHEET_NAME_CRM} to row {raw_total_rows}")
        
        # Clear CRM cache so next read gets fresh data
        with sheet_cache['lock']:
            if SHEET_NAME_CRM in sheet_cache['sheets']:
                sheet_cache['sheets'][SHEET_NAME_CRM]['data'] = None
    else:
        logger.info(f"CRM rows already synced or no data found (CRM: {last_crm_data_row}, RAW: {raw_total_rows})")


# pylint: disable=no-member
service = build('sheets', 'v4', credentials=credentials)
sheet = service.spreadsheets()
# pylint: enable=no-member

# Global cache for spreadsheet data
sheet_cache = {
    'sheets': {},
    'lock': threading.Lock()
}

# Cache expiration time (in seconds)
CACHE_EXPIRATION = 300  # 5 minutes

# Middleware to log each request and wrap all values in double quotes
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log general request details
    client_host = request.client.host
    logger.info(f"Received request from {client_host}") 
    logger.info(f"Endpoint: {request.url.path}, Method: {request.method}")
    logger.info(f"Headers: {request.headers}")
    console.print(f"Received request from {client_host}")
    console.print(f"Endpoint: {request.url.path}, Method: {request.method}")
    console.print(f"Headers: {request.headers}")

    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            # Read and decode the request body
            body = await request.body()
            data = body.decode('utf-8')  # Decode bytes to string
            console.print(f"Raw Payload: {data}")
            logger.info(f"Payload: {data}")

            def convert_to_quoted_values(data):
                """
                Function to add double quotes around values in a string.
                Leaves empty values unchanged.
                
                :param data: String with unquoted values.
                :return: String with values wrapped in double quotes.
                """
                if data is not None and data.strip() != "":
                    return f'"{data}"'  # Add quotes around non-empty value
                else:
                    return '""'  # Keep empty value as an empty string with double quotes
            
            # converted_data = convert_to_quoted_values(data)

            # Replace escaped newline characters and parse the JSON string into a Python dictionary
            json_str = data.replace("\r\n", "")
            data_dict = json.loads(json_str)
            logger.info(f"Modified Payload: {data_dict}")
            console.print(f"Modified Payload: {data_dict}")


            # Overwrite the request body with the modified JSON
            request._json = data_dict
            request._body = json.dumps(data_dict).encode("utf-8")
        except Exception as e:
            logger.error(f"Failed to parse JSON payload: {e}")
            console.print(f"Failed to parse JSON payload: {e}")
            return JSONResponse(content={"error": "Invalid JSON payload"}, status_code=400)

    # Process the request and get the response
    response = await call_next(request)

    # Log response status
    logger.info(f"Response status: {response.status_code}")

    return response


@app.get("/health")
async def health(request: Request):
    return "ok", 200

@app.get("/api/test")
async def test(request: Request):
    return {"status": "success"}

@app.post("/api/new_booking")
async def new_booking(request: Request):
    data = await request.json()
    await process_request(data, '/new_booking')
    
    # Path to the script to run - using Windows path format
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "heartbeat.bat")
    
    # Check if the script exists before running it
    if os.path.exists(script_path):
        # Run the script in the background
        run_script_in_background(script_path)
    else:
        logger.error(f"Script not found: {script_path}")
    
    # Return success message with count of bookings processed
    booking_count = len(data) if isinstance(data, list) else 1
    return {"status": "success", "message": f"{booking_count} booking(s) processed."}

@app.post("/api/cancel_booking")
async def cancel_booking(request: Request):
    data = await request.json()
    await process_request(data, '/cancel_booking')
    return {"status": "success", "message": "Booking cancellation processed."}

@app.post("/api/updatepostbooking")
async def update_post_booking(request: Request):
    data = await request.json()
    await update_crm_api(data, 'AN')
    return {"status": "success", "message": "Post booking updated."}

@app.post("/api/updatewelcomepack")
async def update_welcome_pack(request: Request):
    data = await request.json()
    await update_crm_api(data, 'AO')
    return {"status": "success", "message": "Welcome pack updated."}

@app.post("/api/updatepoststay")
async def update_post_stay(request: Request):
    data = await request.json()
    await update_crm_api(data, 'AQ')
    return {"status": "success", "message": "Post stay updated."}

@app.post("/api/hospitable/webhook")
async def hospitable_webhook(request: Request):
    # Caddy sets X-Forwarded-For to the real client IP; fall back to direct client if missing
    forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host
    logger.info(f"Hospitable Webhook received from {client_ip} (raw client: {request.client.host})")
    
    if not is_hospitable_ip(client_ip):
        logger.warning(f"Unauthorized IP access attempt to Hospitable webhook: {client_ip}")
        return JSONResponse(content={"error": "Unauthorized IP"}, status_code=403)

    try:
        payload = await request.json()
        action = payload.get("action")
        res_data = payload.get("data", {})
        
        # Map Hospitable format to internal format
        internal_data = map_hospitable_to_internal(payload)
        
        if action == "reservation.created":
            await process_request(internal_data, '/new_booking')
            # Run heartbeat script for new bookings
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "heartbeat.bat")
            if os.path.exists(script_path):
                run_script_in_background(script_path)
                
        elif action == "reservation.changed":
            status = res_data.get("status", "")
            if status.lower() == "cancelled":
                await process_request(internal_data, '/cancel_booking')
            else:
                # Triggers for changed flow include status changes: Checkpoint, Pending, Accepted, Not accepted
                await process_request(internal_data, '/change_booking')
        else:
            logger.info(f"Unhandled action: {action}")
            
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing Hospitable webhook: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

def map_hospitable_to_internal(payload):
    res = payload.get("data", {})
    guest = res.get("guest", {})
    financials = res.get("financials", {})
    guest_financials = financials.get("guest", {})
    total_price = guest_financials.get("total_price", {})
    guests_counts = res.get("guests", {}) # Hospitable 'guests' count object
    
    # Combine names
    first_name = guest.get("first_name", "")
    last_name = guest.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    
    # Use platform_id for internal ID if available, otherwise UUID
    internal_id = res.get("platform_id") or res.get("id")
    
    return {
        "ID": internal_id,
        "GUEST:NAME": full_name,
        "GUEST:EMAIL": guest.get("email"),
        "GUEST:PHONE": guest.get("phone"),
        "INQUIRY:ARRIVE": res.get("arrival_date"),
        "INQUIRY:DEPART": res.get("departure_date"),
        "INQUIRY:BOOK_DATE": res.get("booking_date"),
        "INQUIRY:COST": total_price.get("formatted") or total_price.get("amount"),
        "INQUIRY:NIGHTS": res.get("nights"),
        "INQUIRY:ADULTS": guests_counts.get("adults"),
        "INQUIRY:CHILDREN": guests_counts.get("children"),
        "INQUIRY:CHANNEL": res.get("platform"),
        "INQUIRY:CHECK_IN": res.get("check_in"),
        "INQUIRY:CHECK_OUT": res.get("check_out"),
        # Additional fields
        "GUEST:COUNTRY": guest.get("country"),
    }


def run_script_in_background(script_path):
    """
    Run the given script in the background.

    Args:
    script_path (str): The path to the script to run.
    """
    try:
        # Start the script in the background
        subprocess.Popen([script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Script {script_path} is running in the background.")
    except Exception as e:
        print(f"An error occurred: {e}")


async def process_request(data, endpoint):
    ASCII_text = None
    # Get the current datetime in the required format
    current_datetime = datetime.now(pytz.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    
    # If data is a list, process each booking in the list
    if isinstance(data, list) and len(data) > 0:
        logger.info(f"Processing {len(data)} bookings")
        for booking in data:
            await process_single_booking(booking, endpoint, current_datetime, ASCII_text)
        return
    else:
        # Process a single booking
        await process_single_booking(data, endpoint, current_datetime, ASCII_text)


async def process_single_booking(data, endpoint, current_datetime, ASCII_text=None):
    """Process a single booking entry"""
    if endpoint == "/new_booking":
        status = "ok"
        ASCII_text = r"""
                                                                                                                                                                                      
b.             8 8 8888888888 `8.`888b                 ,8'           8 888888888o       ,o888888o.         ,o888888o.     8 8888     ,88'  8 8888 b.             8     ,o888888o.    
888o.          8 8 8888        `8.`888b               ,8'            8 8888    `88.  . 8888     `88.    . 8888     `88.   8 8888    ,88'   8 8888 888o.          8    8888     `88.  
Y88888o.       8 8 8888         `8.`888b             ,8'             8 8888     `88 ,8 8888       `8b  ,8 8888       `8b  8 8888   ,88'    8 8888 Y88888o.       8 ,8 8888       `8. 
.`Y888888o.    8 8 8888          `8.`888b     .b    ,8'              8 8888     ,88 88 8888        `8b 88 8888        `8b 8 8888  ,88'     8 8888 .`Y888888o.    8 88 8888           
8o. `Y888888o. 8 8 888888888888   `8.`888b    88b  ,8'               8 8888.   ,88' 88 8888         88 88 8888         88 8 8888 ,88'      8 8888 8o. `Y888888o. 8 88 8888           
8`Y8o. `Y88888o8 8 8888            `8.`888b .`888b,8'                8 8888888888   88 8888         88 88 8888         88 8 8888 88'       8 8888 8`Y8o. `Y88888o8 88 8888           
8   `Y8o. `Y8888 8 8888             `8.`888b8.`8888'                 8 8888    `88. 88 8888        ,8P 88 8888        ,8P 8 888888<        8 8888 8   `Y8o. `Y8888 88 8888   8888888 
8      `Y8o. `Y8 8 8888              `8.`888`8.`88'                  8 8888      88 `8 8888       ,8P  `8 8888       ,8P  8 8888 `Y8.      8 8888 8      `Y8o. `Y8 `8 8888       .8' 
8         `Y8o.` 8 8888               `8.`8' `8,`'                   8 8888    ,88'  ` 8888     ,88'    ` 8888     ,88'   8 8888   `Y8.    8 8888 8         `Y8o.`    8888     ,88'  
8            `Yo 8 888888888888        `8.`   `8'                    8 888888888P       `8888888P'         `8888888P'     8 8888     `Y8.  8 8888 8            `Yo     `8888888P'    
"""
    elif endpoint == "/cancel_booking":
        status = "cancelled by guest"
        ASCII_text = r"""
 ________  ________  ________   ________  _______   ___               ________  ________  ________  ___  __    ___  ________   ________     
|\   ____\|\   __  \|\   ___  \|\   ____\|\  ___ \ |\  \             |\   __  \|\   __  \|\   __  \|\  \|\  \ |\  \|\   ___  \|\   ____\    
\ \  \___|\ \  \|\  \ \  \\ \  \ \  \___|\ \   __/|\ \  \            \ \  \|\ /\ \  \|\  \ \  \|\  \ \  \/  /|\ \  \ \  \\ \  \ \  \___|    
 \ \  \    \ \   __  \ \  \\ \  \ \  \    \ \  \_|/_\ \  \            \ \   __  \ \  \\\  \ \  \\\  \ \   ___  \ \  \ \  \\ \  \ \  \  ___  
  \ \  \____\ \  \ \  \ \  \\ \  \ \  \____\ \  \_|\ \ \  \____        \ \  \|\  \ \  \\\  \ \  \\\  \ \  \\ \  \ \  \ \  \\ \  \ \  \|\  \ 
   \ \_______\ \__\ \__\ \__\\ \__\ \_______\ \_______\ \_______\       \ \_______\ \_______\ \_______\ \__\\ \__\ \__\ \__\\ \__\ \_______\
    \|_______|\|__|\|__|\|__| \|__|\|_______|\|_______|\|_______|        \|_______|\|_______|\|_______|\|__| \|__|\|__|\|__| \|__|\|_______|
                                                                                                                                             
                                                                                                                                             
                                                                                                                                             
"""
    elif endpoint == "/change_booking":
        status = "changed"
        ASCII_text = r"""
  ____ _   _    _    _   _  ____ _____    ____   ___   ___  _  _____ _   _  ____ 
 / ___| | | |  / \  | \ | |/ ___| ____|  | __ ) / _ \ / _ \| |/ /_ _| \ | |/ ___|
| |   | |_| | / _ \ |  \| | |  _|  _|    |  _ \| | | | | | | ' / | ||  \| | |  _ 
| |___|  _  |/ ___ \| |\  | |_| | |___   | |_) | |_| | |_| | . \ | || |\  | |_| |
 \____|_| |_/_/   \_\_| \_|\____|_____|  |____/ \___/ \___/|_|\_\___|_| \_|\____|
"""
    if ASCII_text and (not isinstance(data, list) or data is data[0]):
        console.print(ASCII_text)
        logging.info(ASCII_text)
    
    # Format dates and cost values
    arrive_date = format_date(data.get("INQUIRY:ARRIVE"))
    depart_date = format_date(data.get("INQUIRY:DEPART"))
    book_date = format_date(data.get("INQUIRY:BOOK_DATE"))
    cost = format_cost(extract_inquiry_cost(data))
        
    # Prepare the row data with the JSON payload as a whole and split fields
    row_data = [
        data.get("ID"),
        current_datetime,  # DateTime
        status,  # Endpoint
        str(data),  # JSON payload (whole JSON as a string)
        data.get("GUEST:NAME"),
        data.get("GUEST:EMAIL"),
        data.get("GUEST:PHONE"),
        data.get("GUEST:SPOUSE"),
        data.get("GUEST:BIRTHDAY"),
        data.get("GUEST:SOURCE"),
        data.get("GUEST:ADDRESS"),
        data.get("GUEST:HOBBY"),
        arrive_date,  # Formatted arrive date
        data.get("INQUIRY:CHECK_IN"),
        depart_date,  # Formatted depart date
        data.get("INQUIRY:CHECK_OUT"),
        data.get("INQUIRY:NIGHTS"),
        data.get("INQUIRY:ADULTS"),
        data.get("INQUIRY:CHILDREN"),
        data.get("INQUIRY:CHANNEL"),
        book_date,  # Formatted book date
        cost,  # Formatted cost
        data.get("GUEST:COUNTRY"),
        current_datetime,  # Timestamp
        endpoint  # Endpoint (again, if needed)
    ]

    await update_google_sheets(sheet, SPREADSHEET_ID, SHEET_NAME, data, row_data)


async def update_google_sheets(sheet, SPREADSHEET_ID, SHEET_NAME, data, row_data, max_retries=10):
    """Update Google Sheets with retry logic for rate limiting and caching"""
    retry_count = 0
    base_delay = 2  # Start with a 2-second delay
    
    # Extract secondary identifier fields for deduplication
    new_id = data.get('ID')
    new_name = str(data.get("GUEST:NAME", "") or "").strip().lower()
    new_arrive = str(row_data[12] or "").strip() # Formatted arrive date (Column M)
    new_cost = str(row_data[21] or "").strip()   # Formatted cost (Column V)
    
    while retry_count < max_retries:
        try:
            # Use cached data if available and not expired
            values = await get_sheet_data_with_cache(sheet, SPREADSHEET_ID, SHEET_NAME)
            
            # Check if ID already exists
            row_index = -1
            for i, row in enumerate(values):
                if not row:
                    continue
                    
                # 1. Primary ID Check
                if row[0] == new_id:
                    row_index = i
                    break
                    
                # 2. Secondary Deduplication Check
                if len(row) > 4 and new_name:
                    row_name = str(row[4] or "").strip().lower()
                    
                    if row_name == new_name:
                        row_index = i
                        logger.info(f"Duplicate booking found via secondary check: '{new_name}' (Overwriting old ID: {row[0]})")
                        
                        # Use the old ID to prevent altering existing row linkage or ID integrity
                        row_data[0] = row[0]
                        break
                    
            if row_index >= 0:
                # If found, update the existing row with exponential backoff
                await execute_with_backoff(
                    sheet.values().update(
                        spreadsheetId=SPREADSHEET_ID,
                        range=f'{SHEET_NAME}!A{row_index + 1}:Y{row_index + 1}',
                        valueInputOption='RAW',
                        body={
                            'values': [row_data]
                        }
                    ),
                    max_retries=max_retries,
                    base_delay=base_delay,
                    retry_count=retry_count
                )
                logger.info(f"Row {row_index + 1} updated successfully.")
                return
            
            # If no match is found, append a new row with exponential backoff
            await execute_with_backoff(
                sheet.values().append(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f'{SHEET_NAME}!A:Y',
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body={
                        'values': [row_data]
                    }
                ),
                max_retries=max_retries,
                base_delay=base_delay,
                retry_count=retry_count
            )
            
            # Update cache with new row
            with sheet_cache['lock']:
                if SHEET_NAME in sheet_cache['sheets'] and sheet_cache['sheets'][SHEET_NAME]['data'] is not None:
                    # Append up to column V so future secondary checks during this run can verify against it
                    sheet_cache['sheets'][SHEET_NAME]['data'].append(row_data[:22])
            
            logger.info("New row added successfully.")
            
            # Auto-sync CRM - API rows if needed
            try:
                await sync_crm_dimensions(sheet, SPREADSHEET_ID)
            except Exception as sync_e:
                logger.error(f"Failed to sync CRM dimensions: {sync_e}")
                # Don't fail the whole request if sync fails, but log it
                
            return
            
        except Exception as e:
            if "429" in str(e) and "RATE_LIMIT_EXCEEDED" in str(e):
                # This is a rate limit error, implement exponential backoff
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Failed to update Google Sheets after {max_retries} retries: {e}")
                    raise e
                
                # Calculate delay with exponential backoff and jitter
                delay = base_delay * (2 ** (retry_count - 1)) + random.uniform(0, 1)
                logger.warning(f"Rate limit exceeded. Retrying in {delay:.2f} seconds (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                # If it's not a rate limit error, raise it immediately
                logger.error(f"Failed to update Google Sheets: {e}")
                raise e


async def execute_with_backoff(request, max_retries=10, base_delay=2, retry_count=0):
    """Execute a Google Sheets API request with exponential backoff"""
    current_retry = retry_count
    
    while current_retry < max_retries:
        try:
            return request.execute()
        except Exception as e:
            if "429" in str(e) and "RATE_LIMIT_EXCEEDED" in str(e):
                current_retry += 1
                if current_retry >= max_retries:
                    logger.error(f"Failed after {max_retries} retries: {e}")
                    raise e
                
                delay = base_delay * (2 ** (current_retry - 1)) + random.uniform(0, 1)
                logger.warning(f"Rate limit exceeded in execute_with_backoff. Retrying in {delay:.2f} seconds (attempt {current_retry}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                raise e


async def get_sheet_data_with_cache(sheet, SPREADSHEET_ID, SHEET_NAME):
    """Get sheet data with caching to reduce API calls"""
    with sheet_cache['lock']:
        current_time = datetime.now()
        
        # Initialize sub-cache for this sheet if not exists
        if SHEET_NAME not in sheet_cache['sheets']:
             sheet_cache['sheets'][SHEET_NAME] = {'data': None, 'last_updated': None}
        
        cache_entry = sheet_cache['sheets'][SHEET_NAME]

        # If cache is valid, return cached data
        if (cache_entry['data'] is not None and 
            cache_entry['last_updated'] is not None and 
            current_time - cache_entry['last_updated'] < timedelta(seconds=CACHE_EXPIRATION)):
            logger.info(f"Using cached sheet data for {SHEET_NAME}")
            return cache_entry['data']
    
    # Cache is invalid or expired, fetch new data with backoff
    try:
        logger.info(f"Fetching fresh sheet data for {SHEET_NAME}")
        result = await execute_with_backoff(
            sheet.values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=f'{SHEET_NAME}!A:V'  # We need up to column V for deduplication checks
            )
        )
        
        values = result.get('values', [])
        
        # Update cache
        with sheet_cache['lock']:
            sheet_cache['sheets'][SHEET_NAME]['data'] = values
            sheet_cache['sheets'][SHEET_NAME]['last_updated'] = current_time
            
        return values
        
    except Exception as e:
        logger.error(f"Failed to fetch sheet data for {SHEET_NAME}: {e}")
        
        # If cache exists but is expired, use it anyway as fallback
        with sheet_cache['lock']:
             if SHEET_NAME in sheet_cache['sheets'] and sheet_cache['sheets'][SHEET_NAME]['data'] is not None:
                logger.warning(f"Using expired cache as fallback for {SHEET_NAME}")
                return sheet_cache['sheets'][SHEET_NAME]['data']
        
        # No cache available, re-raise the exception
        raise e


async def update_crm_api(data, column):
    # Get the current date in the required format
    current_date = datetime.now().strftime('%Y-%m-%d')

    # Extract the ID from the payload
    booking_id = data.get("ID")
    
    if not booking_id:
        logger.error("ID field is missing in the payload")
        return

    try:
        # Fetch existing data from the CRM - API sheet with caching
        values = await get_sheet_data_with_cache(sheet, SPREADSHEET_ID, SHEET_NAME_CRM)

        # Check if the ID exists in column A
        for i, row in enumerate(values):
            if row and row[0] == booking_id:
                # If found, update the specific column with the current date
                await execute_with_backoff(
                    sheet.values().update(
                        spreadsheetId=SPREADSHEET_ID,
                        range=f'{SHEET_NAME_CRM}!{column}{i + 1}',
                        valueInputOption='RAW',
                        body={
                            'values': [[current_date]]
                        }
                    )
                )
                logger.info(f"Row {i + 1} in column {column} updated with date {current_date}.")
                return

        logger.error(f"ID {booking_id} not found in CRM - API sheet.")
    
    except Exception as e:
        logger.error(f"Failed to update CRM API sheet: {e}")
        raise e  # Re-raise the exception to let FastAPI handle it


def format_date(date_str):
    """Format date strings to 'Sat Feb 22, 2025' format"""
    if not date_str:
        return date_str
    
    try:
        # Handle different date formats
        if "," in date_str:
            # Format like "Sunday, Dec. 29 2024"
            parts = date_str.split(',')
            if len(parts) == 2:
                day_of_week = parts[0].strip()
                rest = parts[1].strip()
                
                # Handle formats with periods in month abbreviation
                rest = rest.replace(".", "")
                
                # Parse the date
                try:
                    date_obj = datetime.strptime(rest, "%b %d %Y")
                    return f"{day_of_week[:3]} {date_obj.strftime('%b %d, %Y')}"
                except ValueError:
                    # Try another format
                    try:
                        # For formats like "17 Apr, 2025"
                        full_date = date_str.replace(",", "").strip()
                        date_obj = datetime.strptime(full_date, "%d %b %Y")
                        return date_obj.strftime("%a %b %d, %Y")
                    except ValueError:
                        pass
        
        elif date_str.count(" at ") > 0:
            # Format like "Mon Dec 30 2024 at 09:39:29"
            date_part = date_str.split(" at ")[0]
            date_obj = datetime.strptime(date_part, "%a %b %d %Y")
            return date_obj.strftime("%a %b %d, %Y")
        
        # Handle formats like "17 Apr, 2025" or "17 Apr 2025" or "17 Apr 2025"
        if date_str.count(" ") >= 2:
            # Remove any commas
            clean_date = date_str.replace(",", "").strip()
            
            # Try different date formats
            formats_to_try = [
                "%d %b %Y",      # 17 Apr 2025
                "%d %B %Y",      # 17 April 2025
                "%d %b, %Y",     # 17 Apr, 2025
                "%d %B, %Y"      # 17 April, 2025
            ]
            
            for fmt in formats_to_try:
                try:
                    date_obj = datetime.strptime(clean_date, fmt)
                    return date_obj.strftime("%a %b %d, %Y")
                except ValueError:
                    continue
        
    except Exception as e:
        logger.error(f"Error formatting date '{date_str}': {e}")
        return date_str
    
    return date_str


def format_cost(cost_str):
    """Format cost strings to have only '£' at the start without 'GBP' at the end"""
    if not cost_str:
        return cost_str
    
    try:
        if not isinstance(cost_str, str):
            cost_str = str(cost_str)
        # Fix common encoding artifacts for GBP
        cost_str = cost_str.replace("Â£", "£")
        if "�" in cost_str and "£" not in cost_str:
            cost_str = cost_str.replace("�", "£")
        # Remove 'GBP' if present
        cost_str = cost_str.replace("GBP", "").strip()
        
        # Ensure there's a pound sign
        if not cost_str.startswith("£"):
            cost_str = f"£{cost_str}"
        
        return cost_str
    except Exception as e:
        logger.error(f"Error formatting cost '{cost_str}': {e}")
        return cost_str


def extract_inquiry_cost(data):
    """Find a cost/price field even if key casing/spacing varies"""
    if not isinstance(data, dict):
        return None

    cost_keys = [
        "INQUIRY:COST",
        "INQUIRY:PRICE",
        "INQUIRY:TOTAL",
        "INQUIRY:AMOUNT",
        "INQUIERY:COST",
        "COST",
        "PRICE",
        "TOTAL",
        "AMOUNT",
    ]

    for key in cost_keys:
        value = data.get(key)
        if value not in (None, ""):
            return value

    normalized = {str(key).strip().upper(): key for key in data.keys()}
    for key in cost_keys:
        normalized_key = key.strip().upper()
        if normalized_key in normalized:
            value = data.get(normalized[normalized_key])
            if value not in (None, ""):
                return value

    return data.get("INQUIRY:COST")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7777)
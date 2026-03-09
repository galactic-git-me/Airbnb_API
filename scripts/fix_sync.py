
import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FixSync")

# Configuration (copied from main.py)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '14mPOQyJn2SrVQVCq853Jw3VDYuwUymqsuy7m371svgU'
SHEET_NAME = 'API_RAWRAW'
SHEET_NAME_CRM = 'CRM - API'
SERVICE_ACCOUNT_FILE = '/home/mac/Airbnb_API/serviceaccount.json'

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)
sheet = service.spreadsheets()

# Mocking the backoff and cache logic from main.py for this script
async def execute_with_backoff(request):
    return request.execute()

async def get_sheet_data(sheet, spreadsheet_id, sheet_name):
    result = sheet.values().get(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet_name}!A:V'
    ).execute()
    return result.get('values', [])

async def get_sheet_id(sheet, spreadsheet_id, sheet_name):
    metadata = sheet.get(spreadsheetId=spreadsheet_id).execute()
    for s in metadata.get('sheets', []):
        props = s.get('properties', {})
        if props.get('title') == sheet_name:
            return props.get('sheetId')
    return None

async def sync():
    print(f"Starting sync for {SPREADSHEET_ID}...")
    
    raw_values = await get_sheet_data(sheet, SPREADSHEET_ID, SHEET_NAME)
    crm_values = await get_sheet_data(sheet, SPREADSHEET_ID, SHEET_NAME_CRM)
    
    last_crm_data_row = 0
    for i, row in enumerate(crm_values):
        if row and len(row) > 0 and str(row[0]).strip():
            last_crm_data_row = i + 1
            
    raw_total_rows = len(raw_values)
    
    print(f"RAW rows: {raw_total_rows}")
    print(f"CRM last data row: {last_crm_data_row}")
    
    if last_crm_data_row < raw_total_rows:
        print(f"Syncing: Copying row {last_crm_data_row} down to {raw_total_rows}...")
        crm_sheet_id = await get_sheet_id(sheet, SPREADSHEET_ID, SHEET_NAME_CRM)
        
        batch_update_request = {
            'requests': [
                {
                    'copyPaste': {
                        'source': {
                            'sheetId': crm_sheet_id,
                            'startRowIndex': last_crm_data_row - 1,
                            'endRowIndex': last_crm_data_row,
                            'startColumnIndex': 0,
                            'endColumnIndex': 50
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
        
        sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body=batch_update_request).execute()
        print("Success!")
    else:
        print("No sync needed.")

if __name__ == "__main__":
    asyncio.run(sync())

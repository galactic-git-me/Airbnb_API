import os
import base64
from getpass import getpass
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def search_messages(service, query):
    try:
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        return messages
    except Exception as error:
        print(f"An error occurred: {error}")
        return []

def get_message_content(service, msg_id):
    try:
        message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        payload = message.get('payload', {})
        parts = payload.get('parts', [])
        
        body = ""
        if 'parts' in payload:
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8')
        elif 'body' in payload:
            data = payload['body'].get('data')
            if data:
                body = base64.urlsafe_b64decode(data).decode('utf-8')
                
        return body
    except Exception as error:
        print(f"An error occurred: {error}")
        return None

def main():
    if not os.path.exists('credentials.json'):
        print("Error: credentials.json not found in the current directory.")
        print("Please download it from Google Cloud Console.")
        return

    service = get_gmail_service()
    
    # Search query
    query = 'subject:"Reservation confirmed" OR "Reservation confirmed" after:2025/12/01'
    print(f"Searching for: {query}")
    
    messages = search_messages(service, query)
    print(f"Found {len(messages)} messages.")
    
    for msg in messages:
        content = get_message_content(service, msg['id'])
        if content:
            print("--- Message ---")
            print(content[:500] + "..." if len(content) > 500 else content)
            print("-" * 20)

if __name__ == '__main__':
    main()

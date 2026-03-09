import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

PAT = os.getenv("PAT")
BASE_URL = "https://public.api.hospitable.com/v2"
WEBHOOK_URL = "http://localhost:7777/api/hospitable/webhook"

HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def get_properties():
    """Fetch all properties to get their UUIDs."""
    print("Fetching properties...")
    url = f"{BASE_URL}/properties"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return [p["id"] for p in data.get("data", [])]

def get_reservations(property_ids, start_date, end_date):
    """Fetch reservations for the given properties and date range."""
    print(f"Fetching reservations from {start_date} to {end_date}...")
    url = f"{BASE_URL}/reservations"
    all_reservations = []
    
    for prop_id in property_ids:
        params = {
            "properties[]": prop_id,
            "start_date": start_date,
            "end_date": end_date,
            "date_query": "checkin"
        }
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 200:
            reservations = response.json().get("data", [])
            all_reservations.extend(reservations)
            print(f" Found {len(reservations)} reservations for property {prop_id}")
        else:
            print(f" Error fetching reservations for property {prop_id}: {response.status_code}")
            
    return all_reservations

def simulate_webhook(reservation):
    """Simulate a Hospitable webhook call using the reservation data."""
    payload = {
        "action": "reservation.created",
        "data": reservation
    }
    try:
        # Note: This requires main.py to be running and accesible.
        # We use localhost here assuming the user runs it on the same machine.
        response = requests.post(WEBHOOK_URL, json=payload)
        if response.status_code == 200:
            print(f" Successfully processed reservation {reservation.get('id')}")
        else:
            print(f" Failed to process reservation {reservation.get('id')}: {response.status_code} - {response.text}")
    except Exception as e:
        print(f" Error connecting to webhook: {e}")

def main():
    print("=== Hospitable Data Retrieval & Processing ===")
    
    if not PAT:
        print("Error: PAT not found in .env file.")
        return

    start_date = input("Enter start date (YYYY-MM-DD): ").strip()
    end_date = input("Enter end date (YYYY-MM-DD): ").strip()
    
    try:
        # Validate date format
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        print("Error: Invalid date format. Use YYYY-MM-DD.")
        return

    try:
        property_ids = get_properties()
        if not property_ids:
            print("No properties found.")
            return
            
        reservations = get_reservations(property_ids, start_date, end_date)
        print(f"\nTotal reservations found: {len(reservations)}")
        
        if not reservations:
            print("No reservations to process.")
            return

        proceed = input(f"Do you want to process {len(reservations)} reservations via webhook? (y/n): ").strip().lower()
        if proceed == 'y':
            for res in reservations:
                simulate_webhook(res)
            print("\nProcessing complete.")
        else:
            print("Processing cancelled.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()

import os
import json
import requests
from datetime import datetime
import pytz
from requests_oauthlib import OAuth1Session
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"
# File to store the previous state
PREVIOUS_STATE_FILE = "previous_state.json"

# Twitter API credentials
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")

def get_current_list():
    response = requests.get(CONSOLIDATED_LIST_URL)
    return response.json()

def load_previous_state():
    if os.path.exists(PREVIOUS_STATE_FILE):
        with open(PREVIOUS_STATE_FILE, 'r') as f:
            return json.load(f)
    return None

def save_current_state(current_state):
    with open(PREVIOUS_STATE_FILE, 'w') as f:
        json.dump(current_state, f)

def compare_lists(previous, current):
    previous_names = set(item['name'] for item in previous['results'])
    current_names = set(item['name'] for item in current['results'])
    
    added = current_names - previous_names
    removed = previous_names - current_names
    
    return added, removed

def send_tweet(message):
    payload = {"text": message}

    # Make the request
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=ACCESS_TOKEN_SECRET,
    )

    # Making the request
    response = oauth.post(
        "https://api.twitter.com/2/tweets",
        json=payload,
    )

    if response.status_code != 201:
        raise Exception(
            f"Request returned an error: {response.status_code} {response.text}"
        )

    print(f"Tweet sent successfully: {message}")
    print(f"Response code: {response.status_code}")
    json_response = response.json()
    print(json.dumps(json_response, indent=4, sort_keys=True))

def check_for_updates():
    print(f"Checking for updates at {datetime.now()}")
    
    current_list = get_current_list()
    previous_list = load_previous_state()
    
    if previous_list is None:
        save_current_state(current_list)
        print("Initial state saved. No comparison made.")
        return
    
    added, removed = compare_lists(previous_list, current_list)
    
    if added or removed:
        message = "Consolidated List Update:\n"
        
        if added:
            message += "Added: " + ", ".join(added) + "\n"
        if removed:
            message += "Removed: " + ", ".join(removed)
        
        try:
            send_tweet(message)
        except Exception as e:
            print(f"Error sending tweet: {str(e)}")
        
        save_current_state(current_list)
    else:
        print("No changes detected.")

def main():
    # Run immediately
    print("Running initial check...")
    check_for_updates()

    # Schedule daily run at 1 PM Eastern Time
    scheduler = BlockingScheduler()
    eastern = pytz.timezone('US/Eastern')
    scheduler.add_job(
        check_for_updates,
        CronTrigger(hour=13, minute=0, timezone=eastern),
        id='daily_check',
        name='Daily check at 1 PM Eastern Time'
    )

    print("Scheduler started. Next run scheduled for 1 PM Eastern Time.")
    scheduler.start()

if __name__ == "__main__":
    main()

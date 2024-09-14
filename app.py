import os
import json
import requests
from datetime import datetime
import pytz
import tweepy
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"
# File to store the previous state
PREVIOUS_STATE_FILE = "previous_state.json"

# Twitter API credentials
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

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
    auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
    auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)
    api = tweepy.API(auth)
    
    try:
        api.update_status(message)
        print(f"Tweet sent successfully: {message}")
    except tweepy.errors.TweepError as e:
        print(f"Error sending tweet: {str(e)}")

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

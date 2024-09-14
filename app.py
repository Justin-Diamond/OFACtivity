import os
import json
import requests
from datetime import datetime
from requests_oauthlib import OAuth1Session
from collections import defaultdict

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
    previous_items = {item['name']: item for item in previous['results']}
    current_items = {item['name']: item for item in current['results']}
    
    added = defaultdict(list)
    removed = defaultdict(list)
    
    for name, item in current_items.items():
        if name not in previous_items:
            added[item['source']].append(item['name'])
    
    for name, item in previous_items.items():
        if name not in current_items:
            removed[item['source']].append(item['name'])
    
    return added, removed

def send_tweet(message):
    payload = {"text": message}
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=ACCESS_TOKEN_SECRET,
    )
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

def format_changes(changes, action):
    messages = []
    for source, names in changes.items():
        if len(names) == 1:
            messages.append(f"{source} {action} {names[0]}")
        else:
            names_str = ", ".join(names[:-1]) + f" and {names[-1]}"
            messages.append(f"{source} {action} {names_str}")
    return messages

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
        messages = format_changes(added, "added")
        messages.extend(format_changes(removed, "removed"))
        
        # Join all messages, but ensure we don't exceed Twitter's character limit
        full_message = " | ".join(messages)
        if len(full_message) > 280:
            full_message = full_message[:277] + "..."
        
        try:
            send_tweet(full_message)
        except Exception as e:
            print(f"Error sending tweet: {str(e)}")
        
        save_current_state(current_list)
    else:
        print("No changes detected.")

if __name__ == "__main__":
    check_for_updates()

import os
import json
import requests
from requests_oauthlib import OAuth1Session
from collections import defaultdict
import redis

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"

# Redis setup
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(redis_url)

# Twitter API credentials
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")

def check_credentials():
    credentials = {
        "CONSUMER_KEY": CONSUMER_KEY,
        "CONSUMER_SECRET": CONSUMER_SECRET,
        "ACCESS_TOKEN": ACCESS_TOKEN,
        "ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET
    }
    
    for key, value in credentials.items():
        if value:
            print(f"{key}: {value[:5]}...{value[-5:]} (Length: {len(value)})")
        else:
            print(f"{key}: Not set")

def get_current_list():
    response = requests.get(CONSOLIDATED_LIST_URL)
    return response.json()

def load_previous_state():
    state = redis_client.get('previous_state')
    if state:
        return json.loads(state)
    return None

def save_current_state(current_state):
    redis_client.set('previous_state', json.dumps(current_state))

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

def simulate_change(data):
    data['results'].append({
        'name': 'Test McTestFace',
        'source': 'Test Source'
    })
    return data

def main():
    print("Checking Twitter API credentials:")
    check_credentials()
    
    try:
        # First run: save current state
        current_list = get_current_list()
        save_current_state(current_list)
        print("Initial state saved to Redis")

        # Simulate a change
        modified_list = simulate_change(current_list)
        print("Simulated change: Added 'Test McTestFace' to the list")

        # Compare and tweet
        previous_list = load_previous_state()
        added, removed = compare_lists(previous_list, modified_list)

        if added or removed:
            messages = format_changes(added, "added")
            messages.extend(format_changes(removed, "removed"))
            
            full_message = " | ".join(messages)
            if len(full_message) > 280:
                full_message = full_message[:277] + "..."
            
            send_tweet(full_message)
        else:
            print("No changes detected (this shouldn't happen in this test)")

    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()

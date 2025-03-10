import os
import json
import requests
from datetime import datetime
from requests_oauthlib import OAuth1Session
from collections import defaultdict
import redis
from atproto import Client  # Bluesky client library

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"

# Redis setup
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.Redis.from_url(
    redis_url,
    ssl_cert_reqs='none'
)

# Twitter API credentials
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")

# Bluesky API credentials
BLUESKY_USERNAME = os.environ.get("BLUESKY_USERNAME")
BLUESKY_PASSWORD = os.environ.get("BLUESKY_PASSWORD")

# Test Redis connection
def test_redis_connection():
    try:
        redis_client.ping()
        print("Successfully connected to Redis!")
    except Exception as e:
        print(f"Redis connection error: {e}")

def get_current_list():
    response = requests.get(CONSOLIDATED_LIST_URL)
    full_data = response.json()
    # Extract only sources and names
    simplified_data = [{'source': item['source'], 'name': item['name']} for item in full_data['results']]
    return simplified_data

def load_previous_state():
    state = redis_client.get('previous_state')
    if state:
        return json.loads(state)
    return None

def save_current_state(current_state):
    redis_client.set('previous_state', json.dumps(current_state))

def compare_lists(previous, current):
    previous_items = {item['name']: item['source'] for item in previous}
    current_items = {item['name']: item['source'] for item in current}
    
    added = defaultdict(list)
    removed = defaultdict(list)
    
    for name, source in current_items.items():
        if name not in previous_items:
            added[source].append(name)
    
    for name, source in previous_items.items():
        if name not in current_items:
            removed[source].append(name)
    
    return added, removed

def send_tweet(message, in_reply_to_id=None):
    payload = {"text": message}
    if in_reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": in_reply_to_id}
    
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
    json_response = response.json()
    return json_response['data']['id']

def post_to_bluesky_thread(messages):
    """
    Posts a series of messages as a thread on Bluesky.
    
    :param messages: List of strings to be posted as a thread.
    """
    try:
        client = Client()
        client.login(BLUESKY_USERNAME, BLUESKY_PASSWORD)
        
        previous_post_uri = None
        for message in messages:
            response = client.com.atproto.repo.create_record(
                repo=BLUESKY_USERNAME,
                collection="app.bsky.feed.post",
                record={
                    "text": message,
                    "createdAt": datetime.now().isoformat(),
                    "reply": {"root": previous_post_uri, "parent": previous_post_uri} if previous_post_uri else None,
                },
            )
            previous_post_uri = response.get("uri")
        
        print("Thread posted successfully on Bluesky!")
    except Exception as e:
        print(f"Error posting to Bluesky: {e}")

def format_changes(changes, action):
    messages = []
    for source, names in changes.items():
        if len(names) == 1:
            messages.append(f"{source} {action}: {names[0]}")
        else:
            names_str = ", and ".join(names)
            messages.append(f"{source} {action}: {names_str}")
    return messages

def split_message(message, max_length=280):
    words = message.split()
    chunks = []
    current_chunk = []

    for word in words:
        if len(" ".join(current_chunk + [word])) <= max_length:
            current_chunk.append(word)
        else:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

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
        
        full_message = " | ".join(messages)
        message_chunks = split_message(full_message)
        
        try:
            # Post to Twitter
            previous_tweet_id = None
            for i, chunk in enumerate(message_chunks):
                if i == 0:
                    tweet_id = send_tweet(chunk)
                else:
                    tweet_id = send_tweet(chunk, in_reply_to_id=previous_tweet_id)
                previous_tweet_id = tweet_id
            
            # Post to Bluesky
            post_to_bluesky_thread(message_chunks)
        except Exception as e:
            print(f"Error posting messages: {str(e)}")
        
        save_current_state(current_list)
    else:
        print("No changes detected.")

if __name__ == "__main__":
    check_for_updates()

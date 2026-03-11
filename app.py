import os
import json
import requests
from datetime import datetime
from requests_oauthlib import OAuth1Session
from collections import defaultdict
import redis
from openai import OpenAI
import ssl
import time

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"

# Redis setup
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Create SSL context that doesn't verify certificates (for Heroku Redis)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

redis_client = redis.from_url(
    redis_url,
    ssl_cert_reqs=None,
    ssl_ca_certs=None,
    ssl_check_hostname=False
)

# Twitter API credentials
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")

# Kimi API credentials (US/international endpoint)
KIMI_API_KEY = os.environ.get("KIMI_API_KEY")
KIMI_BASE_URL = "https://api.moonshot.ai/v1"

# Production safeguards
MAX_FOLLOW_UPS_PER_RUN = 5  # Prevent spam if batch sanctions drop
RATE_LIMIT_DELAY = 2  # Seconds between tweets to avoid rate limits

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

def get_sanctions_context_with_kimi(name, source):
    """
    Uses Kimi API with web search to get structured context about a sanctioned party.
    Kimi researches the entity using authoritative sources and provides structured context.
    Returns None only if Kimi cannot find any verified information.
    """
    try:
        client = OpenAI(
            api_key=KIMI_API_KEY,
            base_url=KIMI_BASE_URL
        )
        
        messages = [
            {
                "role": "system",
                "content": """You are a sanctions research specialist. Use web search to find official information from OFAC, Treasury.gov, BIS, and government sources.

CRITICAL RULES:
1. Output ONLY the final answer. Never output search queries, thinking process, or phrases like "I'll search" or "Let me find"
2. If you cannot find verified information, output exactly: NO_INFO
3. Start with the entity name, then structure like this example:
"Arctic LNG 2: Russian LNG project operator. Based in St. Petersburg. Sanctioned under Russia-related authorities. Involved in Arctic LNG 2 project circumventing sanctions. Designated November 2024."
4. Include: Entity name, type, location, sanctions program, reason for sanctions, designation date
5. Maximum 240 characters. No markdown, no bullet points, no thinking aloud."""
            },
            {
                "role": "user",
                "content": f"Provide factual context for '{name}' on the {source} sanctions list. Search official sources and output only the structured summary starting with the entity name, or NO_INFO."
            }
        ]
        
        # Make the API call with web search tool
        response = client.chat.completions.create(
            model="kimi-k2.5",
            messages=messages,
            temperature=1,
            tools=[
                {
                    "type": "builtin_function",
                    "function": {"name": "$web_search"}
                }
            ]
        )
        
        content = response.choices[0].message.content.strip()
        
        # Remove any thinking/search artifacts that might have slipped through
        content = content.replace("I'll search", "").replace("Let me search", "")
        content = content.replace("**Search queries:**", "").replace("Search queries:", "")
        content = content.replace("I'll look up", "").replace("Let me find", "")
        
        # Check if Kimi found no information
        if "NO_INFO" in content:
            print(f"Kimi could not find verified information for '{name}', skipping follow-up")
            return None
        
        # Clean up any remaining artifacts
        lines = content.split('\n')
        # Filter out lines that look like search queries or thinking
        clean_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('"') and not line.startswith('1.') and not line.startswith('2.') and not line.startswith('3.'):
                if 'site:' not in line and 'http' not in line:
                    clean_lines.append(line)
        
        if clean_lines:
            content = ' '.join(clean_lines)
        else:
            content = content.replace('\n', ' ')
        
        content = content.strip()
        
        # Ensure it's under 280 chars for Twitter (no "Context: " prefix now)
        if len(content) > 280:
            content = content[:277] + "..."
            
        print(f"Generated context for '{name}': {content}")
        return content
        
    except Exception as e:
        print(f"Error getting context from Kimi for '{name}': {e}")
        return None

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
    
    # Count total added entities
    total_added = sum(len(names) for names in added.values())
    
    if added or removed:
        messages = format_changes(added, "added")
        messages.extend(format_changes(removed, "removed"))
        
        full_message = " | ".join(messages)
        message_chunks = split_message(full_message)
        
        # Collect all tweet IDs for follow-ups (keyed by entity name)
        main_tweet_ids = {}
        
        try:
            # Post to Twitter - main thread
            previous_tweet_id = None
            for i, chunk in enumerate(message_chunks):
                if i == 0:
                    tweet_id = send_tweet(chunk)
                    # Store the first tweet ID for each added entity for follow-ups
                    for source, names in added.items():
                        for name in names:
                            main_tweet_ids[name] = tweet_id
                else:
                    tweet_id = send_tweet(chunk, in_reply_to_id=previous_tweet_id)
                previous_tweet_id = tweet_id
            
            # Generate and send follow-up tweets for ADDED entities with safeguards
            follow_up_count = 0
            skipped_count = 0
            
            for source, names in added.items():
                for name in names:
                    # Check if we've hit the max follow-ups limit
                    if follow_up_count >= MAX_FOLLOW_UPS_PER_RUN:
                        skipped_count += 1
                        continue
                    
                    # Get context from Kimi
                    context = get_sanctions_context_with_kimi(name, source)
                    
                    if context:
                        # Send follow-up tweet as reply to the main tweet
                        try:
                            followup_id = send_tweet(context, in_reply_to_id=main_tweet_ids.get(name, previous_tweet_id))
                            print(f"Sent follow-up tweet for {name}")
                            follow_up_count += 1
                            
                            # Rate limit protection - sleep between tweets
                            if follow_up_count < MAX_FOLLOW_UPS_PER_RUN:
                                time.sleep(RATE_LIMIT_DELAY)
                                
                        except Exception as e:
                            print(f"Error sending follow-up tweet for {name}: {e}")
                    else:
                        print(f"No follow-up tweet sent for {name} (no verified information found)")
            
            # Report if any were skipped due to limit
            if skipped_count > 0:
                print(f"Skipped {skipped_count} entities due to MAX_FOLLOW_UPS_PER_RUN limit ({MAX_FOLLOW_UPS_PER_RUN})")
            
        except Exception as e:
            print(f"Error posting messages: {str(e)}")
        
        save_current_state(current_list)
    else:
        print("No changes detected.")

if __name__ == "__main__":
    check_for_updates()

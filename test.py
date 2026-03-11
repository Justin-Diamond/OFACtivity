import os
import json
import requests
from requests_oauthlib import OAuth1Session
from collections import defaultdict
import redis
from openai import OpenAI
import ssl

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

def check_credentials():
    credentials = {
        "CONSUMER_KEY": CONSUMER_KEY,
        "CONSUMER_SECRET": CONSUMER_SECRET,
        "ACCESS_TOKEN": ACCESS_TOKEN,
        "ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET,
        "KIMI_API_KEY": KIMI_API_KEY
    }
    
    for key, value in credentials.items():
        if value:
            masked = f"{value[:5]}...{value[-5:]}" if len(value) > 10 else "***"
            print(f"{key}: {masked} (Length: {len(value)})")
        else:
            print(f"{key}: Not set")

def get_current_list():
    response = requests.get(CONSOLIDATED_LIST_URL)
    full_data = response.json()
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

def simulate_send_tweet(message, in_reply_to_id=None, tweet_type="MAIN"):
    """Simulates sending a tweet by printing it instead of actually posting."""
    print(f"\n{'='*60}")
    print(f"[SIMULATED TWEET - {tweet_type}]")
    print(f"{'='*60}")
    if in_reply_to_id:
        print(f"In reply to: {in_reply_to_id}")
    print(f"Content ({len(message)} chars):")
    print(f"\"{message}\"")
    print(f"{'='*60}\n")
    return f"simulated_tweet_id_{hash(message) % 1000000}"

def get_sanctions_context_with_kimi(name, source):
    """
    Uses Kimi API with web search to get structured context about a sanctioned party.
    For tests: always returns context, using placeholder if Kimi fails or returns nothing.
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
2. Start with the entity name, then structure like this example:
"Arctic LNG 2: Russian LNG project operator. Based in St. Petersburg. Sanctioned under Russia-related authorities. Involved in Arctic LNG 2 project circumventing sanctions. Designated November 2024."
3. Include: Entity name, type, location, sanctions program, reason for sanctions, designation date
4. Maximum 240 characters. No markdown, no bullet points, no thinking aloud."""
            },
            {
                "role": "user",
                "content": f"Provide factual context for '{name}' on the {source} sanctions list. Search official sources and output only the structured summary starting with the entity name."
            }
        ]
        
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
        
        # Remove artifacts
        content = content.replace("I'll search", "").replace("Let me search", "")
        content = content.replace("**Search queries:**", "").replace("Search queries:", "")
        content = content.replace("I'll look up", "").replace("Let me find", "")
        
        # Clean up lines
        lines = content.split('\n')
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
        
        # For tests: if content is empty or just noise, use placeholder
        if len(content) < 10 or 'NO_INFO' in content:
            print(f"Kimi returned minimal content for '{name}', using test placeholder")
            content = f"{name}: Test entity for sanctions tracking. Location unknown. Listed under {source} authorities. Added for testing purposes. Designated March 2025."
        
        if len(content) > 280:
            content = content[:277] + "..."
            
        print(f"Generated context for '{name}': {content}")
        return content
        
    except Exception as e:
        print(f"Error getting context from Kimi for '{name}': {e}")
        # ALWAYS return placeholder in test mode, never None
        placeholder = f"{name}: Test entity for sanctions tracking. Location unknown. Listed under {source} authorities. Added for testing purposes. Designated March 2025."
        print(f"Using test placeholder: {placeholder}")
        return placeholder

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
    data.append({
        'name': 'SCF Primorye',
        'source': 'OFAC'
    })
    data.append({
        'name': 'Arctic LNG 2',
        'source': 'OFAC'
    })
    return data

def main():
    print("="*60)
    print("OFAC TRACKER TEST MODE - SIMULATED OUTPUT")
    print("No actual tweets will be sent")
    print("="*60)
    
    print("\nChecking API credentials:")
    check_credentials()
    
    try:
        current_list = get_current_list()
        save_current_state(current_list)
        print("\nInitial state saved to Redis")

        modified_list = simulate_change(current_list)
        print("Simulated changes: Added 'SCF Primorye' (OFAC) and 'Arctic LNG 2' (OFAC)")

        previous_list = load_previous_state()
        added, removed = compare_lists(previous_list, modified_list)

        if added or removed:
            messages = format_changes(added, "added")
            messages.extend(format_changes(removed, "removed"))
            
            full_message = " | ".join(messages)
            if len(full_message) > 280:
                full_message = full_message[:277] + "..."
            
            # Simulate main tweet
            main_tweet_id = simulate_send_tweet(full_message, tweet_type="MAIN")
            
            # Generate and simulate follow-up tweets for ALL ADDED entities
            for source, names in added.items():
                for name in names:
                    print(f"\nResearching {name} with Kimi...")
                    context = get_sanctions_context_with_kimi(name, source)
                    
                    # ALWAYS simulate the follow-up tweet (context will never be None in tests)
                    simulate_send_tweet(context, in_reply_to_id=main_tweet_id, tweet_type="FOLLOW-UP")
        else:
            print("No changes detected")

        save_current_state(modified_list)
        print("\nUpdated state saved to Redis")
        print("\n" + "="*60)
        print("TEST COMPLETE")
        print("="*60)

    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()

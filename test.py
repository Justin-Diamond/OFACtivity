import os
import json
import random
import requests
from requests_oauthlib import OAuth1Session

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"

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

def get_random_name():
    response = requests.get(CONSOLIDATED_LIST_URL)
    data = response.json()
    names = [item['name'] for item in data['results']]
    return random.choice(names)

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

def main():
    print("Checking Twitter API credentials:")
    check_credentials()
    
    try:
        random_name = get_random_name()
        tweet = f"Test Tweet: Random name from OFAC list - {random_name}"
        send_tweet(tweet)
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()

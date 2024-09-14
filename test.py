import os
import json
import random
import requests
from requests.auth import AuthBase
from requests.auth import HTTPBasicAuth

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"

# Twitter API v2 endpoint for posting tweets
TWITTER_API_URL = "https://api.twitter.com/2/tweets"

# Twitter API credentials
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

class BearerTokenAuth(AuthBase):
    def __init__(self, consumer_key, consumer_secret):
        self.bearer_token_url = "https://api.twitter.com/oauth2/token"
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.bearer_token = self.get_bearer_token()

    def get_bearer_token(self):
        response = requests.post(
            self.bearer_token_url,
            auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret),
            data={'grant_type': 'client_credentials'},
            headers={"User-Agent": "TwitterDevSampleCode"}
        )

        if response.status_code != 200:
            raise Exception(f"Cannot get a Bearer token (HTTP {response.status_code}): {response.text}")

        body = response.json()
        return body['access_token']

    def __call__(self, r):
        r.headers['Authorization'] = f"Bearer {self.bearer_token}"
        r.headers['User-Agent'] = "TwitterDevSampleCode"
        return r

def check_credentials():
    credentials = {
        "TWITTER_API_KEY": TWITTER_API_KEY,
        "TWITTER_API_SECRET": TWITTER_API_SECRET,
        "TWITTER_ACCESS_TOKEN": TWITTER_ACCESS_TOKEN,
        "TWITTER_ACCESS_TOKEN_SECRET": TWITTER_ACCESS_TOKEN_SECRET
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
    auth = BearerTokenAuth(TWITTER_API_KEY, TWITTER_API_SECRET)
    payload = {"text": message}

    response = requests.post(TWITTER_API_URL, auth=auth, json=payload)

    if response.status_code != 201:
        raise Exception(f"Request returned an error: {response.status_code} {response.text}")

    print(f"Tweet sent successfully: {message}")

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

import os
import json
import random
import requests
import tweepy

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"

# Twitter API credentials
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

def get_random_name():
    response = requests.get(CONSOLIDATED_LIST_URL)
    data = response.json()
    names = [item['name'] for item in data['results']]
    return random.choice(names)

def send_tweet(message):
    auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
    auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)
    api = tweepy.API(auth)

    api.update_status(message)
    print(f"Tweet sent: {message}")

def main():
    try:
        random_name = get_random_name()
        print("Random Name: " + random_name)
        tweet = f"Test Tweet: Random name from OFAC list - {random_name}"
        send_tweet(tweet)
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()

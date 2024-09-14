import os
import json
import random
import requests

# URL of the consolidated list
CONSOLIDATED_LIST_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"

def get_random_name():
    try:
        response = requests.get(CONSOLIDATED_LIST_URL)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        data = response.json()
        names = [item['name'] for item in data['results']]
        return random.choice(names)
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

def main():
    try:
        random_name = get_random_name()
        if random_name:
            message = f"Test Output: Random name from OFAC list - {random_name}"
            print(message)
            print("(Actual tweeting is disabled due to API restrictions)")
        else:
            print("Failed to retrieve a random name.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()

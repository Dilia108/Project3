import requests, os
from dotenv import load_dotenv
load_dotenv()

payload = {
    "grant_type":    "client_credentials",
    "client_id":     os.getenv("SF_CONSUMER_KEY"),
    "client_secret": os.getenv("SF_CONSUMER_SECRET"),
}
r = requests.post(
    "https://orgfarm-0eccb3e7ef-dev-ed.develop.my.salesforce.com/services/oauth2/token",
    data=payload
)
print(r.json())
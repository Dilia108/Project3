import requests
import os
from dotenv import load_dotenv
load_dotenv()

# ── OpenAI ──────────────────────────────────────────────────
try:
    from openai import OpenAI
    c = OpenAI()
    models = c.models.list()
    print(f"✓ OpenAI connected — first model: {models.data[0].id}")
except Exception as e:
    print(f"✗ OpenAI failed: {e}")

# ── Supabase ─────────────────────────────────────────────────
try:
    from supabase import create_client
    s = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    s.table("supplier").select("*").execute()
    print("✓ Supabase connected")
except Exception as e:
    print(f"✗ Supabase failed: {e}")

# ── Salesforce (Client Credentials Flow) ─────────────────────
try:
    payload = {
        "grant_type":    "client_credentials",
        "client_id":     os.getenv("SF_CONSUMER_KEY"),
        "client_secret": os.getenv("SF_CONSUMER_SECRET"),
    }
    r = requests.post(
        "https://orgfarm-0eccb3e7ef-dev-ed.develop.my.salesforce.com/services/oauth2/token",
        data=payload
    )
    token_data = r.json()
    if "access_token" not in token_data:
        raise Exception(token_data)
    print(f"✓ Salesforce connected — instance: {token_data['instance_url']}")
except Exception as e:
    print(f"✗ Salesforce failed: {e}")
import requests
import os
from dotenv import load_dotenv
load_dotenv()

# ── Salesforce: fetch Check24 account ────────────────────────
try:
    payload = {
        "grant_type":    "client_credentials",
        "client_id":     os.getenv("SF_CONSUMER_KEY"),
        "client_secret": os.getenv("SF_CONSUMER_SECRET"),
    }
    r = requests.post(
        f"https://{os.getenv('SF_ORG_DOMAIN')}/services/oauth2/token",
        data=payload
    )
    token_data = r.json()
    if "access_token" not in token_data:
        raise Exception(token_data)

    from simple_salesforce import Salesforce
    sf = Salesforce(
        instance_url=token_data["instance_url"],
        session_id=token_data["access_token"]
    )

    result = sf.query("SELECT Name, Type, CustomerPriority__c, Active__c FROM Account WHERE Name = 'Check24'")
    if result["totalSize"] == 0:
        raise Exception("Check24 account not found in Salesforce")
    account = result["records"][0]
    print(f"✓ Salesforce — Check24 found:")
    print(f"    Name:              {account['Name']}")
    print(f"    Type:              {account['Type']}")
    print(f"    Customer Priority: {account.get('CustomerPriority__c', 'N/A')}")
    print(f"    Active:            {account.get('Active__c', 'N/A')}")

except Exception as e:
    print(f"✗ Salesforce Check24 query failed: {e}")

# ── Supabase: 3 validation queries ───────────────────────────
try:
    from supabase import create_client
    s = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

    # Query 1: supplier count
    r1 = s.table("supplier").select("*", count="exact").execute()
    print(f"\n✓ Supabase Query 1 — Total suppliers: {r1.count}")

    # Query 2: Check24 active connections
    r2 = s.table("client_supplier").select(
        "client_name, status, supplier(name)"
    ).eq("client_name", "Check24").eq("status", "active").execute()
    print(f"✓ Supabase Query 2 — Check24 active suppliers: {len(r2.data)}")
    for row in r2.data:
        print(f"    {row['supplier']['name']}")

    # Query 3: Check24 rate codes
    r3 = s.table("product").select(
        "rate_code, rate_type, product_type, source_country, destination_country"
    ).eq("client_name", "Check24").eq("status", "active").execute()
    print(f"✓ Supabase Query 3 — Check24 active rate codes: {len(r3.data)}")
    for row in r3.data:
        print(f"    {row['rate_code']} | {row['rate_type']:5} | {row['product_type']:12} ({row['source_country']}→{row['destination_country']})")

except Exception as e:
    print(f"✗ Supabase validation failed: {e}")
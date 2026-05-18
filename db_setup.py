"""
db_setup.py
===========
Creates and seeds the Supabase PostgreSQL database for the
KAM Supply Intelligence Agent.

Clients:
  - Check24    : Commissionable — net + gross rates — Active
  - Autoslash  : Wholesaler     — net rates only    — Active
  - HappyCar   : Commissionable — net + gross rates — Inactive

Tables:
  - supplier          : car rental suppliers (Avis, Hertz, Enterprise, Budget, Sixt)
  - client_supplier   : which suppliers are connected to which clients
  - product           : rate codes per client/supplier with rate type and product details

Run with:
    python db_setup.py

Requirements:
    - .env file with SUPABASE_URL and SUPABASE_KEY
    - pip install supabase python-dotenv
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# DDL — Create tables
# ============================================================

CREATE_SUPPLIER = """
CREATE TABLE IF NOT EXISTS supplier (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    code        TEXT NOT NULL UNIQUE,
    region      TEXT NOT NULL
);
"""

CREATE_CLIENT_SUPPLIER = """
CREATE TABLE IF NOT EXISTS client_supplier (
    id              SERIAL PRIMARY KEY,
    client_name     TEXT NOT NULL,
    supplier_id     INTEGER NOT NULL REFERENCES supplier(id),
    status          TEXT NOT NULL DEFAULT 'active',
    UNIQUE (client_name, supplier_id)
);
"""

CREATE_PRODUCT = """
CREATE TABLE IF NOT EXISTS product (
    id                  SERIAL PRIMARY KEY,
    client_name         TEXT NOT NULL,
    supplier_id         INTEGER NOT NULL REFERENCES supplier(id),
    rate_code           TEXT NOT NULL,
    rate_type           TEXT NOT NULL,        -- 'net' or 'gross'
    product_type        TEXT NOT NULL,        -- 'domestic_us', 'inbound', 'outbound'
    source_country      TEXT NOT NULL,
    destination_country TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',
    notes               TEXT,
    UNIQUE (client_name, supplier_id, rate_code)
);
"""


# ============================================================
# Seed data
# ============================================================

SUPPLIERS = [
    {"name": "Avis",       "code": "AVIS", "region": "US"},
    {"name": "Hertz",      "code": "HERT", "region": "US"},
    {"name": "Enterprise", "code": "ENTP", "region": "US"},
    {"name": "Budget",     "code": "BUDG", "region": "EU"},
    {"name": "Sixt",       "code": "SIXT", "region": "EU"},
]

# Client names MUST match Salesforce account names exactly
CLIENT_SUPPLIERS = [
    # -------------------------------------------------------
    # Check24 — Commissionable, Active
    # -------------------------------------------------------
    {"client_name": "Check24",   "supplier_code": "AVIS", "status": "active"},
    {"client_name": "Check24",   "supplier_code": "HERT", "status": "active"},
    {"client_name": "Check24",   "supplier_code": "ENTP", "status": "active"},
    # -------------------------------------------------------
    # Autoslash — Wholesaler, Active
    # -------------------------------------------------------
    {"client_name": "Autoslash", "supplier_code": "AVIS", "status": "active"},
    {"client_name": "Autoslash", "supplier_code": "HERT", "status": "active"},
    {"client_name": "Autoslash", "supplier_code": "BUDG", "status": "active"},
    # -------------------------------------------------------
    # HappyCar — Commissionable, Inactive
    # -------------------------------------------------------
    {"client_name": "HappyCar",  "supplier_code": "SIXT", "status": "inactive"},
    {"client_name": "HappyCar",  "supplier_code": "ENTP", "status": "inactive"},
]

PRODUCTS = [
    # ===========================================================
    # CHECK24 — Commissionable → both net AND gross per supplier
    # ===========================================================

    # Check24 + Avis
    {"client_name": "Check24", "supplier_code": "AVIS",
     "rate_code": "JE", "rate_type": "net",   "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Avis net rate — domestic US"},
    {"client_name": "Check24", "supplier_code": "AVIS",
     "rate_code": "JF", "rate_type": "gross", "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Avis gross rate — domestic US — commissionable"},
    {"client_name": "Check24", "supplier_code": "AVIS",
     "rate_code": "KE", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "ES", "status": "active",
     "notes": "Avis net rate — inbound DE→ES"},
    {"client_name": "Check24", "supplier_code": "AVIS",
     "rate_code": "KF", "rate_type": "gross", "product_type": "inbound",
     "source_country": "DE", "destination_country": "ES", "status": "active",
     "notes": "Avis gross rate — inbound DE→ES — commissionable"},
    {"client_name": "Check24", "supplier_code": "AVIS",
     "rate_code": "KG", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "IT", "status": "active",
     "notes": "Avis net rate — inbound DE→IT"},

    # Check24 + Hertz
    {"client_name": "Check24", "supplier_code": "HERT",
     "rate_code": "IT", "rate_type": "net",   "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Hertz net rate — domestic US"},
    {"client_name": "Check24", "supplier_code": "HERT",
     "rate_code": "IU", "rate_type": "gross", "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Hertz gross rate — domestic US — commissionable"},
    {"client_name": "Check24", "supplier_code": "HERT",
     "rate_code": "IV", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "FR", "status": "active",
     "notes": "Hertz net rate — inbound DE→FR"},
    {"client_name": "Check24", "supplier_code": "HERT",
     "rate_code": "IW", "rate_type": "gross", "product_type": "inbound",
     "source_country": "DE", "destination_country": "FR", "status": "active",
     "notes": "Hertz gross rate — inbound DE→FR — commissionable"},

    # Check24 + Enterprise
    {"client_name": "Check24", "supplier_code": "ENTP",
     "rate_code": "EA", "rate_type": "net",   "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Enterprise net rate — domestic US"},
    {"client_name": "Check24", "supplier_code": "ENTP",
     "rate_code": "EB", "rate_type": "gross", "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Enterprise gross rate — domestic US — commissionable"},

    # ===========================================================
    # AUTOSLASH — Wholesaler → net rates ONLY
    # ===========================================================

    # Autoslash + Avis
    {"client_name": "Autoslash", "supplier_code": "AVIS",
     "rate_code": "AJ", "rate_type": "net",   "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Avis net rate — domestic US — wholesaler, no gross equivalent"},
    {"client_name": "Autoslash", "supplier_code": "AVIS",
     "rate_code": "AK", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "ES", "status": "active",
     "notes": "Avis net rate — inbound DE→ES — wholesaler"},
    {"client_name": "Autoslash", "supplier_code": "AVIS",
     "rate_code": "AL", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "IT", "status": "active",
     "notes": "Avis net rate — inbound DE→IT — wholesaler"},

    # Autoslash + Hertz
    {"client_name": "Autoslash", "supplier_code": "HERT",
     "rate_code": "HN", "rate_type": "net",   "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Hertz net rate — domestic US — wholesaler"},
    {"client_name": "Autoslash", "supplier_code": "HERT",
     "rate_code": "HO", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "FR", "status": "active",
     "notes": "Hertz net rate — inbound DE→FR — wholesaler"},

    # Autoslash + Budget
    {"client_name": "Autoslash", "supplier_code": "BUDG",
     "rate_code": "BU", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "FR", "status": "active",
     "notes": "Budget net rate — inbound DE→FR — wholesaler"},
    {"client_name": "Autoslash", "supplier_code": "BUDG",
     "rate_code": "BV", "rate_type": "net",   "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "active",
     "notes": "Budget net rate — domestic US — wholesaler"},

    # ===========================================================
    # HAPPYCAR — Commissionable → net + gross, but INACTIVE
    # ===========================================================

    # HappyCar + Sixt
    {"client_name": "HappyCar", "supplier_code": "SIXT",
     "rate_code": "HX", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "ES", "status": "inactive",
     "notes": "Sixt net rate — inbound DE→ES — contract inactive"},
    {"client_name": "HappyCar", "supplier_code": "SIXT",
     "rate_code": "HY", "rate_type": "gross", "product_type": "inbound",
     "source_country": "DE", "destination_country": "ES", "status": "inactive",
     "notes": "Sixt gross rate — inbound DE→ES — commissionable, contract inactive"},
    {"client_name": "HappyCar", "supplier_code": "SIXT",
     "rate_code": "HZ", "rate_type": "net",   "product_type": "domestic_us",
     "source_country": "US", "destination_country": "US", "status": "inactive",
     "notes": "Sixt net rate — domestic US — contract inactive"},

    # HappyCar + Enterprise
    {"client_name": "HappyCar", "supplier_code": "ENTP",
     "rate_code": "HE", "rate_type": "net",   "product_type": "inbound",
     "source_country": "DE", "destination_country": "IT", "status": "inactive",
     "notes": "Enterprise net rate — inbound DE→IT — contract inactive"},
    {"client_name": "HappyCar", "supplier_code": "ENTP",
     "rate_code": "HF", "rate_type": "gross", "product_type": "inbound",
     "source_country": "DE", "destination_country": "IT", "status": "inactive",
     "notes": "Enterprise gross rate — inbound DE→IT — commissionable, contract inactive"},
]


# ============================================================
# Helper functions
# ============================================================

def run_ddl(sql: str, table_name: str):
    try:
        supabase.rpc("execute_sql", {"query": sql}).execute()
        print(f"  ✓ Table '{table_name}' created or already exists")
    except Exception as e:
        print(f"  ⚠ Could not auto-create '{table_name}' via RPC: {e}")
        print(f"    → Run the DDL manually in Supabase SQL Editor")


def seed_suppliers():
    print("\n[2] Seeding suppliers...")
    for s in SUPPLIERS:
        try:
            supabase.table("supplier").upsert(s, on_conflict="code").execute()
            print(f"  ✓ {s['name']} ({s['code']})")
        except Exception as e:
            print(f"  ✗ {s['name']}: {e}")


def seed_client_suppliers():
    print("\n[3] Seeding client-supplier connections...")
    for cs in CLIENT_SUPPLIERS:
        try:
            result = supabase.table("supplier").select("id").eq("code", cs["supplier_code"]).single().execute()
            supplier_id = result.data["id"]
            record = {
                "client_name": cs["client_name"],
                "supplier_id": supplier_id,
                "status":      cs["status"],
            }
            supabase.table("client_supplier").upsert(
                record, on_conflict="client_name,supplier_id"
            ).execute()
            print(f"  ✓ {cs['client_name']} ↔ {cs['supplier_code']} ({cs['status']})")
        except Exception as e:
            print(f"  ✗ {cs['client_name']} ↔ {cs['supplier_code']}: {e}")


def seed_products():
    print("\n[4] Seeding products (rate codes)...")
    for p in PRODUCTS:
        try:
            result = supabase.table("supplier").select("id").eq("code", p["supplier_code"]).single().execute()
            supplier_id = result.data["id"]
            record = {
                "client_name":          p["client_name"],
                "supplier_id":          supplier_id,
                "rate_code":            p["rate_code"],
                "rate_type":            p["rate_type"],
                "product_type":         p["product_type"],
                "source_country":       p["source_country"],
                "destination_country":  p["destination_country"],
                "status":               p["status"],
                "notes":                p.get("notes", ""),
            }
            supabase.table("product").upsert(
                record, on_conflict="client_name,supplier_id,rate_code"
            ).execute()
            print(f"  ✓ {p['client_name']:12} | {p['supplier_code']} | {p['rate_code']} | {p['rate_type']:5} | {p['product_type']:12} ({p['source_country']}→{p['destination_country']}) [{p['status']}]")
        except Exception as e:
            print(f"  ✗ {p['client_name']} | {p['rate_code']}: {e}")


def validate():
    print("\n[5] Validation queries...")
    try:
        r = supabase.table("supplier").select("*", count="exact").execute()
        print(f"  ✓ Total suppliers: {r.count}")

        for client in ["Check24", "Autoslash", "HappyCar"]:
            r = supabase.table("product").select("rate_code, rate_type, status").eq("client_name", client).execute()
            net   = [x for x in r.data if x["rate_type"] == "net"]
            gross = [x for x in r.data if x["rate_type"] == "gross"]
            print(f"  ✓ {client:12} — {len(r.data):2} rate codes total | net: {len(net)} | gross: {len(gross)}")

        # Commissionable check
        print("\n  Commissionable verification (should have both net and gross):")
        for client in ["Check24", "HappyCar"]:
            r = supabase.table("product").select("rate_type").eq("client_name", client).execute()
            types = set(x["rate_type"] for x in r.data)
            status = "✓ CONFIRMED" if {"net", "gross"} == types else "✗ MISSING ONE"
            print(f"  {status} — {client} has: {types}")

        print("\n  Wholesaler check (Autoslash — net only):")
        r = supabase.table("product").select("rate_type").eq("client_name", "Autoslash").execute()
        types = set(x["rate_type"] for x in r.data)
        status = "✓ CONFIRMED" if types == {"net"} else "✗ UNEXPECTED GROSS RATES FOUND"
        print(f"  {status} — Autoslash has: {types}")

    except Exception as e:
        print(f"  ✗ Validation error: {e}")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("KAM Agent — Supabase Database Setup")
    print("Clients: Check24 (commissionable) | Autoslash (wholesaler) | HappyCar (commissionable, inactive)")
    print("=" * 60)

    print("\n[1] Creating tables...")
    print("  → If RPC fails, run the DDL below manually in")
    print("    Supabase Dashboard → SQL Editor:\n")
    print(CREATE_SUPPLIER)
    print(CREATE_CLIENT_SUPPLIER)
    print(CREATE_PRODUCT)

    run_ddl(CREATE_SUPPLIER,        "supplier")
    run_ddl(CREATE_CLIENT_SUPPLIER, "client_supplier")
    run_ddl(CREATE_PRODUCT,         "product")

    seed_suppliers()
    seed_client_suppliers()
    seed_products()
    validate()

    print("\n" + "=" * 60)
    print("Setup complete. Database is ready for the agent.")
    print("=" * 60)

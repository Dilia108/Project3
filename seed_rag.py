"""
seed_rag.py
===========
Populates ChromaDB with Supabase table descriptions, column definitions,
and a business glossary for the KAM Supply Intelligence Agent.

Clients covered:
  - Check24    : Commissionable — net + gross — Active
  - Autoslash  : Wholesaler     — net only    — Active
  - HappyCar   : Commissionable — net + gross — Inactive

Run with:
    python seed_rag.py

Requirements:
    - pip install chromadb openai python-dotenv
"""

import os
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions

load_dotenv()

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
CHROMA_HOST       = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT       = int(os.getenv("CHROMA_PORT", 8000))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION_NAME", "kam_schema_store")


# ============================================================
# Schema documents
# ============================================================

SCHEMA_DOCUMENTS = [

    # ----------------------------------------------------------
    # Table: supplier
    # ----------------------------------------------------------
    {
        "id": "table_supplier",
        "document": """
Table: supplier
Description: Contains all car rental supplier companies on the platform.
Each supplier is a car rental brand such as Avis, Hertz, Enterprise, Budget, or Sixt.

Columns:
  - id (integer, primary key): unique identifier
  - name (text): full supplier name e.g. 'Avis', 'Hertz', 'Enterprise', 'Budget', 'Sixt'
  - code (text): short uppercase code e.g. 'AVIS', 'HERT', 'ENTP', 'BUDG', 'SIXT'
  - region (text): primary operating region e.g. 'US', 'EU'

Use when asked about: supplier names, supplier codes, which suppliers exist.
JOIN pattern: supplier.id = product.supplier_id or supplier.id = client_supplier.supplier_id
        """,
        "metadata": {"type": "table", "table": "supplier"}
    },

    # ----------------------------------------------------------
    # Table: client_supplier
    # ----------------------------------------------------------
    {
        "id": "table_client_supplier",
        "document": """
Table: client_supplier
Description: Bridge table linking clients to their connected suppliers.
Each row represents a commercial relationship between a client and a supplier.

Columns:
  - id (integer, primary key)
  - client_name (text): must match Salesforce account name exactly
    Known values: 'Check24', 'Autoslash', 'HappyCar'
  - supplier_id (integer, foreign key): references supplier.id
  - status (text): 'active' or 'inactive'

Use when asked about: how many suppliers a client has, which suppliers are
connected to a client, whether a connection is active.

Key JOIN pattern:
  SELECT s.name FROM supplier s
  JOIN client_supplier cs ON cs.supplier_id = s.id
  WHERE cs.client_name = 'Check24' AND cs.status = 'active'
        """,
        "metadata": {"type": "table", "table": "client_supplier"}
    },

    # ----------------------------------------------------------
    # Table: product
    # ----------------------------------------------------------
    {
        "id": "table_product",
        "document": """
Table: product
Description: Contains all rate codes active for each client-supplier combination.
A rate code is a short alphanumeric identifier representing a specific commercial
product in car rental distribution, e.g. 'JE' = Avis net domestic US for Check24.

Columns:
  - id (integer, primary key)
  - client_name (text): must match Salesforce account name exactly
    Known values: 'Check24', 'Autoslash', 'HappyCar'
  - supplier_id (integer, foreign key): references supplier.id
  - rate_code (text): rate code identifier e.g. 'JE', 'JF', 'IT', 'AJ', 'HX'
  - rate_type (text): 'net' or 'gross'
      net   = wholesale price, client marks up independently
      gross = retail price, client earns commission from supplier
  - product_type (text): 'domestic_us', 'inbound', or 'outbound'
  - source_country (text): ISO 2-letter country code where customer is based e.g. 'US', 'DE'
  - destination_country (text): ISO 2-letter country code where car is picked up e.g. 'US', 'ES'
  - status (text): 'active' or 'inactive'
  - notes (text): additional context

Use when asked about: rate codes, rate types, which products a client has,
domestic vs inbound, net vs gross rates, specific supplier rate codes.

Key JOIN pattern:
  SELECT p.rate_code, p.rate_type, p.product_type, s.name as supplier
  FROM product p
  JOIN supplier s ON s.id = p.supplier_id
  WHERE p.client_name = 'Check24' AND p.status = 'active'
  ORDER BY s.name, p.rate_type, p.product_type
        """,
        "metadata": {"type": "table", "table": "product"}
    },

    # ----------------------------------------------------------
    # Business glossary: rate codes
    # ----------------------------------------------------------
    {
        "id": "glossary_rate_codes",
        "document": """
Business glossary: Rate codes

A rate code is a short alphanumeric identifier (usually 2 letters) representing
a specific commercial product in car rental distribution.

Each rate code uniquely identifies:
  - Which supplier provides the rates
  - Whether the rate is net or gross
  - What product type it covers (domestic US, inbound, outbound)
  - Which client it was negotiated for

Rate codes by client in the system:

Check24 (Commissionable — has BOTH net and gross):
  JE = Avis,       net,   domestic US
  JF = Avis,       gross, domestic US  ← commissionable pair of JE
  KE = Avis,       net,   inbound DE→ES
  KF = Avis,       gross, inbound DE→ES  ← commissionable pair of KE
  KG = Avis,       net,   inbound DE→IT
  IT = Hertz,      net,   domestic US
  IU = Hertz,      gross, domestic US  ← commissionable pair of IT
  IV = Hertz,      net,   inbound DE→FR
  IW = Hertz,      gross, inbound DE→FR  ← commissionable pair of IV
  EA = Enterprise, net,   domestic US
  EB = Enterprise, gross, domestic US  ← commissionable pair of EA

Autoslash (Wholesaler — net rates ONLY, no gross equivalents):
  AJ = Avis,   net, domestic US
  AK = Avis,   net, inbound DE→ES
  AL = Avis,   net, inbound DE→IT
  HN = Hertz,  net, domestic US
  HO = Hertz,  net, inbound DE→FR
  BU = Budget, net, inbound DE→FR
  BV = Budget, net, domestic US

HappyCar (Commissionable — net + gross, but ALL inactive):
  HX = Sixt,       net,   inbound DE→ES   [inactive]
  HY = Sixt,       gross, inbound DE→ES   [inactive]
  HZ = Sixt,       net,   domestic US     [inactive]
  HE = Enterprise, net,   inbound DE→IT   [inactive]
  HF = Enterprise, gross, inbound DE→IT   [inactive]
        """,
        "metadata": {"type": "glossary", "topic": "rate_codes"}
    },

    # ----------------------------------------------------------
    # Business glossary: net vs gross and business models
    # ----------------------------------------------------------
    {
        "id": "glossary_business_models",
        "document": """
Business glossary: Business models and rate types

--- Net rate ---
  - Supplier gives client a wholesale/net price
  - Client adds their own markup before showing to end customer
  - Client keeps the margin between what they charge and what they pay
  - rate_type = 'net' in the product table
  - All clients can have net rates

--- Gross rate (commissionable) ---
  - Supplier gives client a retail/gross price including a margin
  - Client earns a commission percentage paid back by the supplier
  - rate_type = 'gross' in the product table
  - Only commissionable clients have gross rates

--- Business model: Commissionable ---
  - Client has BOTH net AND gross rate codes active simultaneously
  - This is intentional — not a data error
  - Net and gross codes often come in pairs for the same route/product
    Example: Check24 has JE (net) + JF (gross) both for Avis domestic US
  - Clients: Check24 (active), HappyCar (inactive)
  - When reporting for a commissionable client, always show BOTH types
    and label them clearly as net or gross

--- Business model: Wholesaler ---
  - Client works exclusively with net rates
  - NO gross rate codes exist for this client
  - Client: Autoslash (active)
  - If asked whether Autoslash has gross rates, the answer is NO

--- Key rule for SQL ---
  Commissionable clients → do NOT filter by rate_type (show all)
  Wholesaler clients     → rate_type will always be 'net' only
  Always show rate_type in output so the KAM can see net vs gross clearly
        """,
        "metadata": {"type": "glossary", "topic": "business_models"}
    },

    # ----------------------------------------------------------
    # Business glossary: product types
    # ----------------------------------------------------------
    {
        "id": "glossary_product_types",
        "document": """
Business glossary: Product types

domestic_us:
  - Car rental entirely within the United States
  - source_country = 'US', destination_country = 'US'
  - Example: US customer renting in New York or Los Angeles

inbound:
  - Customer from one country renting a car in a different country
  - source_country = customer's home country (e.g. 'DE' = Germany)
  - destination_country = where the car is picked up (e.g. 'ES' = Spain)
  - Most common routes in this dataset: DE→ES, DE→FR, DE→IT
  - Example: German tourist renting a car in Spain

outbound:
  - Less common — not currently active in this dataset

SQL for domestic US products:
  SELECT p.rate_code, p.rate_type, s.name as supplier
  FROM product p JOIN supplier s ON s.id = p.supplier_id
  WHERE p.client_name = '[client]'
  AND p.product_type = 'domestic_us' AND p.status = 'active'

SQL for inbound products:
  SELECT p.rate_code, p.rate_type, s.name as supplier,
         p.source_country, p.destination_country
  FROM product p JOIN supplier s ON s.id = p.supplier_id
  WHERE p.client_name = '[client]'
  AND p.product_type = 'inbound' AND p.status = 'active'
        """,
        "metadata": {"type": "glossary", "topic": "product_types"}
    },

    # ----------------------------------------------------------
    # Business glossary: clients
    # ----------------------------------------------------------
    {
        "id": "glossary_clients",
        "document": """
Business glossary: Clients

Clients are online travel agencies (OTAs) or travel companies that distribute
car rental products. Client profile data lives in Salesforce.
Client operational data (rate codes, suppliers) lives in Supabase.

IMPORTANT: client_name in Supabase must match Salesforce Account name exactly.

Client profiles:

Check24:
  - Salesforce account name: 'Check24'
  - Account tier: Strategic
  - Business model: Commissionable
  - Contract status: Active
  - Rate types: net AND gross (both active simultaneously)
  - Suppliers: Avis, Hertz, Enterprise

Autoslash:
  - Salesforce account name: 'Autoslash'
  - Account tier: Growth
  - Business model: Wholesaler
  - Contract status: Active
  - Rate types: net ONLY (no gross rates — wholesaler model)
  - Suppliers: Avis, Hertz, Budget

HappyCar:
  - Salesforce account name: 'HappyCar'
  - Account tier: Standard
  - Business model: Commissionable
  - Contract status: Inactive
  - Rate types: net AND gross (both present but all inactive)
  - Suppliers: Sixt, Enterprise
  - Note: all rate codes are inactive — contract is not currently live
        """,
        "metadata": {"type": "glossary", "topic": "clients"}
    },

    # ----------------------------------------------------------
    # SQL query patterns
    # ----------------------------------------------------------
    {
        "id": "query_patterns",
        "document": """
Common SQL query patterns for KAM agent questions:

1. How many active suppliers does [client] have?
   SELECT COUNT(DISTINCT cs.supplier_id)
   FROM client_supplier cs
   WHERE cs.client_name = '[client]' AND cs.status = 'active'

2. Which suppliers are connected to [client]?
   SELECT s.name, s.code
   FROM supplier s
   JOIN client_supplier cs ON cs.supplier_id = s.id
   WHERE cs.client_name = '[client]' AND cs.status = 'active'

3. What rate codes does [client] have? (all suppliers, grouped)
   SELECT s.name as supplier, p.rate_code, p.rate_type,
          p.product_type, p.source_country, p.destination_country
   FROM product p
   JOIN supplier s ON s.id = p.supplier_id
   WHERE p.client_name = '[client]' AND p.status = 'active'
   ORDER BY s.name, p.rate_type, p.product_type

4. What rate codes does [client] have with [supplier]?
   SELECT p.rate_code, p.rate_type, p.product_type,
          p.source_country, p.destination_country
   FROM product p
   JOIN supplier s ON s.id = p.supplier_id
   WHERE p.client_name = '[client]'
   AND s.name = '[supplier]' AND p.status = 'active'

5. What domestic US rate codes does [client] have?
   SELECT p.rate_code, p.rate_type, s.name as supplier
   FROM product p
   JOIN supplier s ON s.id = p.supplier_id
   WHERE p.client_name = '[client]'
   AND p.product_type = 'domestic_us' AND p.status = 'active'

6. What inbound products does [client] have?
   SELECT p.rate_code, p.rate_type, s.name as supplier,
          p.source_country, p.destination_country
   FROM product p
   JOIN supplier s ON s.id = p.supplier_id
   WHERE p.client_name = '[client]'
   AND p.product_type = 'inbound' AND p.status = 'active'

7. Is [client] commissionable? (has both net and gross?)
   SELECT p.rate_type, COUNT(*) as count
   FROM product p
   WHERE p.client_name = '[client]' AND p.status = 'active'
   GROUP BY p.rate_type
        """,
        "metadata": {"type": "query_patterns", "topic": "sql_examples"}
    },
]


# ============================================================
# Main seeding function
# ============================================================

def seed_chromadb():
    print("=" * 60)
    print("KAM Agent — ChromaDB RAG Store Seeding")
    print("Clients: Check24 | Autoslash | HappyCar")
    print("=" * 60)

    print("\n[1] Connecting to ChromaDB...")
    try:
        client = chromadb.PersistentClient(path="./chroma_db")
        print("  ✓ Connected — local persistent ChromaDB (./chroma_db/)")
    except Exception as e:
        print(f"  ⚠ Local client failed: {e} — trying HTTP client...")
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        print(f"  ✓ Connected to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")

    print("\n[2] Setting up OpenAI embedding function...")
    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name="text-embedding-3-small"
    )

    print(f"\n[3] Creating/loading collection '{CHROMA_COLLECTION}'...")
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        embedding_function=ef,
        metadata={"description": "KAM Agent schema store — tables, columns, business glossary"}
    )
    print(f"  ✓ Collection ready")

    print(f"\n[4] Seeding {len(SCHEMA_DOCUMENTS)} documents...")
    for doc in SCHEMA_DOCUMENTS:
        try:
            collection.upsert(
                ids=[doc["id"]],
                documents=[doc["document"]],
                metadatas=[doc["metadata"]]
            )
            print(f"  ✓ {doc['id']}")
        except Exception as e:
            print(f"  ✗ {doc['id']}: {e}")

    print("\n[5] Validation — test retrieval queries...")
    test_queries = [
        "What rate codes does Check24 have with Avis?",
        "Does Autoslash have gross rates?",
        "What is the difference between net and gross rates?",
        "What does commissionable mean?",
        "Which table has supplier connections to clients?",
        "What are inbound products?",
        "What domestic US rates does Check24 have?",
    ]
    for query in test_queries:
        results = collection.query(query_texts=[query], n_results=1)
        best = results["ids"][0][0] if results["ids"][0] else "none"
        print(f"  ✓ '{query[:55]}' → {best}")

    print("\n" + "=" * 60)
    print(f"Complete. {len(SCHEMA_DOCUMENTS)} documents seeded into ChromaDB.")
    print("Local storage: ./chroma_db/")
    print("=" * 60)


if __name__ == "__main__":
    seed_chromadb()

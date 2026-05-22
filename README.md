# KAM Supply Intelligence Agent — Operations Guide

**Audience:** Operations / Data Analyst
**Last updated:** 21 May 2026 · Sprint 3

This document covers everything needed to run, maintain, and extend the KAM Supply Intelligence Agent without developer support. It assumes you are comfortable with the command line and have access to the project folder.

---

## What the agent does

The agent lets a Key Account Manager type a question in Slack — in plain English — and receive a structured answer combining:

- The client's profile pulled live from Salesforce (tier, business model, contract status, assigned KAM)
- Supplier or product data queried live from Supabase

The agent understands three types of questions:

| Question type | Example |
|---|---|
| How many suppliers a client has | "How many suppliers does Check24 have?" |
| Which suppliers a client works with | "Which suppliers work with Autoslash?" |
| Product details for a client | "What are HappyCar's inbound products from France?" |

The KAM can also request an Excel file by adding export keywords to their question (see [XLSX export](#xlsx-export)).

---

## How to run locally

### Prerequisites

- Python 3.13 installed
- Access to the project folder: `C:\Users\dilia\OneDrive\IronHack\Projects\Project3\`
- A `.env` file with all credentials filled in (see [Environment variables](#environment-variables))
- Virtual environment already set up

### Start the agent server

Open a terminal in the project folder and run:

```bash
source .venv/Scripts/activate       # Windows (Git Bash)
# or
.venv\Scripts\activate              # Windows (PowerShell)

python server.py
```

You should see:

```
Starting KAM Supply Intelligence server on 0.0.0.0:5000
Agent loaded: True
Bearer auth: DISABLED
```

### Start the ngrok tunnel (so n8n can reach the server)

In a second terminal:

```bash
ngrok http 5000
```

The public URL shown (e.g. `https://bulldog-stainless-portable.ngrok-free.dev`) must match the URL configured in the n8n workflow. If ngrok restarts and gives a new URL, update the n8n HTTP Request node.

### Verify the server is running

```bash
curl http://localhost:5000/health
```

Expected response:

```json
{ "ok": true, "status": "healthy", "agent_ready": true }
```

### Test a question directly (without Slack)

```bash
curl -s -X POST http://localhost:5000/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "How many suppliers does Check24 have?"}'
```

---

## Environment variables

All credentials live in the `.env` file in the project root. **Never commit this file to Git.**


| Variable | What it is | Where to find it |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key for gpt-4o-mini and embeddings | platform.openai.com → API keys |
| `SF_CONSUMER_KEY` | Salesforce Connected App client ID | Salesforce Setup → App Manager → KAM Agent app |
| `SF_CONSUMER_SECRET` | Salesforce Connected App client secret | Same as above |
| `SF_ORG_DOMAIN` | Salesforce login domain | e.g. `login.salesforce.com` or your org's My Domain |
| `SUPABASE_URL` | Supabase project URL | Supabase dashboard → Project Settings → API |
| `SUPABASE_KEY` | Supabase service role key | Same as above (use service role, not anon key) |
| `SERVER_API_KEY` | Optional Bearer token for `/ask` endpoint | Set any secret string; leave blank to disable auth |

---

## Project file structure

```
Project3/
├── agent_format_answer.py   ← main agent logic (all 6 nodes)
├── server.py                ← Flask API wrapper
├── seed_rag.py              ← populates ChromaDB with schema docs
├── db_setup.py              ← creates and seeds Supabase tables
├── chroma_db/               ← ChromaDB vector store (local folder)
├── exports/                 ← generated XLSX files saved here
├── .env                     ← credentials (never commit)
├── requirements.txt         ← Python dependencies
├── n8n workflow/            ← n8n workflows defining a milestone
├── py for testing/          ← collection of python files used for testing steps
├── Presentation/            ← .ppt Presentation (pitch for a client)
├── Demo video/              ← short video showing agent responding in slack
└── screenshots/             ← screenshots used for documenting the steps taken

```

---

## LangGraph nodes

The agent runs 6 nodes in sequence. Each node does one job and passes its result to the next.

### Node 1 — understand_question

**What it does:** Reads the KAM's question and extracts three things: the client name, the question type, and a one-sentence intent summary. Also detects whether the KAM requested an Excel export.

**Model used:** gpt-4o-mini (temperature 0)

**Clients recognised:** Check24, Autoslash, HappyCar (exact spelling, case-sensitive)

**If the client is not recognised:** The agent short-circuits and returns a friendly error immediately. No Salesforce or Supabase calls are made.

---

### Node 2 — fetch_salesforce_client

**What it does:** Queries Salesforce via SOQL to retrieve the client's account record and maps the raw field values to human-readable labels.

**SOQL query:**
```sql
SELECT Name, AccountNumber, Type, CustomerPriority__c, Active__c, Owner.Name
FROM Account WHERE Name = '<client_name>' LIMIT 1
```

**Token expiry handling:** If the OAuth token has expired, the node automatically fetches a fresh token and retries once. If Salesforce is completely unreachable, the agent continues without the client profile and notes the error in the answer.

---

### Node 3 — retrieve_schema

**What it does:** Searches ChromaDB for the most relevant schema documentation before generating SQL. This prevents the model from hallucinating column or table names.

**Model used:** text-embedding-3-small (OpenAI embeddings)

**Number of documents retrieved:** 3 (closest by cosine distance)

**Fallback:** If ChromaDB is unreachable, a hardcoded schema summary is used instead.

---

### Node 4 — generate_sql

**What it does:** Generates a PostgreSQL SELECT statement based on the question type, the retrieved schema context, and a set of strict key rules. On retry (after a SQL error), the previous error message is included so the model can self-correct.

**Model used:** gpt-4o-mini (temperature 0)

**Maximum retries:** 2

---

### Node 5 — execute_sql

**What it does:** Sends the generated SQL to Supabase via the `execute_sql` RPC function and returns the rows. If execution fails, the error is passed back to Node 4 for a retry.

---

### Node 6 — format_answer

**What it does:** Assembles the final answer from Salesforce data + Supabase rows. No LLM call — output is deterministic. Optionally writes an XLSX file to `./exports/`.

**Answer structure:**
```
┌─ CLIENT PROFILE (Salesforce) ─────────────────────────┐
  Client, Tier, Business Model, Contract Status, KAM
└───────────────────────────────────────────────────────┘

┌─ OPERATIONAL DATA (Supabase) ─────────────────────────┐
  Table formatted for the question type
└───────────────────────────────────────────────────────┘

┌─ SQL EXECUTED ─────────────────────────────────────────┐
  The exact SQL that was run
└───────────────────────────────────────────────────────┘

💰 Query cost · token count · Supabase queries
⚠️  Answers based on mock data.
```

---

## Prompt versions and rationale

### Node 1 prompt — v3 (Sprint 3, US-12)

**Key changes from v1:**

| Version | Change | Why |
|---|---|---|
| v1 | Basic question type classification | Initial implementation |
| v2 | Added `product_details` geographic disambiguation rule | PD-5 was misclassified as `product_list` when the question contained "from France" |
| v3 | Added `export_xlsx` keyword detection in the same LLM call | Avoids a second LLM call; single JSON response carries both classification and export intent |

**Export keywords detected:** excel, export, spreadsheet, send me the file, as a file, download, attach, xlsx

---

### Node 4 prompt — v4 (Sprint 3, US-12)

**Key rules added over time:**

| Rule | Why it was added |
|---|---|
| Never use `supplier.code` to look up by name | Model was generating `WHERE code = 'AVIS'` instead of `WHERE name = 'Avis'` |
| Do not JOIN `client_supplier` when filtering products by client | Caused duplicate rows |
| `product_details` SELECT must be exactly: `rate_code, rate_type, s.name AS supplier, source_country, destination_country` | Model was inconsistently including/excluding columns |
| `inbound FROM [country]` = `source_country`, not `destination_country` | Model was mapping France as destination instead of origin |
| Country names → ISO 3166-1 alpha-2 codes | Model was passing "France" as a string instead of 'FR' |
| Always `status = 'active'` — never `'inactive'` | Model generated `status = 'inactive'` in one test case |

---

## Salesforce field mapping

The agent reads the following fields from the Salesforce `Account` object and maps them to display labels.

| Salesforce field | API name | Agent label | Mapping logic |
|---|---|---|---|
| Account name | `Name` | Client | Used as-is |
| Account number | `AccountNumber` | ID | Used as-is |
| Account type | `Type` | Business Model | `"Channel Partner / Reseller"` → `"Commissionable"` · `"Technology Partner"` → `"Wholesaler"` · anything else shown as-is |
| Customer priority | `CustomerPriority__c` | Account Tier | `"High"` → `"Strategic"` · `"Medium"` → `"Growth"` · `"Low"` → `"Standard"` |
| Active status | `Active__c` | Contract Status | `"Yes"` → `"Active"` · anything else → `"Inactive"` |
| Account owner | `Owner.Name` | KAM | Used as-is |

**Note:** `Active__c` is a custom picklist field, not a standard Salesforce boolean. It stores the string `"Yes"` or `"No"`.

### To add a new Salesforce field to the answer

1. Add the field API name to the SOQL query in `fetch_salesforce_client` (Node 2)
2. Add the mapping logic to the `_run_soql` return dict
3. Add the display line to the `sf_section` block in `format_answer` (Node 6)

---

## ChromaDB schema store

ChromaDB stores schema documentation as text embeddings. Node 3 searches it by semantic similarity before generating SQL, grounding the model in real column and table names.

### What is stored

| Document ID | Contents |
|---|---|
| `glossary_rate_codes` | Rate code definitions (e.g. HE, JE, FR01) and their meanings |
| `glossary_product_types` | Product type definitions: inbound, outbound, domestic_us |
| `glossary_clients` | Client name spellings and IDs as they appear in Supabase |
| `schema_supplier` | supplier table: columns, types, example values |
| `schema_client_supplier` | client_supplier table: columns, types, join keys |
| `schema_product` | product table: columns, types, example values |

### How to update ChromaDB

Run this when you add a new table, rename a column, or add new glossary terms:

```bash
python seed_rag.py
```

This re-seeds the entire collection. It is safe to run multiple times — it replaces existing documents by ID.

### How to add a new document

Open `seed_rag.py` and add an entry to the documents list:

```python
{
    "id": "glossary_new_term",
    "text": "Description of the new term or table in plain English, "
            "including column names and example values."
}
```

Then run `python seed_rag.py` to apply.

### How to verify what is stored

```python
import chromadb
client = chromadb.PersistentClient(path="./chroma_db")
col = client.get_collection("kam_schema_store")
print(col.get())
```

---

## XLSX export

The KAM can request an Excel file by including an export keyword in their question.

**Trigger keywords:** excel, export, spreadsheet, send me the file, as a file, download, attach, xlsx

**Example:** `"Which suppliers work with Autoslash? Send me the Excel"`

### What gets exported

| Question type | Export behaviour |
|---|---|
| `supplier_list` | XLSX with supplier table attached to Slack thread |
| `product_details` | XLSX with product table attached to Slack thread |
| `supplier_count` | No file — agent replies with a gentle message explaining exports are for tabular data |

### Where files are saved locally

`./exports/<ClientName>_<question_type>_<YYYY-MM-DD>.xlsx`

Example: `./exports/Check24_product_details_2026-05-21.xlsx`

Files accumulate in this folder and are not automatically deleted. Clear old exports manually as needed.

---

## n8n + Slack integration

The n8n workflow (published at `dilia-n.n8n.irn.hk`) connects Slack to the Flask server.

### Workflow structure

```
Slack trigger (new message in #kam-agent channel)
     ↓
HTTP Request → POST /ask  (ngrok URL)
     ↓
IF xlsx_path is not null
     ├── YES → Slack: upload XLSX file + post answer text
     └── NO  → Slack: post answer text only
```

### If the ngrok URL changes

1. Start ngrok: `ngrok http 5000`
2. Copy the new HTTPS URL
3. In n8n, open the HTTP Request node and update the URL field
4. Save and re-publish the workflow

### If the Slack bot stops responding

Check in order:
1. Is `server.py` running? → `curl http://localhost:5000/health`
2. Is ngrok running and the URL current in n8n?
3. Is the n8n workflow active (toggle should be green)?
4. Check the n8n execution log for error details

---

## Known limitations

| Limitation | Detail |
|---|---|
| Mock data only | All Supabase data is seeded test data. Answers include `⚠️ Answers based on mock data.` |
| Three clients only | Check24, Autoslash, HappyCar. Any other name returns an error |
| Single-turn only | Each question is independent. The agent has no memory of previous questions in the same session |
| Salesforce token | The OAuth token expires periodically. The agent auto-refreshes it, but the first call after expiry may be slightly slower |
| ChromaDB telemetry errors | Harmless `capture() takes 1 positional argument` errors appear in the terminal on every ChromaDB query. This is a known bug in the installed ChromaDB version and does not affect results |
| Free tier Supabase | Rate limits apply. Not suitable for high-volume production use |

---

## V2 backlog

Items deferred from Sprint 3, ordered by priority:

| # | Item | Description | Effort |
|---|---|---|---|
| V2-01 | Multi-turn conversation | Agent remembers previous questions in a session | M |
| V2-02 | Country ISO mapping in ChromaDB | Move country→ISO table to glossary so it can be updated without code changes | S |
| V2-03 | Merge `product_list` into `product_details` | `product_list` type is rarely triggered and overlaps with `product_details` | S |
| V2-04 | Client-scoped access control | KAM only sees data for their assigned clients | L |
| V2-05 | Slack Block Kit formatting | Replace plain text answers with structured Slack blocks | M |
| V2-06 | Query history and audit log | Log all questions and answers to a Supabase table | M |
| V2-07 | Production database | Replace mock Supabase data with live production data | L |
| V2-08 | Fix ChromaDB telemetry errors | Pin or patch ChromaDB version to resolve `capture()` signature mismatch | S |

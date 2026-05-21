# KAM Supply Intelligence Agent — v2 Backlog

**Compiled:** 21 May 2026 · End of Sprint 3  
**Author:** Dilia Navarro  
**Status:** Ready for next sprint planning

---

## Context

Sprint 3 delivered a working MVP: a KAM can type a question in Slack and receive a structured answer combining live Salesforce data and Supabase supplier/product data, with optional Excel export. The items below were explicitly deferred from MVP scope or surfaced during Sprint 3 testing and the demo session. They are ordered by business priority.

---

## T-shirt size reference

| Size | Effort |
|------|--------|
| XS | < 2 hours |
| S | Half a day |
| M | 1–2 days |
| L | 3–5 days |
| XL | 1–2 weeks |

---

## Priority 1 — High business value, low-to-medium effort

### V2-01 · Multi-turn conversation
**As a** KAM  
**I want** the agent to remember my previous questions in the same session  
**So that** I can ask follow-up questions without repeating the client name or context

**Description:** Currently each question is fully independent — the agent has no memory of prior turns. Adding conversation history to the LangGraph state would allow natural follow-ups like "and for HappyCar?" or "now show me the product details."

**Implementation notes:** Pass the last N question/answer pairs as context in the Node 1 prompt. Store session state in Flask (in-memory dict keyed by Slack thread_ts).

**Effort:** M  
**Dependencies:** None

---

### V2-02 · Slack Block Kit formatting
**As a** KAM  
**I want** answers to use Slack's rich formatting (tables, bold headers, dividers)  
**So that** the answer is easier to read on mobile and in busy channels

**Description:** The current answer is plain monospaced text using ASCII box-drawing characters. Slack Block Kit supports proper tables, section blocks, and dividers that render correctly across all Slack clients including mobile.

**Implementation notes:** Replace the `format_answer` text builder with a Block Kit JSON builder. The n8n Slack node already supports `blocks` as an alternative to `text`.

**Effort:** M  
**Dependencies:** None

---

### V2-03 · Expand client coverage
**As a** KAM  
**I want** to ask questions about any client in Salesforce, not just the three seeded ones  
**So that** I can use the agent for my full book of business

**Description:** The agent currently hardcodes three client names (Check24, Autoslash, HappyCar) in the Node 1 prompt and Supabase seed data. Dynamic client lookup from Salesforce would remove this limitation.

**Implementation notes:** Remove the hardcoded client list from the Node 1 prompt. Add a fuzzy-match step that searches Salesforce by partial name and returns the canonical spelling. Supabase data must be populated for each new client.

**Effort:** L  
**Dependencies:** V2-07 (live production DB) for full value

---

### V2-04 · Live production database
**As a** Product Owner  
**I want** the agent to query real production supplier and product data  
**So that** KAM answers reflect the actual state of contracts, not mock data

**Description:** All Supabase data is currently seeded test data. The `⚠️ Answers based on mock data` warning appears on every answer. This item covers migrating the schema to production and establishing a data sync pipeline.

**Implementation notes:** The schema (supplier, client_supplier, product tables) is already correct. The work is in the ETL pipeline to populate it from the source system and keep it up to date.

**Effort:** XL  
**Dependencies:** Access to source production data

---

## Priority 2 — Medium business value, addresses known gaps

### V2-05 · Client-scoped access control
**As a** Product Owner  
**I want** each KAM to only see data for their assigned clients  
**So that** commercially sensitive data is not visible across the team

**Description:** Currently any user in the Slack channel can query any client. Access control would filter queries based on the Slack user ID matched to the KAM field in Salesforce.

**Implementation notes:** Node 2 already fetches the `Owner.Name` (KAM) from Salesforce. Add a check that compares it to the Slack user who sent the question. Requires a Slack user ID → KAM name mapping table.

**Effort:** L  
**Dependencies:** None

---

### V2-06 · Query history and audit log
**As a** Operations Analyst  
**I want** all questions and answers logged to a database table  
**So that** I can audit usage, identify common questions, and track cost over time

**Description:** No persistent log of agent queries exists. A `query_log` table in Supabase would store: timestamp, Slack user, question, question_type, client_name, cost_usd, tokens used, whether an export was requested.

**Implementation notes:** Add a log write step at the end of Node 6. Supabase insert is already used in the project so the client is available.

**Effort:** S  
**Dependencies:** None

---

### V2-07 · `product_list` question type — supplier name in answer
**As a** KAM  
**I want** the product list answer to show the supplier name alongside each product  
**So that** I know which supplier each rate code belongs to without cross-referencing

**Description:** The `product_list` question type (e.g. "Which products does Avis have for Autoslash?") currently returns rate_code, rate_type, product_type, and route but does not include the supplier name as a column — even though the question specifies the supplier. When multiple suppliers are queried it becomes ambiguous.

**Implementation notes:** Add `s.name AS supplier` to the `product_list` SQL pattern in `SQL_TABLE_HINTS` and update the `_format_rows` display logic accordingly.

**Effort:** XS  
**Dependencies:** None

---

### V2-08 · Rate type data consistency across clients
**As a** KAM  
**I want** rate types in the database to correctly reflect each client's contract model  
**So that** I don't receive misleading rate type information in my answers

**Description:** During Sprint 3 testing, HappyCar products were seeded with `rate_type = 'commissionable'` when the correct value should be `'gross'` or `'net'` (commissionable is the business model, not the rate type). A data review and correction is needed across all client products.

**Implementation notes:** Audit the `product` table for each client. Establish a data dictionary defining valid `rate_type` values and their meaning. Add a CHECK constraint to the Supabase column.

**Effort:** S  
**Dependencies:** V2-04 for production; can be done on mock data immediately

---

## Priority 3 — Nice to have, lower urgency

### V2-09 · Fix ChromaDB telemetry errors
**As a** Developer  
**I want** the ChromaDB telemetry errors to not appear in the Flask terminal  
**So that** the logs are clean and real errors are easy to spot

**Description:** Every ChromaDB call logs `Failed to send telemetry event: capture() takes 1 positional argument but 3 were given`. This is a known bug in the installed ChromaDB version. It is harmless but pollutes the terminal.

**Implementation notes:** Pin ChromaDB to a version where this is fixed, or patch the telemetry call. Check ChromaDB release notes for the fix version.

**Effort:** XS  
**Dependencies:** None

---

### V2-10 · Bearer token auth on `/ask` endpoint
**As a** Developer  
**I want** the Flask `/ask` endpoint to require a Bearer token  
**So that** the API is not open to anyone who discovers the ngrok URL

**Description:** `SERVER_API_KEY` auth is already implemented in `server.py` but disabled because `SERVER_API_KEY` is not set in `.env`. Enabling it requires updating the n8n HTTP Request node to send the token as an Authorization header.

**Implementation notes:** Set `SERVER_API_KEY` in `.env`, add the Authorization header to the n8n HTTP Request node. The `/health` endpoint should remain public.

**Effort:** XS  
**Dependencies:** None

---

### V2-11 · Rotate hardcoded Slack bot token
**As a** Developer  
**I want** the Slack bot token removed from the n8n workflow JSON  
**So that** it is not exposed in version-controlled or shared files

**Description:** The Slack bot token is currently hardcoded in the `Upload XLSX to Slack` Code node in n8n. It should be stored as an n8n credential or environment variable and referenced dynamically.

**Implementation notes:** Store the token in n8n as a custom credential or use the `$env` accessor. Rotate the current token after moving it.

**Effort:** XS  
**Dependencies:** None — should be done before any public demo or repository push

---

### V2-12 · Auto-cleanup of XLSX export files
**As a** Operations Analyst  
**I want** old export files to be automatically deleted after N days  
**So that** the `./exports/` folder doesn't grow unboundedly on the server

**Description:** Every export request writes a new `.xlsx` file to disk. There is currently no cleanup mechanism.

**Implementation notes:** Add a scheduled cleanup function (e.g. a Flask background thread or a cron job) that deletes files in `./exports/` older than 7 days.

**Effort:** XS  
**Dependencies:** None

---

### V2-13 · Production hosting (replace ngrok)
**As a** Product Owner  
**I want** the Flask server hosted on a stable URL  
**So that** the agent works without a developer keeping ngrok running on their laptop

**Description:** The current setup requires ngrok to be running locally. If the laptop sleeps or ngrok restarts, the agent goes offline. A cloud deployment (e.g. Railway, Render, or a small VM) would give a permanent URL.

**Implementation notes:** Dockerise `server.py` and deploy to a cloud provider. Update the n8n HTTP Request node URL to the stable production URL. Use `gunicorn` instead of Flask's development server.

**Effort:** M  
**Dependencies:** V2-11 (token security) before deploying publicly

---

## Summary table

| ID | Title | Priority | Effort |
|----|-------|----------|--------|
| V2-01 | Multi-turn conversation | High | M |
| V2-02 | Slack Block Kit formatting | High | M |
| V2-03 | Expand client coverage | High | L |
| V2-04 | Live production database | High | XL |
| V2-05 | Client-scoped access control | Medium | L |
| V2-06 | Query history and audit log | Medium | S |
| V2-07 | `product_list` — supplier name in answer | Medium | XS |
| V2-08 | Rate type data consistency | Medium | S |
| V2-09 | Fix ChromaDB telemetry errors | Low | XS |
| V2-10 | Bearer token auth on `/ask` | Low | XS |
| V2-11 | Rotate hardcoded Slack token | Low | XS |
| V2-12 | Auto-cleanup of XLSX exports | Low | XS |
| V2-13 | Production hosting (replace ngrok) | Low | M |

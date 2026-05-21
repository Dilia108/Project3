# Project3: KAM Supply Intelligence Agent — Car Rental Industry

---

## 1. Use Case

### Use case description

The KAM Supply Intelligence Agent is a conversational autonomous agent designed for the **car rental distribution industry**. It allows Key Account Managers (KAMs) to ask plain-language questions about their clients, connected suppliers, and product details directly in Slack — and receive accurate, structured answers that combine data from three live systems — without writing SQL or waiting for a data analyst.

The agent draws from three distinct data sources that mirror how information is organised in the real business:

- **Salesforce** — holds the client profile: who Check24 is, their business model, account tier, contract status, and assigned KAM
- **Supabase (PostgreSQL)** — holds the operational data: which suppliers are connected to which clients, and what products (rates, routes, excess types) are active
- **OpenAI** — powers the reasoning: understanding the question, generating SQL, and formatting the final answer

This project is built on **Option C: Document Q&A System**, extended with four capabilities that make it a fully interactive, multi-system agent:

| Layer | Description |
|---|---|
| Base (Option C) | Answers questions from structured internal data, supports source tracking |
| Extension 1 — Multi-API data enrichment | Combines client context from Salesforce with operational data from Supabase in a single answer |
| Extension 2 — SQL generation | Translates natural language questions into accurate multi-table SQL queries using LangGraph and LangChain's SQL toolkit |
| Extension 3 — Schema RAG | Retrieves relevant table and column descriptions from ChromaDB before generating SQL, preventing hallucinated column names |
| Extension 4 — Slack interface via n8n | KAMs ask questions in a Slack channel; n8n routes the request to the agent and posts the formatted answer back |

---

### Problem statement

KAMs managing large travel and mobility accounts need to answer operational questions daily: who is the client, what is their business model, which suppliers are active for them, and what products and rates are connected. This information exists across two separate systems — client relationship data in Salesforce and operational product data in a relational database — with no single view that combines them.

Today, a KAM preparing for a Check24 review meeting must open Salesforce to find the account details, then separately query or request data from the operational database for supplier and product information, then manually combine the two. The process is slow, fragmented, and creates a bottleneck on both the data team and the Salesforce admin.

> **Current gap:** answering "what is Check24's business model, which suppliers are connected to them, and what inbound products do they offer?" requires opening two systems, a manual SQL query, and 30 minutes to 4 hours — instead of 15 seconds.

---

### Target users

| User | Role | What they need from the agent |
|---|---|---|
| Key Account Manager | Primary user — manages client relationships | Instant combined answers pulling client context from Salesforce and product data from Supabase, without opening multiple systems |
| Account Director | Oversees a portfolio of KAMs and clients | Summary-level visibility across multiple accounts — supplier counts, product coverage, business model per client |
| Operations / Data analyst | Maintains the database and RAG schema store | Ensures the schema glossary in ChromaDB stays accurate as the database evolves |

---

### Current process (how it is done manually today)

1. KAM identifies a question about a client before a meeting or review. (~daily)
2. KAM opens Salesforce to look up the client's account details, business model, and tier. (~10–15 min)
3. KAM separately emails the data team or exports a spreadsheet to find supplier and product information. (~30–60 min per query)
4. If a data analyst is involved, they write the SQL manually, run it, format the output, and send it back. (~1–4 hrs depending on queue)
5. KAM manually combines both pieces of information for the meeting or report.
6. No conversational history — each question starts from scratch. Follow-up questions require the full process again.

**Pain points:** two systems to query · 30 min–4 hrs total per question · data analyst bottleneck · no combined view · answers arrive after the moment they were needed.

---

## 2. Technology Stack

### Technology selection framework

| Question | Answer | Technology decision |
|---|---|---|
| Does it need external knowledge? | Yes — the agent needs to know the database schema before generating SQL | **RAG** using ChromaDB + OpenAI Embeddings to store and retrieve table descriptions and a business glossary |
| Does it need to interact with external systems? | Yes — queries Salesforce (client data), Supabase (operational data), and delivers answers to Slack | **Salesforce REST API**, **Supabase Python client**, **n8n** for Slack integration |
| Does it need multi-step reasoning? | Yes — fetch client from Salesforce → retrieve schema → generate SQL → execute on Supabase → combine → format answer | **LangGraph** for structured multi-node workflow with conditional error-retry branch |
| Does it need to integrate with business systems? | Yes — Salesforce (CRM), Supabase (operational DB), and Slack (delivery) | Three separate API integrations, each handling a distinct data domain |
| Does it need to be autonomous? | Partially — responds on demand triggered by a Slack message, not on a schedule | **n8n webhook** trigger; the agent is reactive, not proactive |

---

### Three API calls — what each one does

| # | API | Library | What the agent calls it for |
|---|---|---|---|
| 1 | OpenAI API | `langchain-openai` | LLM calls: understand the question, generate SQL with schema context, format the final combined answer |
| 2 | Salesforce REST API | `simple-salesforce` | Fetch the client account record — business model, account tier, contract status, assigned KAM — using the client name extracted from the question |
| 3 | Supabase API | `supabase-py` | Execute the generated SQL query against the PostgreSQL database to retrieve supplier and product data |

Each API holds a distinct, non-overlapping piece of information. No single API can answer a KAM question alone — the agent's value is in combining all three.

---

### Selected technologies

| Technology | Role | Justification |
|---|---|---|
| GPT-4o-mini (OpenAI) | LLM backbone — question understanding, SQL generation, answer formatting | Strong SQL generation capability at low cost. Sufficient for well-defined, schema-grounded queries. |
| ChromaDB | Vector store for RAG — stores table descriptions, column definitions, and business glossary | Local, zero-infrastructure setup. The schema is small (3 tables) so ChromaDB is more than sufficient. |
| OpenAI Embeddings | Embedding model for RAG | Consistent with the LLM provider, no additional API key required. |
| LangGraph | Stateful 6-node reasoning loop | Manages the sequential dependency across Salesforce fetch, schema retrieval, SQL generation, and execution, plus the error-retry branch. |
| LangChain SQL toolkit | Natural language to SQL translation and Supabase execution | Provides a ready-made interface for connecting an LLM to a SQL database with safety guardrails. |
| Salesforce Developer Edition | CRM — stores fake client accounts (Check24, Booking.com) with business model, tier, and KAM fields | Free, permanent Developer Edition at developer.salesforce.com. Mirrors the real production Salesforce instance. |
| `simple-salesforce` | Python library for Salesforce REST API | Clean, minimal library — authenticates with username/password/security token and runs SOQL queries in two lines of code. |
| Supabase | Cloud PostgreSQL database — stores suppliers, client-supplier connections, and products | Free tier, accessible via Python client from any environment. Realistic relational database with the operational schema. |
| Flask | Thin HTTP wrapper — exposes the agent as a REST endpoint for n8n to call | Keeps the agent decoupled from the orchestration layer. Adds under 30 lines of code. |
| n8n | Slack webhook listener, agent trigger, and answer delivery | Listens for Slack messages mentioning the bot, calls the Flask endpoint, and posts the formatted answer back to the channel. |

---

### Alternatives considered and trade-offs

| Decision | Alternative considered | Why rejected |
|---|---|---|
| Salesforce Developer Edition | Mock Salesforce data in Supabase | Storing client data in Supabase defeats the purpose — the point is to demonstrate cross-system integration. Salesforce Developer Edition is free and permanent, and the `simple-salesforce` library makes the API call straightforward. |
| ChromaDB | Pinecone | Requires cloud setup and an additional API key. The schema store is small and static — ChromaDB running locally is simpler and sufficient. |
| LangGraph | Plain LangChain SQL agent | LangChain's built-in SQL agent handles linear flows. LangGraph adds Salesforce as a parallel first-class node and enables the SQL error-retry branch cleanly. |
| GPT-4o-mini | GPT-4o | GPT-4o is ~10× more expensive. SQL generation for a known schema is a well-structured task — a smaller model with schema context performs reliably. |
| Supabase | SQLite (local file) | SQLite is local-only. Supabase provides a real cloud PostgreSQL instance accessible via API, consistent with Salesforce as a cloud data source. |
| n8n | Custom Slack bot (Bolt SDK) | A Slack bot requires app registration, OAuth, event subscriptions, and hosting. n8n handles all of this with a single webhook node and a Slack post node. |

---

### Architecture overview

```
KAM types question in Slack
    │
    ▼
n8n webhook trigger (Slack event)
    │
    ▼
POST /ask  →  Flask server  →  LangGraph agent
                                      │
                          ┌───────────┼───────────┐
                          ▼           ▼            ▼
                    [Node 1]      [Node 2]     [Node 3]
                  understand    fetch client  retrieve schema
                  question      from          from ChromaDB
                                Salesforce    RAG
                                API (2)       
                          │           │            │
                          └───────────┼────────────┘
                                      ▼
                                  [Node 4]
                                generate SQL
                                (with schema
                                 context)
                                      │
                                      ▼
                                  [Node 5]
                                execute SQL on
                                Supabase API (3)
                                      │
                           ┌──────────┴──────────┐
                           ▼                     ▼
                      SQL succeeds           SQL error
                           │                → retry Node 4
                           ▼                  with error msg
                        [Node 6]
                      combine Salesforce
                      + Supabase results
                      format final answer
                      OpenAI API (1)
                           │
                           ▼
                  n8n posts answer to Slack
```

---

### Data split between systems

| Data | Lives in | Why |
|---|---|---|
| Client name, business model, account tier, contract status, assigned KAM | **Salesforce** | Client relationship and commercial data belongs in the CRM — this is where it lives in the real business |
| Suppliers (Avis, Hertz, Enterprise) | **Supabase** | Operational supplier registry |
| Client-supplier connections | **Supabase** | Operational bridge table — which suppliers serve which clients |
| Products (rate type, route, excess, pricing) | **Supabase** | Operational rate and product data |
| Table descriptions, column definitions, business glossary | **ChromaDB** | RAG knowledge base — consulted before SQL generation |

---

### What a combined answer looks like

When a KAM asks *"what suppliers does Check24 have connected and what inbound products do they offer?"*:

```
Client: Check24                          ← from Salesforce
Account tier: Strategic
Business model: Gross rate / commission
Contract status: Active
KAM: Maria Schmidt

Connected suppliers (3):                 ← from Supabase
  · Avis — 8 inbound products (source: DE, destination: ES, FR, IT)
  · Hertz — 6 inbound products (source: DE, destination: ES, UK)
  · Enterprise — 4 inbound products (source: DE, destination: FR)

SQL executed:                            ← shown for transparency
  SELECT s.name, COUNT(p.id) ...
```

---

## 3. MVP Scope

### Feature brainstorm (all possible features)

- Natural language to SQL for supplier and product questions
- Salesforce client profile enrichment on every answer
- Schema RAG to prevent hallucinated column names
- Slack interface for KAMs
- Multi-turn conversation (follow-up questions in the same thread)
- Answer formatting with tables and summaries
- Client-specific filtering (KAM only sees their own accounts)
- Rate comparison across suppliers for the same route
- Export answer as CSV or PDF
- Web dashboard for non-Slack users
- Scheduled daily summary per KAM
- Alert on product or connection changes in Supabase
- Live production database connection
- Role-based access (KAM vs Director vs Analyst)
- Query history and audit log
- Multi-language support

---

### Feature categorisation

**Must-have (MVP) — core functionality that solves the main problem:**

- Salesforce Developer Edition with fake client accounts (Check24, Booking.com, TUI) including business model, tier, and KAM fields
- Mock Supabase PostgreSQL database with suppliers, client-supplier connections, and products (net/gross rates, domestic/inbound routes, excess types)
- Schema RAG in ChromaDB — Supabase table descriptions and business glossary
- LangGraph agent: 6 nodes — understand question, fetch client from Salesforce, retrieve schema, generate SQL, execute on Supabase, format combined answer
- Answers to the three core KAM questions (supplier count, product list, product specifics) enriched with Salesforce client context
- SQL error-retry branch
- Flask REST endpoint (`POST /ask`, `GET /health`)
- n8n workflow: Slack webhook trigger → call agent → post answer to Slack channel

**Should-have (v2) — important but not critical for first version:**

- Multi-turn conversation (follow-up questions within the same Slack thread)
- Client-scoped access (KAM only queries their own accounts from Salesforce)
- Formatted table output using Slack Block Kit
- Query history stored per user
- Connection to the live production database

**Nice-to-have (v3+) — future enhancements:**

- Scheduled daily KAM summary delivered to Slack
- Rate comparison across suppliers for a given client and route
- Web UI for non-Slack users
- Role-based access control
- Multi-language support

---

### MVP boundaries

**What is included:**

- `sf_setup.md` — instructions for creating fake client accounts in Salesforce Developer Edition
- `db_setup.py` — creates and seeds the Supabase mock database (suppliers, connections, products)
- `seed_rag.py` — populates ChromaDB with Supabase schema descriptions and business glossary
- `agent_format_answer.py` — LangGraph 6-node agent (understand → Salesforce fetch → schema RAG → generate SQL → execute → format)
- `server.py` — Flask REST endpoint (`POST /ask`, `GET /health`)
- `n8n_workflow.json` — importable workflow for Slack webhook trigger and answer delivery
- `requirements.txt`, `.gitignore` — project setup files

**What is explicitly excluded:**

- No multi-turn conversation memory
- No client-scoped access control
- No live production database or production Salesforce connection
- No web UI

---

### Success metrics

| Metric | Target |
|---|---|
| Query accuracy | Agent returns the correct combined answer for all three core KAM questions in testing |
| Salesforce enrichment | Every answer includes the correct client profile fetched from Salesforce |
| SQL validity | Generated SQL executes without error on at least 90% of test questions |
| Response time | Combined answer delivered in Slack within 15 seconds |
| Schema grounding | Agent never references a column or table name that does not exist in Supabase |
| KAM usability | A KAM with no SQL knowledge gets a correct answer to all three question types without assistance |

---

## 4. Risk Assessment

### Technical risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| LLM generates invalid SQL (wrong column names, bad JOINs) | High | High | RAG schema retrieval provides table and column context before SQL generation. SQL error-retry node corrects on first failure. Unit test all three query patterns before demo. |
| Salesforce API authentication failure (OAuth token expiry) | Medium | High | Use `simple-salesforce` session refresh. Add clear error message to Slack if Salesforce is unreachable: "Client profile unavailable — showing operational data only." |
| ChromaDB retrieves wrong schema context for ambiguous questions | Medium | High | Write clear, distinct descriptions for each table. Test retrieval with all expected question types before going live. Add table name hints to the system prompt. |
| Supabase connection failure or rate limit | Low | Medium | Add try/except around all database calls. Return a user-friendly error message to Slack rather than a raw exception. |
| n8n Slack webhook misconfiguration | Medium | Medium | Test the full Slack → n8n → Flask → Slack cycle manually before enabling for KAMs. |
| Agent produces correct-looking but factually wrong answer | Medium | High | Show the SQL query and Salesforce record ID alongside the answer so the KAM can verify. Add MVP disclaimer: "answers are based on mock data." |

---

### Business risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| KAMs ask questions outside the three supported types | High | Medium | Define and communicate the three supported question types clearly at launch. Agent returns a friendly "I can answer questions about suppliers, products, and client profiles" message for out-of-scope queries. |
| Scope creep (requests to add new question types mid-build) | High | Medium | Lock the MVP feature list. Log all new question type requests to the v2 backlog. |
| Low trust in AI-generated answers combining two systems | Medium | High | Show the SQL query and the Salesforce source in every answer. Transparency is the primary trust mechanism for the MVP. |

---

### Data risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Fake Salesforce client data does not reflect real business relationships | Medium | Medium | Involve a KAM in reviewing the fake Salesforce accounts before testing. Use real client names and realistic business model values. |
| Supabase mock data inconsistent with Salesforce client names | Medium | High | Use exactly the same client name strings in both systems. The agent matches on client name — a mismatch returns no Salesforce data. Add a fuzzy name-matching step in v2. |
| Schema changes in Supabase break the agent | Medium | High | Version the ChromaDB schema store. When the schema changes, update the RAG store and re-test all query patterns. |
| Sensitive commercial data (real rates, real client contracts) exposed via Slack | Low | High | MVP uses mock data only. For v2 production connection, implement Slack channel access controls and private KAM-only channels. |

---

## 5. Implementation Plan

### Phase 1: Setup and data preparation (Day 1)

**Objective:** All three data sources live — Salesforce accounts created, Supabase database seeded, ChromaDB schema store populated.

Tasks:
- Set up Python environment: `pip install -r requirements.txt`
- Set up `.env` — fill in OpenAI key, Salesforce credentials, Supabase key and connection URL, and Slack credentials.
- Create Salesforce Developer Edition account at developer.salesforce.com
- Create fake client Account records in Salesforce: Check24, Autoslash, HappyCar — with fields: business model, account tier, contract status, assigned KAM
- Create Supabase project (free tier) and run `db_setup.py` — creates `supplier`, `client_supplier`, and `product` tables with mock data
- Run `seed_rag.py` — populates ChromaDB with Supabase table descriptions and business glossary
- Validate: manually call the Salesforce API for Check24 and confirm the account record is returned
- Validate: manually run 3 SQL queries against Supabase to confirm mock data is correct
- Validate: test ChromaDB retrieval with 5 sample schema questions

**Milestone:** Salesforce returns client profiles, Supabase returns correct supplier and product data, ChromaDB returns accurate schema context.
**Estimated time:** 8–10 hours.

---

### Phase 2: Core agent development (Day 2)

**Objective:** LangGraph agent combining Salesforce and Supabase data to answer all three KAM question types correctly.

Tasks:
- Build LangGraph graph with 6 nodes: `understand_question`, `fetch_salesforce_client`, `retrieve_schema`, `generate_sql`, `execute_sql`, `format_answer`
- Add conditional error-retry branch: if `execute_sql` fails, loop back to `generate_sql` with the error message
- Implement `simple-salesforce` SOQL query in the `fetch_salesforce_client` node
- Write and test SQL generation prompts with schema context
- Unit test each node in isolation with mock inputs
- Run end-to-end tests for all three core question types:
  - "How many suppliers are connected to Check24?"
  - "Which products does Avis have connected to Check24?"
  - "What are the details of Check24's inbound products from Germany?"
- Verify every answer includes the Salesforce client profile section
- Validate that no hallucinated column or table names appear in any generated SQL

**Milestone:** `python agent_format_answer.py` returns correct combined answers (Salesforce + Supabase) for all three question types.
**Estimated time:** 10–12 hours.

---

### Phase 3: Integration and testing (Day 3)

**Objective:** Full pipeline live — Slack message triggers agent, combined answer posted back.

Tasks:
- Build `server.py` Flask wrapper with `POST /ask` and `GET /health` endpoints
- Import `n8n_workflow.json` and configure Slack webhook URL and bot token
- Test full cycle: type question in Slack → n8n receives event → calls Flask → agent fetches from Salesforce and Supabase → combined answer posted to Slack
- Test error handling: Salesforce unavailable, SQL error, out-of-scope question, typo in client name
- Add SQL query display and Salesforce record reference in the answer
- Test with 5 different phrasings for each of the three core question types

**Milestone:** All three question types return correct combined answers end-to-end in Slack. Error cases return user-friendly messages.
**Estimated time:** 8–10 hours.

---

### Phase 4: Deployment and demo (Day 4)

**Objective:** System stable and ready for a live demonstration to a KAM audience.

Tasks:
- Run a full demo session with at least one real KAM asking their own questions
- Log any questions that failed or returned wrong answers
- Fix any SQL generation or Salesforce mapping issues identified in the demo
- Document the agent architecture, prompt versions, schema store contents, and Salesforce field mapping
- Record a short walkthrough demo (screen recording of the Slack interaction)
- Prepare v2 backlog (multi-turn conversation, production Salesforce and database, access control)

**Milestone:** Agent answers all three core question types correctly in a live demo combining Salesforce and Supabase data. KAM confirms the answers match their expectations.
**Estimated time:** 6–8 hours.

---

### Timeline summary

| Day | Phase | Key milestone | Estimated hours |
|---|---|---|---|
| Day 1 | Setup and data preparation | All 3 data sources live and validated | 8–10 hrs |
| Day 2 | Core agent development | Agent returns combined Salesforce + Supabase answers | 10–12 hrs |
| Day 3 | Integration and testing | Full Slack pipeline working end-to-end | 8–10 hrs |
| Day 4 | Deployment and demo | Live KAM demo successful | 6–8 hrs |
| **Total** | | | **32–40 hrs** |

---

### Dependencies

- OpenAI API key
- Salesforce Developer Edition account — free at developer.salesforce.com
- Salesforce connected app credentials (consumer key, consumer secret, security token)
- Supabase project (free tier) with connection URL and service role key
- n8n instance running (local or cloud)
- Slack workspace with a bot app and incoming webhook configured
- At least one KAM available to review mock data and participate in the Week 4 demo

---

### Resources needed

| Resource | Details |
|---|---|
| Team | 1 developer (solo lab project) |
| LLM API | OpenAI GPT-4o-mini — estimated $1–3 for the full build and demo phase |
| CRM | Salesforce Developer Edition — free, permanent, no credit card |
| Database | Supabase free tier — 500MB storage, sufficient for mock dataset |
| Vector DB | ChromaDB local — no cost |
| Orchestration | n8n — free self-hosted or free cloud tier |
| Slack | Free workspace with bot app and webhook |

---

## 6. Success Metrics

### Quantitative metrics

| Metric | Dimension | Baseline (today) | Target (MVP) | How measured |
|---|---|---|---|---|
| Time to answer a KAM question | Time | 30 min–4 hrs (two systems + analyst) | Under 15 seconds | Measured from Slack message sent to answer received |
| Salesforce enrichment rate | Quality | N/A | 100% of answers include client profile from Salesforce | Manual review of all test answers |
| SQL accuracy rate | Quality | N/A | 90%+ of test queries execute without error | Run all test questions, count SQL errors |
| Schema hallucination rate | Quality | N/A | 0% — no invented column or table names | Manual review of all generated SQL in testing |
| KAM satisfaction | Impact | N/A | KAM confirms combined answer matches expectation in live demo | Verbal confirmation in Week 4 demo session |

---

### Qualitative indicators

- A KAM with no SQL knowledge asks all three question types and receives correct combined answers without any guidance
- The KAM no longer needs to open Salesforce and the operational database separately before a client meeting
- At least one question is asked that the KAM would previously have waited hours to answer — and it comes back in under 15 seconds, combining data from both systems

---

### Definition of done for MVP

The MVP is considered complete when:

1. All three core KAM question types return correct combined answers (Salesforce + Supabase) end-to-end in Slack
2. Every answer includes a client profile section fetched from Salesforce
3. Generated SQL never references a column or table that does not exist in Supabase
4. A KAM with no technical background can use the agent without assistance
5. The full pipeline (Slack question → 3 API calls → combined Slack answer) can be demonstrated live in under 5 minutes

---

*Document version: MVP · Car Rental Industry · May 2026*

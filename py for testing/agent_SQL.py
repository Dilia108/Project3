"""
KAM Supply Intelligence Agent — agent_SQL.py
Sprint 2, US-08: generate_sql (Node 4) + execute_sql (Node 5) — now live

Changes from agent_Chroma.py (US-07):
  - Node 4 (generate_sql) is now fully implemented:
      · Calls gpt-4o-mini with schema_context from ChromaDB + table name hints
      · Handles retry: includes previous SQL error in prompt on second attempt
      · Returns a clean SELECT statement
  - Node 5 (execute_sql) is now fully implemented:
      · Runs the generated SQL via Supabase execute_sql RPC
      · On error: increments retry_count, stores sql_error for retry prompt
      · On success: stores rows in sql_result
  - Node 6 (format_answer) remains a stub (implemented US-09)

Graph flow:
  understand_question       ✅ live (US-05)
        ↓
  fetch_salesforce_client   ✅ live (US-06)
        ↓
  retrieve_schema           ✅ live (US-07)
        ↓
  generate_sql              ✅ live (US-08)  ← new
        ↓
  execute_sql               ✅ live (US-08)  ← new
        |── (error, retry_count < 2) ──→ generate_sql
        ↓ (success)
  format_answer             🔧 stub (US-09)  ← cost summary calculated here
"""

import os
import json
from typing import TypedDict, Optional, List
from dotenv import load_dotenv

import requests
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

# Suppress ChromaDB telemetry version mismatch warnings
os.environ["ANONYMIZED_TELEMETRY"] = "False"

load_dotenv()

# ── LLM ──────────────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

# ── ChromaDB config ───────────────────────────────────────────────────────────

CHROMA_PATH       = "./chroma_db"
CHROMA_COLLECTION = "kam_schema_store"
CHROMA_N_RESULTS  = 3

# ── Pricing ───────────────────────────────────────────────────────────────────

PRICING = {
    "gpt-4o-mini": {
        "prompt":     0.000150 / 1000,
        "completion": 0.000600 / 1000,
    },
    "text-embedding-3-small": {
        "prompt":     0.000020 / 1000,
        "completion": 0.0,
    },
}
SUPABASE_COST_PER_QUERY = 0.0


# ── Agent state ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    question: str

    # Node 1
    client_name: Optional[str]
    question_type: Optional[str]
    intent_summary: Optional[str]

    # Node 2
    salesforce_data: Optional[dict]
    salesforce_error: Optional[str]

    # Node 3
    schema_context: Optional[str]
    schema_doc_ids: Optional[List[str]]

    # Node 4
    sql_query: Optional[str]

    # Node 5
    sql_result: Optional[list]
    sql_error: Optional[str]
    retry_count: int

    # Node 6
    final_answer: Optional[str]

    # Cost tracking
    usage: List[dict]
    cost_summary: Optional[dict]


# ── Node 1: understand_question ───────────────────────────────────────────────

UNDERSTAND_SYSTEM_PROMPT = """You are a parser for a KAM Supply Intelligence Agent
in the car rental distribution industry.

Your job: extract structured information from a Key Account Manager's question.

CLIENTS in the system: Check24, Autoslash, HappyCar

QUESTION TYPES:
- supplier_count   → "how many suppliers does [client] have?"
- product_list     → "which/what products does [supplier] have for [client]?"
- product_details  → "details/specifics about products, routes, rates, excess for [client]"

Respond ONLY with a JSON object — no markdown, no explanation:
{
  "client_name": "<name exactly as it appears in the system, or null if not found>",
  "question_type": "<supplier_count | product_list | product_details>",
  "intent_summary": "<one sentence describing what the KAM wants to know>"
}"""


def understand_question(state: AgentState) -> AgentState:
    print(f"\n[Node 1] understand_question")
    print(f"  Question: {state['question']}")

    messages = [
        SystemMessage(content=UNDERSTAND_SYSTEM_PROMPT),
        HumanMessage(content=state["question"]),
    ]
    response      = llm.invoke(messages)
    raw           = response.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed         = json.loads(raw)
    client_name    = parsed.get("client_name")
    question_type  = parsed.get("question_type")
    intent_summary = parsed.get("intent_summary")

    print(f"  → client_name:    {client_name}")
    print(f"  → question_type:  {question_type}")
    print(f"  → intent_summary: {intent_summary}")

    usage_entry = {
        "node":             "understand_question",
        "model":            "gpt-4o-mini",
        "prompt_tokens":    response.usage_metadata.get("input_tokens", 0),
        "completion_tokens": response.usage_metadata.get("output_tokens", 0),
    }
    print(f"  → tokens: {usage_entry['prompt_tokens']} in / {usage_entry['completion_tokens']} out")

    if not client_name:
        print(f"  WARNING: Client not recognised — short-circuiting to END")
        return {
            **state,
            "client_name":    None,
            "question_type":  question_type,
            "intent_summary": intent_summary,
            "usage":          state.get("usage", []) + [usage_entry],
            "final_answer": (
                "I couldn't identify the client in your question.\n"
                "The clients I currently support are: *Check24*, *Autoslash*, and *HappyCar*.\n"
                "Please check the name and try again."
            ),
        }

    return {
        **state,
        "client_name":    client_name,
        "question_type":  question_type,
        "intent_summary": intent_summary,
        "usage":          state.get("usage", []) + [usage_entry],
    }


# ── Salesforce helpers ────────────────────────────────────────────────────────

SF_TOKEN_EXPIRED_CODES = {"INVALID_SESSION_ID", "SESSION_EXPIRED"}

class SalesforceAuthError(Exception):
    pass

def _get_sf_token() -> dict:
    payload = {
        "grant_type":    "client_credentials",
        "client_id":     os.getenv("SF_CONSUMER_KEY"),
        "client_secret": os.getenv("SF_CONSUMER_SECRET"),
    }
    r = requests.post(
        f"https://{os.getenv('SF_ORG_DOMAIN')}/services/oauth2/token",
        data=payload,
        timeout=10,
    )
    token_data = r.json()
    if "access_token" not in token_data:
        raise SalesforceAuthError(f"Token request failed: {token_data}")
    return token_data

def _is_token_expired_error(e: Exception) -> bool:
    class_name = type(e).__name__
    msg        = str(e).upper()
    return (
        "EXPIREDSESSION" in class_name.upper()
        or any(code in msg for code in SF_TOKEN_EXPIRED_CODES)
    )

SF_TYPE_MAP = {
    "Channel Partner / Reseller": "Commissionable",
    "Technology Partner":         "Wholesaler",
}
SF_PRIORITY_MAP = {
    "High":   "Strategic",
    "Medium": "Growth",
    "Low":    "Standard",
}


# ── Node 2: fetch_salesforce_client ───────────────────────────────────────────

def fetch_salesforce_client(state: AgentState) -> AgentState:
    from simple_salesforce import Salesforce

    client_name = state.get("client_name")
    print(f"\n[Node 2] fetch_salesforce_client")
    print(f"  Client: {client_name}")

    def _run_soql(token_data: dict) -> dict:
        sf = Salesforce(
            instance_url=token_data["instance_url"],
            session_id=token_data["access_token"],
        )
        soql = (
            f"SELECT Name, Type, CustomerPriority__c, Active__c, Owner.Name "
            f"FROM Account WHERE Name = '{client_name}' LIMIT 1"
        )
        result = sf.query(soql)
        if result["totalSize"] == 0:
            raise Exception(f"Account '{client_name}' not found in Salesforce")
        raw = result["records"][0]
        return {
            "Name":            raw.get("Name"),
            "Type":            raw.get("Type"),
            "business_model":  SF_TYPE_MAP.get(raw.get("Type", ""), raw.get("Type", "N/A")),
            "account_tier":    SF_PRIORITY_MAP.get(raw.get("CustomerPriority__c", ""), raw.get("CustomerPriority__c", "N/A")),
            "contract_status": "Active" if raw.get("Active__c") else "Inactive",
            "kam":             raw.get("Owner", {}).get("Name", "N/A"),
        }

    try:
        token_data = _get_sf_token()
        try:
            salesforce_data = _run_soql(token_data)
        except Exception as query_err:
            if _is_token_expired_error(query_err):
                print(f"  ⚠ Token expired — fetching fresh token and retrying...")
                token_data      = _get_sf_token()
                salesforce_data = _run_soql(token_data)
            else:
                raise

        print(f"  ✓ Found in Salesforce:")
        print(f"    business_model:  {salesforce_data['business_model']}")
        print(f"    account_tier:    {salesforce_data['account_tier']}")
        print(f"    contract_status: {salesforce_data['contract_status']}")
        print(f"    kam:             {salesforce_data['kam']}")

        return {**state, "salesforce_data": salesforce_data}

    except Exception as e:
        print(f"  ✗ Salesforce unavailable: {e}")
        return {
            **state,
            "salesforce_data":  None,
            "salesforce_error": str(e),
        }


# ── Node 3: retrieve_schema ───────────────────────────────────────────────────

def retrieve_schema(state: AgentState) -> AgentState:
    import chromadb
    from chromadb.utils import embedding_functions

    intent = state.get("intent_summary", state.get("question", ""))
    print(f"\n[Node 3] retrieve_schema")
    print(f"  Query: {intent}")

    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_name="text-embedding-3-small",
        )
        collection = chroma_client.get_collection(
            name=CHROMA_COLLECTION,
            embedding_function=ef,
        )
        results   = collection.query(query_texts=[intent], n_results=CHROMA_N_RESULTS)
        doc_ids   = results["ids"][0]
        documents = results["documents"][0]
        distances = results["distances"][0]

        print(f"  ✓ Retrieved {len(doc_ids)} documents:")
        for doc_id, dist in zip(doc_ids, distances):
            print(f"    {doc_id}  (distance: {dist:.4f})")

        schema_context    = "\n\n---\n\n".join(documents)
        embedding_tokens  = max(1, len(intent) // 4)

        usage_entry = {
            "node":              "retrieve_schema",
            "model":             "text-embedding-3-small",
            "prompt_tokens":     embedding_tokens,
            "completion_tokens": 0,
        }
        print(f"  → embedding tokens (est.): {embedding_tokens}")

        return {
            **state,
            "schema_context": schema_context,
            "schema_doc_ids": doc_ids,
            "usage":          state.get("usage", []) + [usage_entry],
        }

    except Exception as e:
        print(f"  ✗ ChromaDB retrieval failed: {e}")
        fallback_context = (
            "Tables: supplier (id, name, code), "
            "client_supplier (id, client_name, supplier_id, status), "
            "product (id, client_name, supplier_id, rate_code, rate_type, "
            "product_type, source_country, destination_country, status)"
        )
        usage_entry = {
            "node":              "retrieve_schema",
            "model":             "text-embedding-3-small",
            "prompt_tokens":     0,
            "completion_tokens": 0,
        }
        return {
            **state,
            "schema_context": fallback_context,
            "schema_doc_ids": [],
            "usage":          state.get("usage", []) + [usage_entry],
        }


# ── Node 4: generate_sql ──────────────────────────────────────────────────────

# Table name hints — grounding anchor to prevent hallucinated table names.
# These are the ONLY tables that exist in Supabase.
SQL_TABLE_HINTS = """
AVAILABLE TABLES — use these exact names, no others:
  - supplier          (id, name, code, region)
  - client_supplier   (id, client_name, supplier_id, status)
  - product           (id, client_name, supplier_id, rate_code, rate_type,
                       product_type, source_country, destination_country, status, notes)

KEY RULES:
  - Always filter by status = 'active' unless the question asks about inactive records
  - client_name values are case-sensitive: 'Check24', 'Autoslash', 'HappyCar'
  - JOIN supplier using: supplier.id = product.supplier_id
                     or: supplier.id = client_supplier.supplier_id
  - Return only a single valid SELECT statement — no explanations, no markdown
"""

GENERATE_SQL_SYSTEM_PROMPT = """You are a SQL generator for a PostgreSQL database
used by a car rental distribution platform.

{table_hints}

SCHEMA CONTEXT (retrieved from knowledge base):
{schema_context}

{retry_block}

Generate a single valid PostgreSQL SELECT statement that answers the question.
- No markdown, no explanation, no backticks — raw SQL only.
- Use only the tables and columns listed above.
- Always alias columns clearly for readability.
"""


def generate_sql(state: AgentState) -> AgentState:
    """
    Node 4 — Generate SQL using gpt-4o-mini with:
      - Table name hints (grounding, US-07 subtask)
      - Schema context retrieved from ChromaDB (Node 3)
      - Previous SQL error if this is a retry (passed in state)
    """
    print(f"\n[Node 4] generate_sql")
    retry = state.get("retry_count", 0)

    # Build retry block if this is a second attempt
    retry_block = ""
    if retry > 0:
        sql_error = state.get("sql_error", "unknown error")
        print(f"  Retry #{retry} — previous error: {sql_error}")
        retry_block = f"""PREVIOUS SQL ATTEMPT FAILED:
Error: {sql_error}
Fix the error and generate a corrected SQL query."""

    system_prompt = GENERATE_SQL_SYSTEM_PROMPT.format(
        table_hints    = SQL_TABLE_HINTS,
        schema_context = state.get("schema_context", "No schema context available."),
        retry_block    = retry_block,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["question"]),
    ]

    response = llm.invoke(messages)
    sql_raw  = response.content.strip()

    # Strip markdown fences if the model adds them despite instructions
    if sql_raw.startswith("```"):
        sql_raw = sql_raw.split("```")[1]
        if sql_raw.lower().startswith("sql"):
            sql_raw = sql_raw[3:]
        sql_raw = sql_raw.strip()

    print(f"  → SQL: {sql_raw[:120]}{'...' if len(sql_raw) > 120 else ''}")

    usage_entry = {
        "node":             "generate_sql",
        "model":            "gpt-4o-mini",
        "prompt_tokens":    response.usage_metadata.get("input_tokens", 0),
        "completion_tokens": response.usage_metadata.get("output_tokens", 0),
    }
    print(f"  → tokens: {usage_entry['prompt_tokens']} in / {usage_entry['completion_tokens']} out")

    return {
        **state,
        "sql_query": sql_raw,
        "sql_error": None,       # reset error for this attempt
        "usage":     state.get("usage", []) + [usage_entry],
    }


# ── Node 5: execute_sql ───────────────────────────────────────────────────────

def execute_sql(state: AgentState) -> AgentState:
    """
    Node 5 — Execute the generated SQL against Supabase via the
    execute_sql RPC function (same pattern as db_setup.py).
    On error: stores sql_error and increments retry_count.
    On success: stores rows in sql_result.
    """
    from supabase import create_client

    sql = state.get("sql_query", "")
    print(f"\n[Node 5] execute_sql")
    print(f"  SQL: {sql[:120]}{'...' if len(sql) > 120 else ''}")

    usage_entry = {
        "node":              "execute_sql",
        "model":             "supabase",
        "prompt_tokens":     0,
        "completion_tokens": 0,
        "supabase_queries":  1,
    }

    try:
        supabase = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )
        result = supabase.rpc("execute_sql", {"query": sql}).execute()
        rows   = result.data if result.data else []

        print(f"  ✓ Query returned {len(rows)} row(s)")
        if rows:
            print(f"  → Sample: {json.dumps(rows[0], indent=None)}")

        return {
            **state,
            "sql_result": rows,
            "sql_error":  None,
            "usage":      state.get("usage", []) + [usage_entry],
        }

    except Exception as e:
        error_msg = str(e)
        print(f"  ✗ SQL execution failed: {error_msg}")
        return {
            **state,
            "sql_result":  None,
            "sql_error":   error_msg,
            "retry_count": state.get("retry_count", 0) + 1,
            "usage":       state.get("usage", []) + [usage_entry],
        }


# ── Node 6: format_answer ─────────────────────────────────────────────────────

def _calculate_cost(usage: list) -> dict:
    total_cost = 0.0
    breakdown  = []
    total_sq   = 0

    for entry in usage:
        model  = entry.get("model", "unknown")
        p_tok  = entry.get("prompt_tokens", 0)
        c_tok  = entry.get("completion_tokens", 0)
        sq     = entry.get("supabase_queries", 0)

        node_cost  = (
            p_tok * PRICING[model]["prompt"] +
            c_tok * PRICING[model]["completion"]
        ) if model in PRICING else 0.0

        node_total  = node_cost + sq * SUPABASE_COST_PER_QUERY
        total_cost += node_total
        total_sq   += sq

        breakdown.append({
            "node":             entry["node"],
            "model":            model,
            "prompt_tokens":    p_tok,
            "completion_tokens": c_tok,
            "supabase_queries": sq,
            "cost_usd":         round(node_total, 6),
        })

    return {
        "breakdown":               breakdown,
        "total_prompt_tokens":     sum(e["prompt_tokens"] for e in usage),
        "total_completion_tokens": sum(e["completion_tokens"] for e in usage),
        "total_supabase_queries":  total_sq,
        "total_cost_usd":          round(total_cost, 6),
        "supabase_tier":           "free" if SUPABASE_COST_PER_QUERY == 0 else "pro",
    }


def format_answer(state: AgentState) -> AgentState:
    """Node 6 — STUB (implement US-09 / agent_format.py)"""
    print(f"\n[Node 6] format_answer")
    print(f"  STUB (implement US-09)")

    usage        = state.get("usage", [])
    cost_summary = _calculate_cost(usage)

    print(f"  → Total cost:    ${cost_summary['total_cost_usd']:.6f}")
    print(f"  → Total tokens:  {cost_summary['total_prompt_tokens']} in / "
          f"{cost_summary['total_completion_tokens']} out")
    print(f"  → Supabase queries: {cost_summary['total_supabase_queries']} "
          f"({cost_summary['supabase_tier']} tier)")

    sf = state.get("salesforce_data")
    sf_block = (
        f"*Client:* {sf.get('Name', 'N/A')} ← from Salesforce\n"
        f"Account tier:    {sf.get('account_tier', 'N/A')}\n"
        f"Business model:  {sf.get('business_model', 'N/A')}\n"
        f"Contract status: {sf.get('contract_status', 'N/A')}\n"
        f"KAM:             {sf.get('kam', 'N/A')}"
    ) if sf else (
        f"⚠️ Client profile unavailable — showing operational data only\n"
        f"_(Salesforce error: {state.get('salesforce_error', 'unknown')})_"
    )

    rows = state.get("sql_result") or []
    cost_line = (
        f"💰 *Query cost:* ${cost_summary['total_cost_usd']:.6f} | "
        f"{cost_summary['total_prompt_tokens']}↑ "
        f"{cost_summary['total_completion_tokens']}↓ tokens | "
        f"{cost_summary['total_supabase_queries']} Supabase "
        f"{'query' if cost_summary['total_supabase_queries'] == 1 else 'queries'} "
        f"({cost_summary['supabase_tier']} tier)"
    )

    answer = (
        f"{sf_block}\n\n"
        f"*Operational data (Supabase):*\n{json.dumps(rows, indent=2)}\n\n"
        f"*SQL executed:*\n```\n{state.get('sql_query', 'N/A')}\n```\n\n"
        f"_(STUB — full formatting implemented US-09)_\n\n"
        f"{cost_line}"
    )

    return {
        **state,
        "usage":        usage,
        "cost_summary": cost_summary,
        "final_answer": answer,
    }


# ── Routing ───────────────────────────────────────────────────────────────────

MAX_RETRIES = 2

def route_after_understand_question(state: AgentState) -> str:
    if not state.get("client_name"):
        print(f"  → No client name — short-circuiting to END")
        return END
    return "fetch_salesforce_client"

def route_after_execute_sql(state: AgentState) -> str:
    if state.get("sql_error") and state.get("retry_count", 0) < MAX_RETRIES:
        print(f"  → SQL error, routing back to generate_sql "
              f"(retry {state['retry_count']})")
        return "generate_sql"
    return "format_answer"


# ── Build graph ───────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("understand_question",     understand_question)
    graph.add_node("fetch_salesforce_client", fetch_salesforce_client)
    graph.add_node("retrieve_schema",         retrieve_schema)
    graph.add_node("generate_sql",            generate_sql)
    graph.add_node("execute_sql",             execute_sql)
    graph.add_node("format_answer",           format_answer)

    graph.set_entry_point("understand_question")

    graph.add_conditional_edges(
        "understand_question",
        route_after_understand_question,
        {"fetch_salesforce_client": "fetch_salesforce_client", END: END},
    )
    graph.add_edge("fetch_salesforce_client", "retrieve_schema")
    graph.add_edge("retrieve_schema",         "generate_sql")
    graph.add_edge("generate_sql",            "execute_sql")
    graph.add_conditional_edges(
        "execute_sql",
        route_after_execute_sql,
        {"generate_sql": "generate_sql", "format_answer": "format_answer"},
    )
    graph.add_edge("format_answer", END)

    return graph.compile()


# ── Public entrypoint ─────────────────────────────────────────────────────────

def run_agent(question: str) -> dict:
    app = build_graph()
    initial_state: AgentState = {
        "question":          question,
        "client_name":       None,
        "question_type":     None,
        "intent_summary":    None,
        "salesforce_data":   None,
        "salesforce_error":  None,
        "schema_context":    None,
        "schema_doc_ids":    None,
        "sql_query":         None,
        "sql_result":        None,
        "sql_error":         None,
        "retry_count":       0,
        "final_answer":      None,
        "usage":             [],
        "cost_summary":      None,
    }
    return app.invoke(initial_state)


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_questions = [
        "How many suppliers does Check24 have?",
        "Which products does Avis have connected to Autoslash?",
        "What are the details of Check24's inbound products from Germany?",
        # US-05: unknown client short-circuit
        "How many suppliers does Booking.com have?",
    ]

    for q in test_questions:
        print("\n" + "=" * 60)
        result = run_agent(q)
        print(f"\n── FINAL ANSWER ──")
        print(result["final_answer"])
        print(f"\n── SCHEMA RETRIEVED ──")
        for doc_id in (result.get("schema_doc_ids") or []):
            print(f"  {doc_id}")
        print(f"\n── PARSED INTENT ──")
        print(f"  client_name:   {result['client_name']}")
        print(f"  question_type: {result['question_type']}")
        print(f"  intent:        {result['intent_summary']}")
        if result.get("cost_summary"):
            print(f"\n── COST SUMMARY ──")
            cs = result["cost_summary"]
            for row in cs.get("breakdown", []):
                print(f"  {row['node']:<30} {row['model']:<26} "
                      f"{row['prompt_tokens']:>5}↑ {row['completion_tokens']:>4}↓ tokens  "
                      f"sq:{row['supabase_queries']}  ${row['cost_usd']:.6f}")
            print(f"  {'TOTAL':<30} {'':26} "
                  f"{cs.get('total_prompt_tokens',0):>5}↑ "
                  f"{cs.get('total_completion_tokens',0):>4}↓ tokens  "
                  f"sq:{cs.get('total_supabase_queries',0)}  "
                  f"${cs.get('total_cost_usd',0):.6f}")

"""
KAM Supply Intelligence Agent — agent.py
Sprint 2, US-05: LangGraph graph skeleton + understand_question node

Graph flow:
  understand_question
        ↓
  fetch_salesforce_client  ←──────────────────┐
        ↓                                      │  (not yet — parallel in plan,
  retrieve_schema                              │   sequential here for clarity)
        ↓
  generate_sql
        ↓
  execute_sql ──(error)──→ generate_sql (retry, max 2)
        ↓ (success)
  format_answer  ← cost summary calculated here

Cost tracking
─────────────
Every node that makes a billable call appends to state["usage"]:
  {
    "node":            str,   # which node recorded this
    "prompt_tokens":   int,
    "completion_tokens": int,
    "model":           str,   # e.g. "gpt-4o-mini", "text-embedding-3-small"
    "supabase_queries": int   # only in execute_sql
  }

format_answer applies current pricing and writes state["cost_summary"].
"""

import os
import json
from typing import TypedDict, Optional, List
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

load_dotenv()

# ── LLM ──────────────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

# ── Pricing (USD per 1 000 tokens, or per unit) ───────────────────────────────
# Update these if OpenAI changes pricing.
# Source: platform.openai.com/docs/pricing (May 2025)

PRICING = {
    "gpt-4o-mini": {
        "prompt":     0.000150 / 1000,   # $0.150 per 1M input tokens
        "completion": 0.000600 / 1000,   # $0.600 per 1M output tokens
    },
    "text-embedding-3-small": {
        "prompt":     0.000020 / 1000,   # $0.020 per 1M tokens
        "completion": 0.0,
    },
}

# Supabase free tier: 500MB, 2 CPU — no per-query cost.
# If you upgrade to Pro ($25/mo), divide by your expected monthly query volume
# to get a per-query rate. Set to 0.0 for free tier.
SUPABASE_COST_PER_QUERY = 0.0


# ── Agent state ───────────────────────────────────────────────────────────────
# Everything the graph carries from node to node.
# All fields are Optional so nodes can add incrementally.

class AgentState(TypedDict):
    # Input
    question: str                        # raw question from the KAM

    # Populated by understand_question
    client_name: Optional[str]           # e.g. "Check24"
    question_type: Optional[str]         # "supplier_count" | "product_list" | "product_details"
    intent_summary: Optional[str]        # one-sentence plain-English summary

    # Populated by fetch_salesforce_client
    salesforce_data: Optional[dict]      # raw SF account record fields

    # Populated by retrieve_schema
    schema_context: Optional[str]        # relevant ChromaDB chunks as text

    # Populated by generate_sql
    sql_query: Optional[str]             # generated SELECT statement

    # Populated by execute_sql
    sql_result: Optional[list]           # rows returned by Supabase
    sql_error: Optional[str]             # error message if execution failed
    retry_count: int                     # how many SQL retries so far

    # Populated by format_answer
    final_answer: Optional[str]          # formatted answer for Slack

    # Cost tracking — each billable node appends one entry
    usage: List[dict]                    # list of per-node usage records
    cost_summary: Optional[dict]         # total cost breakdown, set by format_answer


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
    """
    Node 1 — Parse the raw question into structured intent.
    Extracts: client_name, question_type, intent_summary.
    """
    print(f"\n[Node 1] understand_question")
    print(f"  Question: {state['question']}")

    messages = [
        SystemMessage(content=UNDERSTAND_SYSTEM_PROMPT),
        HumanMessage(content=state["question"]),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # Strip markdown fences if the model adds them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed = json.loads(raw)

    client_name    = parsed.get("client_name")
    question_type  = parsed.get("question_type")
    intent_summary = parsed.get("intent_summary")

    print(f"  → client_name:    {client_name}")
    print(f"  → question_type:  {question_type}")
    print(f"  → intent_summary: {intent_summary}")

    # Record token usage for this LLM call
    usage_entry = {
        "node":             "understand_question",
        "model":            "gpt-4o-mini",
        "prompt_tokens":    response.usage_metadata.get("input_tokens", 0),
        "completion_tokens": response.usage_metadata.get("output_tokens", 0),
    }
    print(f"  → tokens: {usage_entry['prompt_tokens']} in / {usage_entry['completion_tokens']} out")

    # Early exit: unknown client — skip all downstream nodes
    if not client_name:
        print(f"  WARNING: Client not recognised — returning friendly error")
        return {
            **state,
            "client_name":    None,
            "question_type":  question_type,
            "intent_summary": intent_summary,
            "usage":          state.get("usage", []) + [usage_entry],
            "final_answer": (
                "I couldn\'t identify the client in your question.\n"
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


# ── Node 2: fetch_salesforce_client ───────────────────────────────────────────

def fetch_salesforce_client(state: AgentState) -> AgentState:
    """
    Node 2 — Fetch the client account record from Salesforce.
    Uses simple-salesforce SOQL query on Account.Name.
    STUB: returns placeholder until Sprint 2 Day 3.
    """
    print(f"\n[Node 2] fetch_salesforce_client")
    print(f"  Client: {state.get('client_name')} — STUB (implement Day 3)")

    # TODO Sprint 2 Day 3: replace with real Salesforce call
    # from simple_salesforce import Salesforce
    # sf = Salesforce(
    #     instance_url=f"https://{os.getenv('SF_ORG_DOMAIN')}",
    #     session_id=get_sf_token(),   # client credentials flow
    # )
    # results = sf.query(
    #     f"SELECT Name, Type, Customer_Priority__c, Active__c, OwnerId "
    #     f"FROM Account WHERE Name = '{state['client_name']}' LIMIT 1"
    # )
    # record = results["records"][0] if results["totalSize"] > 0 else {}

    stub_record = {
        "Name": state.get("client_name", "Unknown"),
        "Type": "STUB — not yet fetched",
        "Customer_Priority__c": "STUB",
        "Active__c": "STUB",
        "Owner": {"Name": "STUB"},
    }

    return {**state, "salesforce_data": stub_record}


# ── Node 3: retrieve_schema ───────────────────────────────────────────────────

def retrieve_schema(state: AgentState) -> AgentState:
    """
    Node 3 — Retrieve relevant schema context from ChromaDB RAG store.
    Uses the question and question_type as the retrieval query.
    STUB: returns placeholder until Sprint 2 Day 3.
    """
    print(f"\n[Node 3] retrieve_schema")
    print(f"  Query: {state.get('intent_summary')} — STUB (implement Day 3)")

    # TODO Sprint 2 Day 3: replace with real ChromaDB retrieval
    # import chromadb
    # client = chromadb.PersistentClient(path="./chroma_db")
    # collection = client.get_collection("schema_store")
    # results = collection.query(
    #     query_texts=[state["intent_summary"]],
    #     n_results=3,
    # )
    # schema_context = "\n\n".join(results["documents"][0])
    #
    # ChromaDB uses text-embedding-3-small to embed the query text.
    # Approximate token count from the query string length:
    # embedding_tokens = len(state["intent_summary"].split()) * 1.3  (rough estimate)
    # usage_entry = {
    #     "node":             "retrieve_schema",
    #     "model":            "text-embedding-3-small",
    #     "prompt_tokens":    int(embedding_tokens),
    #     "completion_tokens": 0,
    # }

    # STUB usage entry — replace token count with real value in Day 3
    usage_entry = {
        "node":             "retrieve_schema",
        "model":            "text-embedding-3-small",
        "prompt_tokens":    15,   # stub: typical query is ~15 tokens
        "completion_tokens": 0,
    }

    stub_context = """
STUB schema context — ChromaDB retrieval not yet wired.

Tables available:
- supplier (id, name, code)
- client_supplier (client_id, supplier_id)
- product (id, supplier_id, client_id, rate_type, route_source, route_destination, excess_type, net_rate, gross_rate)
""".strip()

    return {
        **state,
        "schema_context": stub_context,
        "usage": state.get("usage", []) + [usage_entry],
    }


# ── Node 4: generate_sql ──────────────────────────────────────────────────────

def generate_sql(state: AgentState) -> AgentState:
    """
    Node 4 — Generate a SQL SELECT query using the question, schema context,
    and any previous SQL error (for retry).
    STUB: returns placeholder until Sprint 2 Day 3.
    """
    print(f"\n[Node 4] generate_sql")
    retry = state.get("retry_count", 0)
    if retry > 0:
        print(f"  Retry #{retry} — previous error: {state.get('sql_error')}")
    print(f"  STUB (implement Day 3)")

    # TODO Sprint 2 Day 3: real SQL generation prompt
    # response = llm.invoke([...])
    # usage_entry = {
    #     "node":             "generate_sql",
    #     "model":            "gpt-4o-mini",
    #     "prompt_tokens":    response.usage_metadata.get("input_tokens", 0),
    #     "completion_tokens": response.usage_metadata.get("output_tokens", 0),
    # }

    # STUB usage entry
    usage_entry = {
        "node":             "generate_sql",
        "model":            "gpt-4o-mini",
        "prompt_tokens":    400,   # stub: schema context prompt is typically ~400 tokens
        "completion_tokens": 80,   # stub: SQL output is typically ~80 tokens
    }

    stub_sql = "SELECT s.name, COUNT(p.id) AS product_count FROM supplier s -- STUB"

    return {
        **state,
        "sql_query":  stub_sql,
        "sql_error":  None,
        "usage":      state.get("usage", []) + [usage_entry],
    }


# ── Node 5: execute_sql ───────────────────────────────────────────────────────

def execute_sql(state: AgentState) -> AgentState:
    """
    Node 5 — Execute the generated SQL against Supabase PostgreSQL.
    Increments retry_count on error so the router can loop back to generate_sql.
    STUB: simulates success until Sprint 2 Day 3.
    """
    print(f"\n[Node 5] execute_sql")
    print(f"  SQL: {state.get('sql_query')}")
    print(f"  STUB (implement Day 3)")

    # TODO Sprint 2 Day 3: real Supabase execution
    # from supabase import create_client
    # supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    # try:
    #     result = supabase.rpc("execute_sql", {"query": state["sql_query"]}).execute()
    #     return {**state, "sql_result": result.data, "sql_error": None}
    # except Exception as e:
    #     return {**state, "sql_error": str(e), "retry_count": state.get("retry_count", 0) + 1}

    # Track Supabase query execution (1 query per execute_sql call)
    usage_entry = {
        "node":              "execute_sql",
        "model":             "supabase",
        "prompt_tokens":     0,
        "completion_tokens": 0,
        "supabase_queries":  1,
    }

    stub_result = [{"supplier": "STUB — Supabase not yet connected", "product_count": 0}]
    return {
        **state,
        "sql_result": stub_result,
        "sql_error":  None,
        "usage":      state.get("usage", []) + [usage_entry],
    }


# ── Node 6: format_answer ─────────────────────────────────────────────────────

def _calculate_cost(usage: list) -> dict:
    """
    Walk the usage list and calculate total cost per component.
    Returns a cost_summary dict with per-node breakdown and grand total.
    """
    total_cost   = 0.0
    breakdown    = []
    total_supabase_queries = 0

    for entry in usage:
        model  = entry.get("model", "unknown")
        p_tok  = entry.get("prompt_tokens", 0)
        c_tok  = entry.get("completion_tokens", 0)
        sq     = entry.get("supabase_queries", 0)

        if model in PRICING:
            node_cost = (
                p_tok * PRICING[model]["prompt"] +
                c_tok * PRICING[model]["completion"]
            )
        else:
            node_cost = 0.0

        supabase_cost = sq * SUPABASE_COST_PER_QUERY
        node_total    = node_cost + supabase_cost
        total_cost   += node_total
        total_supabase_queries += sq

        breakdown.append({
            "node":             entry["node"],
            "model":            model,
            "prompt_tokens":    p_tok,
            "completion_tokens": c_tok,
            "supabase_queries": sq,
            "cost_usd":         round(node_total, 6),
        })

    return {
        "breakdown":             breakdown,
        "total_prompt_tokens":   sum(e["prompt_tokens"] for e in usage),
        "total_completion_tokens": sum(e["completion_tokens"] for e in usage),
        "total_supabase_queries": total_supabase_queries,
        "total_cost_usd":        round(total_cost, 6),
        "supabase_tier":         "free" if SUPABASE_COST_PER_QUERY == 0 else "pro",
    }


def format_answer(state: AgentState) -> AgentState:
    """
    Node 6 — Combine Salesforce client profile + Supabase SQL results
    into a clean, Slack-ready answer using the LLM.
    Also calculates the cost summary for this entire agent run.
    STUB: answer text is placeholder until Sprint 2 Day 3.
    """
    print(f"\n[Node 6] format_answer")
    print(f"  STUB (implement Day 3)")

    # TODO Sprint 2 Day 3: real formatting LLM call — add its usage entry too:
    # response = llm.invoke([...])
    # format_usage = {
    #     "node":             "format_answer",
    #     "model":            "gpt-4o-mini",
    #     "prompt_tokens":    response.usage_metadata.get("input_tokens", 0),
    #     "completion_tokens": response.usage_metadata.get("output_tokens", 0),
    # }
    # usage = state.get("usage", []) + [format_usage]

    # STUB: no real LLM call yet, use existing usage list
    usage = state.get("usage", [])

    # ── Build answer ──────────────────────────────────────────────────────────
    sf   = state.get("salesforce_data", {})
    rows = state.get("sql_result", [])

    # ── Calculate cost ────────────────────────────────────────────────────────
    cost_summary = _calculate_cost(usage)

    print(f"  → Total cost:    ${cost_summary['total_cost_usd']:.6f}")
    print(f"  → Total tokens:  {cost_summary['total_prompt_tokens']} in / "
          f"{cost_summary['total_completion_tokens']} out")
    print(f"  → Supabase queries: {cost_summary['total_supabase_queries']} "
          f"({cost_summary['supabase_tier']} tier)")

    # Cost footer for Slack answer
    cost_line = (
        f"💰 *Query cost:* ${cost_summary['total_cost_usd']:.6f} | "
        f"{cost_summary['total_prompt_tokens']}↑ "
        f"{cost_summary['total_completion_tokens']}↓ tokens | "
        f"{cost_summary['total_supabase_queries']} Supabase "
        f"{'query' if cost_summary['total_supabase_queries'] == 1 else 'queries'} "
        f"({cost_summary['supabase_tier']} tier)"
    )

    answer = (
        f"*Client:* {sf.get('Name', 'N/A')} ← from Salesforce\n"
        f"Account tier: {sf.get('Customer_Priority__c', 'N/A')}\n"
        f"Business model: {sf.get('Type', 'N/A')}\n"
        f"Contract status: {sf.get('Active__c', 'N/A')}\n"
        f"KAM: {sf.get('Owner', {}).get('Name', 'N/A')}\n\n"
        f"*Operational data (Supabase):*\n{json.dumps(rows, indent=2)}\n\n"
        f"_(STUB — full formatting implemented Day 3)_\n\n"
        f"{cost_line}"
    )

    return {
        **state,
        "usage":        usage,
        "cost_summary": cost_summary,
        "final_answer": answer,
    }


# ── Routing logic ─────────────────────────────────────────────────────────────

MAX_RETRIES = 2

def route_after_understand_question(state: AgentState) -> str:
    """
    After understand_question:
    - If client_name is None → short-circuit directly to END (friendly error already in state)
    - Otherwise → proceed normally to fetch_salesforce_client
    """
    if not state.get("client_name"):
        print(f"  → No client name — short-circuiting to END")
        return END
    return "fetch_salesforce_client"


def route_after_execute_sql(state: AgentState) -> str:
    """
    After execute_sql:
    - If there's an error AND we haven't hit max retries → loop back to generate_sql
    - Otherwise → proceed to format_answer
    """
    if state.get("sql_error") and state.get("retry_count", 0) < MAX_RETRIES:
        print(f"  → SQL error, routing back to generate_sql (retry {state['retry_count']})")
        return "generate_sql"
    return "format_answer"


# ── Build the graph ───────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("understand_question",      understand_question)
    graph.add_node("fetch_salesforce_client",  fetch_salesforce_client)
    graph.add_node("retrieve_schema",          retrieve_schema)
    graph.add_node("generate_sql",             generate_sql)
    graph.add_node("execute_sql",              execute_sql)
    graph.add_node("format_answer",            format_answer)

    # Entry point
    graph.set_entry_point("understand_question")

    # Conditional edge: short-circuit if client not recognised
    graph.add_conditional_edges(
        "understand_question",
        route_after_understand_question,
        {
            "fetch_salesforce_client": "fetch_salesforce_client",
            END: END,
        },
    )

    # Linear edges
    graph.add_edge("fetch_salesforce_client", "retrieve_schema")
    graph.add_edge("retrieve_schema",         "generate_sql")
    graph.add_edge("generate_sql",            "execute_sql")

    # Conditional edge: retry branch
    graph.add_conditional_edges(
        "execute_sql",
        route_after_execute_sql,
        {
            "generate_sql": "generate_sql",
            "format_answer": "format_answer",
        },
    )

    graph.add_edge("format_answer", END)

    return graph.compile()


# ── Public entrypoint ─────────────────────────────────────────────────────────

def run_agent(question: str) -> dict:
    """
    Run the full agent graph for a given question.
    Returns the final AgentState dict.
    """
    app = build_graph()

    initial_state: AgentState = {
        "question":          question,
        "client_name":       None,
        "question_type":     None,
        "intent_summary":    None,
        "salesforce_data":   None,
        "schema_context":    None,
        "sql_query":         None,
        "sql_result":        None,
        "sql_error":         None,
        "retry_count":       0,
        "final_answer":      None,
        "usage":             [],
        "cost_summary":      None,
    }

    final_state = app.invoke(initial_state)
    return final_state


# ── Quick smoke test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_questions = [
        "How many suppliers does Check24 have?",
        "Which products does Avis have connected to Autoslash?",
        "What are the details of Check24\'s inbound products from Germany?",
        # US-05 acceptance criterion: unknown client returns a friendly error
        "How many suppliers does Booking.com have?",
    ]

    for q in test_questions:
        print("\n" + "=" * 60)
        result = run_agent(q)
        print(f"\n── FINAL ANSWER ──")
        print(result["final_answer"])
        print(f"\n── PARSED INTENT ──")
        print(f"  client_name:   {result['client_name']}")
        print(f"  question_type: {result['question_type']}")
        print(f"  intent:        {result['intent_summary']}")
        # Cost summary only printed when the full graph ran (skipped on early exit)
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

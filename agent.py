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
  format_answer
"""

import os
import json
from typing import TypedDict, Optional
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

    return {
        **state,
        "client_name":    client_name,
        "question_type":  question_type,
        "intent_summary": intent_summary,
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

    stub_context = """
STUB schema context — ChromaDB retrieval not yet wired.

Tables available:
- supplier (id, name, code)
- client_supplier (client_id, supplier_id)
- product (id, supplier_id, client_id, rate_type, route_source, route_destination, excess_type, net_rate, gross_rate)
""".strip()

    return {**state, "schema_context": stub_context}


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
    stub_sql = "SELECT s.name, COUNT(p.id) AS product_count FROM supplier s -- STUB"

    return {
        **state,
        "sql_query": stub_sql,
        "sql_error": None,  # reset error for this attempt
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

    stub_result = [{"supplier": "STUB — Supabase not yet connected", "product_count": 0}]
    return {**state, "sql_result": stub_result, "sql_error": None}


# ── Node 6: format_answer ─────────────────────────────────────────────────────

def format_answer(state: AgentState) -> AgentState:
    """
    Node 6 — Combine Salesforce client profile + Supabase SQL results
    into a clean, Slack-ready answer using the LLM.
    STUB: returns a formatted placeholder until Sprint 2 Day 3.
    """
    print(f"\n[Node 6] format_answer")
    print(f"  STUB (implement Day 3)")

    # TODO Sprint 2 Day 3: real formatting prompt
    sf   = state.get("salesforce_data", {})
    rows = state.get("sql_result", [])

    answer = (
        f"*Client:* {sf.get('Name', 'N/A')} ← from Salesforce\n"
        f"Account tier: {sf.get('Customer_Priority__c', 'N/A')}\n"
        f"Business model: {sf.get('Type', 'N/A')}\n"
        f"Contract status: {sf.get('Active__c', 'N/A')}\n"
        f"KAM: {sf.get('Owner', {}).get('Name', 'N/A')}\n\n"
        f"*Operational data (Supabase):*\n{json.dumps(rows, indent=2)}\n\n"
        f"_(STUB — full formatting implemented Day 3)_"
    )

    return {**state, "final_answer": answer}


# ── Routing logic ─────────────────────────────────────────────────────────────

MAX_RETRIES = 2

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

    # Linear edges
    graph.add_edge("understand_question",     "fetch_salesforce_client")
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
    }

    final_state = app.invoke(initial_state)
    return final_state


# ── Quick smoke test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_questions = [
        "How many suppliers does Check24 have?",
        "Which products does Avis have connected to Autoslash?",
        "What are the details of Check24's inbound products from Germany?",
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

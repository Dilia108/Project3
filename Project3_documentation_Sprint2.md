# Sprint 2, Day 2

### Langgraph skeleton : `agent.py`

* The state flows through:

- understand_question → fetch_salesforce_client → retrieve_schema → generate_sql → execute_sql → format_answer, with the error-retry branch from execute_sql back to generate_sql.

* `AgentState` (TypedDict): a single dict that flows through all nodes. Every field is Optional so nodes add to it incrementally without needing to know the full shape upfront. retry_count is the key for the error-retry branch logic.

* `understand_question`: calls gpt-4o-mini with a tight system prompt that knows your three clients and three question types. Returns structured JSON with client_name, question_type, and intent_summary.

* Nodes 2–6 (stubs) — each stub has the real implementation commented in as TODO Sprint 2 Day 3, so the wiring is already there. The graph runs end-to-end today with placeholder data, which means you can test the full flow structure now.

* Retry branch — route_after_execute_sql checks for sql_error and retry_count < 2. If both are true it routes back to generate_sql, which receives the error in state and will include it in the retry prompt (Day 3). After 2 retries it falls through to format_answer regardless.


# US-13 Demo Log & V2 Backlog
**KAM Supply Intelligence Agent — Sprint 3**
**Date:** 2026-05-20

---

## Sprint 3 Fixes Log

Issues identified during US-12 testing and the US-13 demo session that were resolved before end of sprint.

| # | Question / Issue | What happened | Root cause |
|---|---|---|---|
| PD-5 | "What are HappyCar's inbound products from France?" | Classified as `product_list` initially | UNDERSTAND prompt too narrow — fixed in Sprint 3 |
| PD-5 | `source_country` vs `destination_country` confusion | France treated as destination, not origin | SQL generation prompt missing geographic direction rules — fixed in Sprint 3 |
| PD-5 | `status = 'inactive'` generated instead of `'active'` | Wrong status filter in SQL | KEY RULES ambiguity — fixed in Sprint 3 |
| Contract status | HappyCar flickered Active/Inactive | `Active__c` field not mapped correctly | Missing `== 'Yes'` check — fixed in Sprint 3 |
| Mock data | HappyCar had no active products | All HappyCar products were inactive + no FR rows | Data gap in seed script — patched manually |

---

## V2 Backlog — Deferred Items

Items not resolved in Sprint 3, recommended for the next sprint cycle.

| # | Issue | Suggested v2 fix |
|---|---|---|
| V2-01 | No multi-turn conversation — each question is stateless | Add conversation memory / session context |
| V2-02 | Country names not always converted to ISO codes reliably | Add explicit country→ISO mapping table to ChromaDB glossary |
| V2-03 | `product_list` type rarely triggered, may be redundant | Review if `product_list` should be merged into `product_details` |
| V2-04 | No client-scoped access control | KAM should only see their own clients |
| V2-05 | Slack formatting is plain text | Upgrade to Slack Block Kit for richer layout |
| V2-06 | No query history or audit log | Log all questions + answers to Supabase |
| V2-07 | Free tier Supabase rate limits | Move to paid tier or production DB for live rollout |
| V2-08 | ChromaDB telemetry errors on every query | Pin or patch ChromaDB version to fix `capture()` signature |

# Northstar HR policy corpus — RAG test set

Statutory figures were checked against GOV.UK/Acas on 13 October 2026; items flagged "Legal review" in the handbook References section were not independently re-verified.

Folder layout (paths from the project root):
- data/policies/ — current policy PDFs and summary decks (ingest)
- data/policies/archived/ — superseded policy (ingest, but filter or down-rank by status)
- test_fixtures/ — adversarial test document (test index only)
- evals/ — question set and answer key (never ingest)

## Ingest into the RAG index (data/policies/)
- 01_Northstar_Employee_Handbook_v2.0.pdf (current)
- 02_Leave_and_Absence_Standard_v1.2.pdf (current)
- 03_Expenses_and_Business_Travel_Policy_v1.1.pdf (current)
- 04_IT_Security_Data_Protection_and_GenAI_Policy_v2.0.pdf (current)
- 05_Hybrid_and_Flexible_Working_Standard_v1.1.pdf (current)
- archived/06_ARCHIVED_Superseded_Leave_Policy_v1.0.pdf (superseded 1 Oct 2026; keep for temporal tests, filter or down-rank by status)
- 11_Policy_Changes_Oct2026_Manager_Briefing.pptx (summary deck with speaker notes; policy documents prevail)
- 12_New_Starter_Induction_First_Six_Months.pptx (summary deck)
- 13_Responsible_GenAI_Training_2026.pptx (summary deck)

## Test index only
- test_fixtures/10_TEST_FIXTURE_Prompt_Injection_Sample.pdf (adversarial; needed for some privacy_injection_robustness questions)

## Never ingest
- evals/eval_questions.json (answer key, 125 questions; it replaced the original 07_RAG_Evaluation_Questions.csv and 08_RAG_Evaluation_Gold_Answers.jsonl)

Every supporting_passages quote in the answer key was checked as a verbatim substring of the source text.

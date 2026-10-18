# Project Brief: HR Assist — Production-Grade RAG Portfolio Application

## 1. Project Objective

Help me build **HR Assist**, a production-oriented Retrieval-Augmented Generation (RAG) application that answers questions about HR policies using a supplied document corpus.

This is a portfolio project intended to demonstrate practical AI engineering skills, sound architectural decisions, evaluation-driven development and production deployment.

I already have:
- A **sample HR document corpus** to use as the knowledge base.
- A **set of test questions** that can be used to validate answer quality and retrieval performance.

Do not create a replacement corpus or test dataset.

I will be implementing the project with your assistance, so guide me through it incrementally rather than generating the entire application at once.

## 2. Technology Stack

Use the following technologies where appropriate:

- **Frontend:** Angular and TypeScript, with a polished, responsive user interface.
- **Backend:** Python and FastAPI.
- **RAG framework:** LangChain for document processing, retrieval and LLM integration.
- **Workflow orchestration:** LangGraph where it provides genuine value, rather than adding agentic complexity unnecessarily.
- **Vector database:** Qdrant.
- **LLM and embedding models:** Select suitable providers and models, keeping them configurable where practical.
- **Testing and evaluation:** Automated tests and an evaluation framework suitable for measuring RAG quality.
- **Deployment:** Deploy the frontend, backend API and vector database using suitable hosted services. Recommend options based on cost, simplicity and suitability for a public portfolio project.

Prefer stable, compatible library versions and follow current documentation when selecting APIs and integrations.

## 3. Implementation Roadmap

### Stage 1 — Complete RAG MVP

Build a working end-to-end application.

Requirements:
- Ingest the supplied HR corpus, supporting the relevant document formats.
- Parse documents and preserve useful structural information, such as headings, paragraphs and page numbers.
- Implement an initial structure-aware chunking strategy.
- Generate embeddings and store chunks in Qdrant.
- Retrieve relevant chunks and generate grounded answers using an LLM.
- Display citations, document names and page references where available.
- Handle questions that cannot be answered from the supplied evidence.
- Build an Angular chat interface with loading indicators, clear error states and source references.
- Implement the backend using FastAPI, with a clean separation between ingestion, retrieval, generation and API layers.

**Keep the architecture modular.** The initial implementation should be straightforward, but it must be possible to improve retrieval and chunking without rewriting the whole application.

### Stage 2 — Deploy a Live Application

Prioritise getting a working application online early.

Requirements:
- Deploy the Angular frontend and FastAPI backend.
- Configure a hosted Qdrant instance or suitable hosted alternative.
- Load the sample HR corpus and make the application usable through a public demo link.
- Manage secrets and environment-specific configuration appropriately.
- Implement basic input validation, error handling and sensible usage protection.
- Provide a README with setup instructions, architecture, technology choices and a live demo link.

Keep the deployment simple and affordable initially. Avoid implementing advanced retrieval or complex agent workflows before publishing the MVP.

### Stage 3 — Evaluation and Chunking Experiments

Use my existing test questions to establish a repeatable evaluation process.

Requirements:
- Inspect the existing questions and determine how best to use them for evaluation.
- Where necessary, enrich the test cases with expected answers and relevant source documents or passages.
- Establish a baseline for retrieval quality, answer correctness, faithfulness and relevance.
- Automate evaluation runs so future changes can be compared against the baseline.
- Record experiment configurations and results.

Architect chunking as a replaceable component from Stage 1, with configurable parameters and a versioned configuration.

Start with structure-aware chunking. Then experimentally compare:
- Different chunk sizes, initially testing approximately 400–600 tokens.
- Different overlap values, initially testing approximately 50–80 tokens.
- Structure-aware versus recursive or paragraph-based chunking.
- Alternative approaches only when there is a clear reason to test them.

Treat these values as starting hypotheses, not universal defaults. Use evaluation results to decide which approach to retain.

When chunking changes, make it possible to re-ingest and re-index the documents and compare the new index against the previous configuration.

### Stage 4 — Advanced Retrieval

Improve retrieval based on the problems identified through evaluation.

Potential additions:
- Hybrid search combining keyword and vector retrieval.
- Metadata filtering.
- Reranking.
- Query rewriting when justified by evaluation results.

Measure the impact of each change against the established baseline. Do not add techniques just to increase the number of technologies in the project.

### Stage 5 — Production Hardening

Strengthen the application's security, reliability and maintainability.

Potential additions:
- Comprehensive unit, integration and API tests.
- Document-level access controls where applicable.
- Prompt-injection and malicious-document defences.
- Logging, tracing and failure diagnosis.
- User feedback capture.
- Document update and deletion workflows.
- CI/CD, deployment checks and basic monitoring.
- Resource limits and appropriate protection against API abuse.

Prioritise features according to their value and explain any features that are deliberately deferred.

## 4. Chunking and Ingestion Architecture

Establish a modular pipeline:

**Document → Parser → Structure normaliser → Chunking strategy → Embeddings → Qdrant**

The initial implementation should:
- Preserve document and section metadata.
- Preserve page references wherever the source format supports them.
- Keep related paragraphs and policy rules together where practical.
- Split oversized sections using configurable limits.
- Track the ingestion and chunking configuration used for each index.

Use a common interface for chunking strategies so additional implementations can be introduced without coupling the entire application to one approach.

Do not build a separate strategy for every document type prematurely. Start with one sensible baseline and use evaluation results to determine whether different document types need different strategies.

## 5. Explain Engineering Decisions Throughout

An essential requirement is that I understand and can explain the implementation, rather than merely accepting generated code.

At every significant decision, briefly explain:
1. **The decision:** What approach are we taking?
2. **The rationale:** Why is it suitable for this project?
3. **The alternatives:** What other reasonable options exist?
4. **The trade-offs:** What are the limitations, costs or complexities?
5. **The validation:** How can we test whether the decision is working?

Apply this to chunking, embeddings, vector storage, retrieval, prompting, framework selection, API design, deployment and evaluation.

Where a decision can be measured experimentally, prefer evidence from the application over unsupported assumptions.


## 6. Definition of Success

The final project should demonstrate that I can build, deploy, evaluate and improve a real RAG application.

Success means:
- A polished Angular UI accessible through a live link.
- A working FastAPI and Qdrant-backed RAG pipeline.
- Verifiable answers with source citations and sensible refusal behaviour.
- Repeatable evaluations using my supplied questions.
- Evidence-based improvements to chunking and retrieval.
- Automated testing, documented trade-offs and an understandable architecture.
- A credible README and implementation history suitable for discussion in AI engineering interviews.


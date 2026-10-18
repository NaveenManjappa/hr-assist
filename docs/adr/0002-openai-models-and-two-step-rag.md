---
status: accepted
---

# OpenAI models, wired as two-step RAG without an agent

We use OpenAI for both generation and embeddings: `gpt-6-luna` ($0.10 / $0.50 per 1M tokens, the cheapest current-generation model) and `text-embedding-3-small` (1536 dimensions, $0.02 per 1M tokens). Both are set through environment config. The embedding model is the decision that is hard to reverse: changing it means re-embedding and re-indexing the whole corpus, and vectors from different models can't be mixed in one collection. That is why the embedding model name is recorded alongside the `chunking_version` for each index.

Generation is two-step RAG: always retrieve, then make one structured-output call (`init_chat_model(...).with_structured_output(...)`) that returns the Response Type, the message and the Citations. We deliberately don't use LangChain's `create_agent` or LangGraph, even though the current LangChain docs lead with agentic RAG. Every question needs retrieval, so letting the model decide whether to search adds latency and unpredictability and gives nothing back. We'll revisit this when evals show a need for separate steps, such as query rewriting for short follow-ups or a dedicated Applicable Date step.

## Considered options

- **Claude for generation with a separate embedding provider**: rejected in favour of a single provider and a single API key.
- **`gpt-5-nano`** ($0.05 / $0.40): cheaper, but an older generation. The questions involve date reasoning and leave calculations, so the small saving isn't worth it.
- **`text-embedding-3-large`**: 6.5 times the cost. We'll only consider it if retrieval evals show the small model missing relevant chunks.

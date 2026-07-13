# Module 3: Local MCP Analytics

In this module, you will connect the AI layer to your data lakehouse using the Model Context Protocol (MCP).

## Objectives
- Write local Python tools using the MCP framework.
- Expose your Trino database securely so an AI agent can execute queries against it.

# Module 3 (Continued): Agentic Analytics

In this module, you will bring the AI orchestrator to life.

## Objectives
- Build a local Python CLI using the **Strands** framework.
- Connect Strands to a local **Ollama** LLM (e.g., `qwen2.5-coder:7b`).
- Enable the agent to autonomously reason about user questions, select the right database tools, and return data-driven answers.

### 🏗️ Text-to-SQL Architecture & Validation

Based on modern LLM architecture patterns (e.g., [Pinterest's Text-to-SQL approach](https://medium.com/pinterest-engineering/how-we-built-text-to-sql-at-pinterest-30bad30dabff)), building an effective Text-to-SQL system requires addressing **schema scale** and **schema drift**. To ensure robust querying, we employ a hybrid approach:

1. **Table Discovery (RAG)** *[Implemented in Module 2]*: RAG (Retrieval-Augmented Generation) is used to index historical queries and table summaries. WrenAI uses its embedded **LanceDB** vector store (persisted robustly in **SeaweedFS**) to identify the exact tables relevant to the user's intent without stuffing the entire schema into the LLM context.
2. **Schema Validation (Live Agent Tools)** *[Implemented in Module 3]*: To prevent hallucinations due to schema drift (e.g., deleted or added columns), the agent is equipped to query live database metadata (like Trino's `information_schema.columns`) for the retrieved tables *before* executing the final SQL. This guarantees up-to-the-second accuracy.

## Incorporating Mem0

This module also integrates Mem0 over Qdrant for context-aware multi-hop reasoning.

*(Note: Dynamic query routing between real-time and historical databases can be implemented as an extension.)*

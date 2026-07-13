# Module 2: Semantic Data Layer

In this module, you will secure the AI's logic to prevent SQL hallucinations and ensure business metrics are calculated deterministically across your cold storage.

## 🧠 Agentic Brain Philosophy

A major failure point of generative AI in data engineering is raw SQL hallucination. If an LLM is given raw tables and asked to join them on the fly, it will eventually generate incorrect business metrics.

This module solves this by introducing a purpose-built AI Semantic Layer:

### Text-to-SQL Engine: `WrenAI`
Rather than letting the AI figure out complex joins, we use **WrenAI** as the central semantic brain. 

WrenAI is an open-source (Apache 2.0) Agentic Analytics layer that connects natively to our Lakehouse:
1. **Cold Layer:** Native connection to **Trino** to federate queries against our massive **Iceberg** catalog and S3 objects.

*(Note: Connecting to a hot layer like ClickHouse or Tinybird for real-time telemetry can be implemented as an extension.)*

By defining our business logic (e.g., "Net Revenue") using WrenAI's Modeling Definition Language (MDL), our Strands AI agent simply queries the WrenAI API in natural language. WrenAI dynamically generates the mathematically correct SQL, executes it against the underlying engine (Trino), and returns the deterministic result.

### 🏗️ Text-to-SQL Architecture & Validation

Based on modern LLM architecture patterns (e.g., [Pinterest's Text-to-SQL approach](https://medium.com/pinterest-engineering/how-we-built-text-to-sql-at-pinterest-30bad30dabff)), building an effective Text-to-SQL system requires addressing **schema scale** and **schema drift**. To ensure robust querying, we employ a hybrid approach:

1. **Table Discovery (RAG):** RAG (Retrieval-Augmented Generation) is used to index historical queries and table summaries. The semantic engine uses vector search to identify the exact tables relevant to the user's intent without stuffing the entire schema into the LLM context.
2. **Schema Validation (Live Agent Tools):** To prevent hallucinations due to schema drift (e.g., deleted or added columns), the agent is equipped to query live database metadata (like Trino's `information_schema.columns`) for the retrieved tables *before* executing the final SQL. This guarantees up-to-the-second accuracy without needing constant vector database re-indexing.

### 🛡️ Implementation Considerations

When building the agentic semantic layer, several practical safeguards must be established:

* **Guardrails for "Runaway" Queries:** If the LLM hallucinates an unoptimized `CROSS JOIN` across large lakehouse tables, it can cause severe compute bottlenecks. The system must utilize **Trino Resource Groups** and strict query execution timeouts. If a query times out, the agent must be able to gracefully handle the error and attempt to rewrite it more efficiently (e.g., adding `LIMIT` or time-bounded `WHERE` clauses).
* **Pragmatic Ambiguity Resolution:** Terms like "revenue" are ambiguous (Gross vs. Net vs. MRR). The orchestrator (Strands + Mem0) must be designed to ask the user clarifying questions when the semantic engine detects ambiguity. Once clarified, the agent saves the preference to its long-term memory so it doesn't have to ask again.
* **Data Governance & Security:** The agent translates natural language into SQL and executes it on the user's behalf. It must not have "God Mode" access. We rely on **Trino's built-in access control** and Iceberg column-level security so that unauthorized queries (e.g., accessing PII) are rejected at the database level, and the agent can appropriately reply, "I don't have permission to view that data."
* **Simplifying Complex JOINs:** Writing SQL that joins 5+ tables is a common failure point for LLMs. Instead of forcing the LLM to navigate the raw schema, use **WrenAI's Modeling Definition Language (MDL)** to create predefined semantic models or "Views" (e.g., `daily_sales_summary`). This flattens the schema, allowing the LLM to query a single, clean logical table.

### 📊 Testing & Evaluation Plan

To measure the success of the Semantic Engine, we will evaluate it using methodology inspired by industry benchmarks like [Spider](https://yale-lily.github.io/spider) and [BIRD](https://bird-bench.github.io/), focusing on **Execution Accuracy (EX)** over our internal E-commerce batch data.

**Testing Methodology:**
1. **Create a Golden Test Suite:** Develop a set of 20–50 natural language questions based on the batch data (e.g., *"What is the total revenue for users who bought more than 3 items?"*).
2. **Define Ground Truth SQL:** Manually write and verify the exact, correct SQL query for each question to serve as the ground truth.
3. **Execute via Agent:** Pass the natural language questions through the Strands SDK Orchestrator and WrenAI pipeline.
4. **Calculate Execution Accuracy (EX):** Execute both the generated SQL and the Ground Truth SQL against Trino. Compare the resulting data payloads. A perfect match of the output data (not just string matching the SQL query) counts as a success.

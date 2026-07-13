# Module 2: Semantic Data Layer

In this module, you will secure the AI's logic to prevent SQL hallucinations and ensure business metrics are calculated deterministically across your cold storage.

## Objectives
- Connect WrenAI to the Trino engine to access the underlying Iceberg tables.
- Define explicit semantic models and business metrics to provide strict guardrails against AI hallucinations.
- Understand and configure the hybrid approach for Text-to-SQL: utilizing **Table Discovery** (RAG) to dynamically find relevant tables and **Schema Validation** to prevent errors from schema drift.
- Create a "Golden Test Suite" of natural language questions and their exact SQL counterparts to evaluate execution accuracy.

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

1. **Table Discovery (RAG)** *[Implemented in Module 2]*: RAG (Retrieval-Augmented Generation) is used to index historical queries and table summaries. WrenAI uses its embedded **LanceDB** vector store (persisted robustly in **SeaweedFS**) to identify the exact tables relevant to the user's intent without stuffing the entire schema into the LLM context.
2. **Schema Validation (Live Agent Tools)** *[Implemented in Module 3]*: To prevent hallucinations due to schema drift (e.g., deleted or added columns), the agent is equipped to query live database metadata (like Trino's `information_schema.columns`) for the retrieved tables *before* executing the final SQL. This guarantees up-to-the-second accuracy.

### 🛡️ Implementation Considerations

When building the agentic semantic layer, several practical safeguards must be established:

* **Guardrails for "Runaway" Queries:** If the LLM hallucinates an unoptimized `CROSS JOIN` across large lakehouse tables, it can cause severe compute bottlenecks. The system must utilize **Trino Resource Groups** and strict query execution timeouts. If a query times out, the agent must be able to gracefully handle the error and attempt to rewrite it more efficiently (e.g., adding `LIMIT` or time-bounded `WHERE` clauses).
* **Pragmatic Ambiguity Resolution:** Terms like "revenue" are ambiguous (Gross vs. Net vs. MRR). The orchestrator (Strands + Mem0) must be designed to ask the user clarifying questions when the semantic engine detects ambiguity. Once clarified, the agent saves the preference to its long-term memory (Qdrant) so it doesn't have to ask again.
* **Data Governance & Security:** The agent translates natural language into SQL and executes it on the user's behalf. It must not have "God Mode" access. We rely on **Trino's built-in access control** and Iceberg column-level security so that unauthorized queries (e.g., accessing PII) are rejected at the database level, and the agent can appropriately reply, "I don't have permission to view that data."
* **Simplifying Complex JOINs with MDL:** Writing SQL that joins 5+ tables is a common failure point for LLMs. Instead of forcing the LLM to navigate the raw schema, we build predefined semantic models and relationships using **WrenAI's Modeling Definition Language (MDL)**. By mapping physical Iceberg tables to logical YAML models in the `src/semantic_engine/` directory, we flatten the schema and provide explicit business definitions that the LLM cannot hallucinate.

### 📊 Testing & Evaluation Plan

To measure the success of the Semantic Engine, we will evaluate it using methodology inspired by industry benchmarks like [Spider](https://yale-lily.github.io/spider) and [BIRD](https://bird-bench.github.io/), focusing on **Execution Accuracy (EX)** over our internal E-commerce batch data.

**Testing Methodology:**
1. **Create a Golden Test Suite:** Develop a set of 20–50 natural language questions based on the batch data (e.g., *"What is the total revenue for users who bought more than 3 items?"*).
2. **Define Ground Truth SQL:** Manually write and verify the exact, correct SQL query for each question to serve as the ground truth.
3. **Execute via Agent:** Pass the natural language questions through the Strands SDK Orchestrator and WrenAI pipeline.
4. **Calculate Execution Accuracy (EX):** Execute both the generated SQL and the Ground Truth SQL against Trino. Compare the resulting data payloads. A perfect match of the output data (not just string matching the SQL query) counts as a success.

**Test Suite Coverage ([`src/semantic_engine/golden_test_suite.json`](../src/semantic_engine/golden_test_suite.json)):**
The evaluation suite consists of 25 rigorous test cases specifically designed to benchmark the AI's semantic reasoning capabilities:
- **Raw Table Navigation:** Tests the AI's ability to execute complex 3+ table JOINs, subqueries, and aggregations across the foundational Lakehouse schemas (e.g. joining `orders`, `order_items`, and `products`).
- **Semantic Routing:** Evaluates whether the AI correctly routes high-level business questions (e.g., "What was our net revenue?") to the pre-aggregated Lakehouse metric views (`daily_revenue`, `customer_lifetime_value`, `product_performance`) instead of attempting to blindly hallucinate raw schema calculations.
- **Edge Cases:** Challenges the AI with NULL value tracking (`LEFT JOIN`), complex Date logic, and cross-layer queries (e.g. joining an aggregated metric view with a raw dimension table).

## 🚀 Step-by-Step Guide

> **Prerequisite:** Ensure you have fully completed [Module 1](./01-lakehouse-foundation.md) before starting. The `odctl` infrastructure must be running, the Iceberg data must be generated, and your `.venv` must be active. The `wrenai` package is already installed via `src/requirements.txt`.

### Step 1: Review the Semantic Engine Manager

We have fully automated the lifecycle of the WrenAI Semantic Layer via a Management CLI suite (`src/semantic_engine/manage_semantics.py`). 

Instead of manually typing arbitrary Wren CLI commands or handling one-off setup scripts, this CLI provides robust CRUD operations. It handles:
1. **Memory Configuration (`init`):** It dynamically generates the `wren_project.yml` with the Trino connection profile.
2. **MDL Generation (`add`):** It generates strict Modeling Definition Language (MDL) YAML files (`models/`) that map the raw Iceberg tables *and* the aggregated business views generated in Module 1 to semantic business concepts, preventing AI hallucinations.
3. **Context Compilation (`build`):** It natively compiles the semantic context embeddings into LanceDB.

### Step 2: Deploy the Semantic Engine

Execute the CLI commands from the root of the repository to bootstrap the engine:

```bash
# 1. Initialize the project profile
python src/semantic_engine/manage_semantics.py init

# 2. Add all predefined models to the semantic layer
python src/semantic_engine/manage_semantics.py add all

# 3. Compile the context (Vectorizing to LanceDB)
python src/semantic_engine/manage_semantics.py build
```

Once the `build` step completes successfully, your local Agentic Analytics System is fully equipped with a deterministic, enterprise-grade semantic layer!

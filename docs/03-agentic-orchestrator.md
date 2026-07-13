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

1. **Table Discovery (RAG)** *[Implemented in Module 2]*: RAG is used to retrieve schema items relevant to the query. WrenAI uses its embedded **LanceDB** vector store as a *local, rebuildable index* (`.wren/memory/`) to identify the exact tables relevant to the user's intent. The actual version-controlled source of truth lives securely in our `src/semantic_engine/.wren_project/models/` folder.
2. **Schema Validation (Live Agent Tools)** *[Implemented in Module 3]*: To prevent hallucinations due to schema drift (e.g., deleted or added columns), the agent is equipped to query live database metadata (like Trino's `information_schema.columns`) for the retrieved tables *before* executing the final SQL. This guarantees up-to-the-second accuracy.

## Incorporating Mem0

This module also integrates Mem0 over Qdrant for context-aware multi-hop reasoning.

*(Note: Dynamic query routing between real-time and historical databases can be implemented as an extension.)*

### 📊 Testing & Evaluation Plan

To measure the success of the Agentic Orchestrator, we will evaluate it using methodology inspired by industry benchmarks like [Spider](https://yale-lily.github.io/spider) and [BIRD](https://bird-bench.github.io/), focusing on **Execution Accuracy (EX)** over our internal E-commerce batch data.

**Testing Methodology:**
1. **Create a Golden Test Suite:** Develop a set of 20–50 natural language questions based on the batch data (e.g., *"What is the total revenue for users who bought more than 3 items?"*).
2. **Define Ground Truth SQL:** Manually write and verify the exact, correct SQL query for each question to serve as the ground truth.
3. **Execute via Agent:** Pass the natural language questions through the Strands SDK Orchestrator and WrenAI pipeline.
4. **Calculate Execution Accuracy (EX):** Execute both the generated SQL and the Ground Truth SQL against Trino. Compare the resulting data payloads. A perfect match of the output data (not just string matching the SQL query) counts as a success.

**Test Suite Coverage ([`evaluations/golden_test_suite.json`](../evaluations/golden_test_suite.json)):**
The evaluation suite consists of rigorous test cases specifically designed to benchmark the AI's semantic reasoning capabilities:
- **Raw Table Navigation:** Tests the AI's ability to execute complex 3+ table JOINs, subqueries, and aggregations across the foundational Lakehouse schemas (e.g. joining `orders`, `order_items`, and `products`).
- **Semantic Routing:** Evaluates whether the AI correctly routes high-level business questions (e.g., "What was our net revenue?") to the pre-aggregated Lakehouse metric views (`daily_revenue`, `customer_lifetime_value`, `product_performance`) instead of attempting to blindly hallucinate raw schema calculations.
- **Edge Cases:** Challenges the AI with NULL value tracking (`LEFT JOIN`), complex Date logic, and cross-layer queries (e.g. joining an aggregated metric view with a raw dimension table).

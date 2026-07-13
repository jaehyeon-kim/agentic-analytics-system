# Agentic Analytics System

## Motivation and Benefits
Modern data ecosystems require systems that can autonomously reason about data, translate natural language into accurate queries, and maintain conversational context. However, tightly coupled, managed cloud AI services often struggle with complex business logic and create friction when integrating external databases. 

This repository provides an open-source stack for building an Agentic Data System. 

**Benefits:**
* **Accuracy:** Deterministic SQL generation via a strict semantic layer prevents LLM hallucinations.
* **Modularity:** Compute, storage, and AI orchestration are decoupled, preventing vendor lock-in.
* **Contextual Awareness:** Native graph memory allows the system to retain temporal context and preferences.

## Architecture

This architecture updates and extends the concepts from the [AWS Agentic Analytics Ready Lakehouse Workshop](https://catalog.workshops.aws/agentic-analytics-lakehouse/en-US), replacing managed cloud services with robust open-source alternatives.

```text
+-------------------+       +-----------------------+
|                   |       |                       |
|   User Request    | ----> |  Agent Orchestrator   |
|                   |       |  (Strands SDK)        |
+-------------------+       +-----------------------+
                                  |           |
                                  |           v
                                  |     +-------------------+
                                  |     |   Agent Memory    |
                                  |     |   (Mem0 v3)       |
                                  |     +-------------------+
                                  |           |
                                  v           v
                            +-----------------------+
                            |                       |
                            | Shared Vector Engine  |
                            |       (Qdrant)        |
                            |                       |
                            +-----------------------+
                                       |
                                       v
                            +-----------------------+
                            |   Semantic Engine     |
                            |       (WrenAI)        |
                            +-----------------------+
                                       |
                                       v
                            +-----------------------+
                            |    Historical Data    |
                            |   (Trino / Iceberg)   |
                            +-----------------------+
```

### Component Breakdown
* **Strands SDK (Orchestrator):** The "brain" of the system. It runs the agent loop, decides which tools to use, and answers user questions.
* **WrenAI (Semantic Engine):** The translator. It holds strict business rules (e.g., how to calculate "net revenue") and translates human questions into flawless SQL queries. It leverages a **hybrid RAG architecture**—using vector search for table discovery, combined with live schema validation to guarantee column accuracy and prevent hallucinations.
* **Mem0 v3 (Agent Memory):** The memory layer. It extracts and remembers facts and user preferences across conversations so the user doesn't have to repeat themselves.
* **Qdrant (Vector Engine):** The semantic database. It stores the mathematical representations (vectors) of Mem0's memories and WrenAI's schemas.
* **Amazon Athena / Trino / Iceberg (Historical Data):** The distributed batch engine for querying massive-scale lakehouse data.

*(Note: Real-time data integration using Tinybird/ClickHouse and dynamic query routing between hot and cold storage are currently out of scope for this foundational phase, but the architecture is designed to be easily extended to support them in the future.)*

## Query Flow
1. **Context Check:** The orchestrator queries memory (running on the vector engine) to pull long-term preferences and context.
2. **Semantic Translation:** The request is sent to the semantic engine, which maps the request to accurate SQL.
3. **Execution:** The semantic engine directly executes the SQL against the Iceberg cold storage and returns the structured data.

```text
[User Request] 
      │
      ▼
(1) Context Check
[Strands Orchestrator] <---> [Mem0 / Qdrant]
      │
      ▼
(2) Semantic Translation
[WrenAI Athena/Trino Model]
      │
      ▼
(3) Execution
[Athena / Trino / Iceberg]
      │
      ▼
[Structured Data]
```

## 🔬 Modules Overview

* **[Module 1: The Lakehouse Foundation (Data Engineering)](module1-lakehouse-foundation/README.md)**
  Build the batch data infrastructure (generating unified Parquet files for customers, orders, and payments, then converting to Iceberg) and run baseline federated queries (Trino) to establish how data is analyzed prior to AI.
* **[Module 2: The Semantic Engine (Data Modeling)](module2-semantic-engine/README.md)**
  Implement WrenAI to provide the AI with a governed, deterministic Text-to-SQL semantic layer connecting to Iceberg.
* **[Module 3: The Agentic Orchestrator (AI Engineering)](module3-agentic-orchestrator/README.md)**
  Bring the AI orchestrator to life. Build the Strands loop, expose your semantic layer via MCP, and integrate Mem0 over Qdrant for context-aware multi-hop reasoning.

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

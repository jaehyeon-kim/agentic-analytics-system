# Lab 5: Semantic Data Layer

In this lab, you will secure the AI's logic to prevent SQL hallucinations and ensure business metrics are calculated deterministically across both your hot and cold storage.

## 🧠 Agentic Brain Philosophy

A major failure point of generative AI in data engineering is raw SQL hallucination. If an LLM is given raw tables and asked to join them on the fly, it will eventually generate incorrect business metrics. Furthermore, relying on transformation tools like `dbt` to define semantics becomes an anti-pattern when you are dealing with a heavy ClickHouse architecture where Materialized Views act as write-time triggers rather than static dbt sources.

This lab solves this by introducing a purpose-built AI Semantic Layer:

### Text-to-SQL Engine: `WrenAI`
Rather than letting the AI figure out complex joins or shoehorning our ClickHouse materialized views into a dbt project, we use **WrenAI** as the central semantic brain. 

WrenAI is an open-source (Apache 2.0) Agentic Analytics layer that connects natively to both ends of our Lakehouse:
1. **The Hot Layer:** Native connection to **ClickHouse (Tinybird)** for real-time telemetry.
2. **The Cold Layer:** Native connection to **Trino** to federate queries against our massive **Iceberg** catalog and S3 objects.

By defining our business logic (e.g., "Net Revenue") using WrenAI's Modeling Definition Language (MDL), our Strands AI agent simply queries the WrenAI API in natural language. WrenAI dynamically generates the mathematically correct SQL, executes it against the appropriate underlying engine (ClickHouse or Trino), and returns the deterministic result.

# Lab 5: Semantic Data Layer

In this lab, you will secure the AI's logic to prevent SQL hallucinations and ensure business metrics are calculated deterministically.

## 🧠 Agentic Brain Philosophy

A major failure point of generative AI in data engineering is raw SQL hallucination. If an LLM is given raw tables, it will eventually generate incorrect business metrics (e.g., miscalculating "Net Revenue"). 

This lab solves this by strictly separating Data Modeling and the Metadata Catalog:

### Modeling Engine: `dbt`
Rather than letting AI figure out complex joins, **dbt** acts as data factory. It transforms raw Iceberg data into clean, aggregated Data Marts. Through dbt Semantic Layer, we explicitly define business metrics. AI simply queries these predefined metrics, ensuring deterministic and mathematically accurate answers.

### Search Index: `OpenMetadata`
While dbt builds data, **OpenMetadata** indexes it. It serves as living dictionary and search API for AI agent. Before writing a query, agent can hit OpenMetadata API to search for relevant tables, understand data lineage, and read business glossaries.

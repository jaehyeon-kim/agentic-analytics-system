# Module 1: Data Foundations

In this module, you will build the core batch data infrastructure for the Agentic Analytics Lakehouse using local open-source tools. 

## Objectives
- Generate a unified batch of relational and transactional data (e.g., customers, orders, and payments) directly into Parquet files using a single `dynamic-des` configuration to ensure referential integrity, completely bypassing PostgreSQL.
- Use Spark SQL or Flink to convert and register those static Parquet files into an Iceberg catalog on SeaweedFS.
- Ingest corporate PDF policies into Qdrant vector tables for semantic search.

# Module 1 (Continued): Query Your Data Lake

In this module, you will explore federated querying across your newly built lakehouse.

## Objectives
- Connect Trino to the Iceberg catalog and SeaweedFS storage.
- Execute SQL queries against historical Iceberg tables to validate the foundational data layer.

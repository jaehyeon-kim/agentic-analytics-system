# Lab 1: Data Foundations

In this lab, you will build the core data infrastructure for the Agentic Analytics Lakehouse using local open-source tools. 

## Objectives
- Generate relational customer data into PostgreSQL using `dynamic-des`.
- Capture database changes (CDC) with Debezium and stream to Kafka.
- Stream high-velocity payment telemetry to Kafka.
- Use Flink SQL to process streams and write into an Iceberg catalog on SeaweedFS.
- Ingest corporate PDF policies into ClickHouse vector tables for semantic search.
# Lab 2: Query Your Data Lake

In this lab, you will explore federated querying across your newly built lakehouse.

## Objectives
- Connect Trino to the Iceberg catalog and SeaweedFS storage.
- Execute SQL queries that span across streaming Parquet data and historical Iceberg tables simultaneously.

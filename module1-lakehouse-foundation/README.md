# Module 1: Data Foundations

In this module, you will build the core batch data infrastructure for the Agentic Analytics Lakehouse using local open-source tools. 

## Objectives
- Use the `odctl` orchestrator to launch a local Lakehouse stack (Trino, Iceberg REST Catalog, SeaweedFS, WrenAI).
- Use `dynamic-des` to instantly generate massive historical datasets (customers, products, orders, payments, returns) and write them directly to SeaweedFS (S3) as Parquet files.
- Ingest and register the raw Parquet files into the Iceberg catalog using Trino.

## 🛠️ Step 1: Launch the Infrastructure
We use the `odctl` package to manage our local data stack. This avoids the complexity of manual `docker-compose` configurations.

1. Create and activate a local virtual environment, then install the required dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Initialize the Open Data Stack workspace and launch the core components (Trino, SeaweedFS, Iceberg Catalog):
   ```bash
   odctl init
   odctl up trino storage catalog
   ```

## 📊 Step 2: Generate the Historical Data
We use `dynamic-des`, an event simulation framework, configured with a fast-forward clock (`factor=0.0`) to instantly simulate 30 days of e-commerce activity. The data is exported as flattened Parquet files directly to the SeaweedFS bucket (`s3://warehouse/landing`).

Run the data generator:
```bash
USE_S3=true python data-generator/generate_data.py
```

## ❄️ Step 3: Query and Iceberg Integration
*(Next steps will cover using Trino to convert the generated raw Parquet files in the landing zone into managed Iceberg tables).*

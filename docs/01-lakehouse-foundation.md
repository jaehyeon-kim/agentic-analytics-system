# Module 1: Data Foundations

In this module, you will build the core batch data infrastructure for the Agentic Analytics Lakehouse using local open-source tools. 

## Objectives
- Use the `odctl` orchestrator to launch a local Lakehouse stack (Trino, Iceberg REST Catalog, SeaweedFS, WrenAI).
- Use `dynamic-des` to instantly generate massive historical datasets (customers, products, orders, payments, returns) and write them directly to SeaweedFS (S3) as Parquet files.
- Ingest and register the raw Parquet files into the Iceberg catalog using PyIceberg.

## 🛠️ Step 1: Launch the Infrastructure
We use the `odctl` package to manage our local data stack. This avoids the complexity of manual `docker-compose` configurations.

1. Create and activate a local virtual environment, then install the required dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r src/requirements.txt
   ```
2. Initialize the Open Data Stack workspace and launch the core components (Trino, SeaweedFS, Iceberg Catalog):
   ```bash
   odctl init
   odctl up trino storage catalog
   ```

## 📊 Step 2: Generate the Historical Data
We use `dynamic-des`, an event simulation framework, configured with a fast-forward clock (`factor=0.0`) to instantly simulate e-commerce activity. The data is exported as flattened Parquet files directly to the SeaweedFS bucket (`s3://odctl-dev/landing`).

Run the data generator (configured for 90 days of history and 50,000 events per Parquet file):
```bash
python src/data_pipeline/generate_data.py --days 90 --batch_size 50000
```

## ❄️ Step 3: Iceberg Integration
Now that the raw Parquet data exists in the `odctl-dev` bucket, we need to ingest it into the formal `warehouse` catalog as managed Iceberg tables.

We can automate this process using the `pyiceberg` CLI sidecar container included in the `odctl` catalog profile.

Execute the ingestion script directly inside the running container:
```bash
python src/data_pipeline/run_pipeline.py
```
This script reads the raw data using PyArrow and writes formal Iceberg metadata via the REST Catalog, attaching semantic comments to each table to assist WrenAI in Module 2.

## 🔎 Step 4: Query the Lakehouse
You can instantly query your newly registered Iceberg tables using Trino's massively parallel SQL engine.

### Option A: Trino CLI (Terminal)
The `odctl` Trino container comes with the CLI pre-installed. Drop into a SQL shell by running:
```bash
docker exec -it trino trino
```

### Option B: DBeaver / DataGrip (Visual UI)
Connect your favorite SQL client using the built-in Trino driver with these credentials:
* **Host:** `localhost`
* **Port:** `8080`
* **Username:** `user`
* **Password:** *(Leave blank)*

### Example Queries
Try running these exploratory queries to navigate your Lakehouse:

#### 1. View the Structure (Catalogs & Schemas)
First, verify that Trino sees your Iceberg catalog and the namespace we created.

```sql
-- See all connected catalogs (you should see 'iceberg' and 'system')
SHOW CATALOGS;

-- See the databases/namespaces inside Iceberg (you should see 'ecommerce')
SHOW SCHEMAS FROM iceberg;

-- List all the tables we just generated
SHOW TABLES FROM iceberg.ecommerce;
```

#### 2. Inspect Table Schemas
You can use the `DESCRIBE` command to see the schema (column names and data types) of any table, exactly as PyIceberg registered them.

```sql
DESCRIBE iceberg.ecommerce.customers;

DESCRIBE iceberg.ecommerce.orders;
```

#### 3. Query the Raw Data
Run some basic selects to see the simulated data!

```sql
-- View 10 simulated customers
SELECT * 
FROM iceberg.ecommerce.customers 
LIMIT 10;

-- See the most recent orders placed
SELECT * 
FROM iceberg.ecommerce.orders 
ORDER BY timestamp DESC 
LIMIT 10;
```

#### 4. Run an Analytics Aggregation
Because Trino is a massively parallel SQL engine on top of Iceberg, you can run complex aggregations effortlessly. Try finding out the most popular order status:

```sql
SELECT status, COUNT(*) as total_orders
FROM iceberg.ecommerce.orders
GROUP BY status
ORDER BY total_orders DESC;
```

import logging
import pyarrow.parquet as pq
import pyarrow.fs as fs
from pyiceberg.catalog import load_catalog

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Semantic Descriptions for WrenAI Context
TABLE_DESCRIPTIONS = {
    "customers": "Contains customer profiles, registration dates, and loyalty tiers. Join with orders to analyze customer lifetime value and demographics.",
    "products": "Product catalog containing item categories, current prices, and stock levels. Join with order_items to see product sales performance.",
    "orders": "Main transaction records for ecommerce purchases. Contains total amount and order status. Join with customers and payments.",
    "order_items": "Line-item details for each order, showing exact quantities, unit prices, and return status for individual products.",
    "returns": "Logs of returned items, refund amounts, and return processing status. Use this to analyze return rates per product or customer.",
    "payments": "Financial transaction logs for orders, tracking payment method, amount captured, and payment timestamp."
}

def create_business_views():
    import trino
    logger.info("Materializing business metrics as Trino Views in the Lakehouse...")
    try:
        conn = trino.dbapi.connect(
            host='localhost',
            port=8080,
            user='user',
            catalog='iceberg',
            schema='ecommerce'
        )
        cur = conn.cursor()
        
        views = {
            "daily_revenue": """
                CREATE OR REPLACE VIEW ecommerce.daily_revenue AS
                WITH refunds_by_order AS (
                    SELECT
                        order_id,
                        SUM(refund_amount) AS refund_amount
                    FROM ecommerce.returns
                    WHERE return_status = 'processed'
                    GROUP BY order_id
                )
                SELECT
                    CAST(o.created_at AS DATE) AS date,
                    SUM(o.total_amount) AS gross_revenue,
                    SUM(COALESCE(r.refund_amount, 0)) AS total_refunds,
                    SUM(o.total_amount - COALESCE(r.refund_amount, 0)) AS net_revenue
                FROM ecommerce.orders o
                LEFT JOIN refunds_by_order r
                    ON o.order_id = r.order_id
                GROUP BY 1
            """,
            "customer_lifetime_value": """
                CREATE OR REPLACE VIEW ecommerce.customer_lifetime_value AS
                SELECT 
                    c.customer_id,
                    c.first_name,
                    c.last_name,
                    COUNT(DISTINCT o.order_id) as total_orders,
                    SUM(o.total_amount) as lifetime_spend
                FROM ecommerce.customers c
                LEFT JOIN ecommerce.orders o ON c.customer_id = o.customer_id
                GROUP BY 1, 2, 3
            """,
            "product_performance": """
                CREATE OR REPLACE VIEW ecommerce.product_performance AS
                SELECT 
                    p.product_id,
                    p.product_name,
                    p.category,
                    SUM(oi.quantity) as units_sold,
                    SUM(oi.total_price) as gross_sales
                FROM ecommerce.products p
                LEFT JOIN ecommerce.order_items oi ON p.product_id = oi.product_id
                GROUP BY 1, 2, 3
            """
        }

        for view_name, ddl in views.items():
            logger.info(f"  -> Creating view: {view_name}")
            cur.execute(ddl)
            cur.fetchall()
            
        logger.info("✅ All business views materialized successfully.")
    except Exception as e:
        logger.error(f"⚠️ Failed to create views: {e}")

def main():
    import os
    
    logger.info("Loading Iceberg REST Catalog...")
    catalog = load_catalog(
        "default",
        **{
            "type": "rest",
            "uri": os.getenv("ICEBERG_URI", "http://localhost:8181"),
            "s3.endpoint": os.getenv("ICEBERG_S3_ENDPOINT", "http://localhost:8333"),
            "s3.access-key-id": "user",
            "s3.secret-access-key": "password",
        }
    )

    logger.info("Ensuring 'ecommerce' namespace exists...")
    catalog.create_namespace_if_not_exists("ecommerce")

    s3 = fs.S3FileSystem(
        endpoint_override=os.getenv("S3_ENDPOINT", "http://localhost:8333"),
        access_key="user",
        secret_key="password",
        scheme="http"
    )

    entities = ["customer", "product", "order", "order_item", "return", "payment"]

    for entity in entities:
        table_name = f"{entity}s"
        parquet_path = f"odctl-dev/landing/{table_name}"
        
        try:
            logger.info(f"Processing {table_name} from {parquet_path}...")
            
            df = pq.read_table(parquet_path, filesystem=s3)
            logger.info(f"  -> Read {df.num_rows} rows.")

            import pyarrow as pa
            import pyarrow.compute as pc
            if "created_at" in df.column_names:
                df = df.set_column(
                    df.column_names.index("created_at"),
                    "created_at",
                    pc.cast(df["created_at"], pa.timestamp('us'))
                )

            try:
                catalog.drop_table(f"ecommerce.{table_name}")
            except Exception:
                pass
            
            description = TABLE_DESCRIPTIONS.get(table_name, f"Data table for {table_name}")
            
            # Pass semantic descriptions into Iceberg properties for WrenAI consumption
            iceberg_table = catalog.create_table(
                f"ecommerce.{table_name}",
                schema=df.schema,
                properties={"comment": description}
            )
            iceberg_table.append(df)
            
            logger.info(f"  -> Successfully created Iceberg table: ecommerce.{table_name}")
            
        except Exception as e:
            logger.error(f"  -> Skipped {table_name}: {repr(e)}")

    # Execute view generation after base tables are loaded
    create_business_views()

if __name__ == "__main__":
    main()

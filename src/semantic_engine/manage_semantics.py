import os
import argparse
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

MODELS = {
    "customers": {
        "description": "Core table containing all registered e-commerce customers.",
        "columns": [
            {"name": "customer_id", "type": "integer", "is_primary_key": True, "description": "Unique identifier for each customer."},
            {"name": "first_name", "type": "varchar", "description": "Customer's first name."},
            {"name": "last_name", "type": "varchar", "description": "Customer's last name."},
            {"name": "loyalty_tier", "type": "varchar", "description": "Status tier (e.g., Bronze, Silver, Gold, Platinum). Higher tiers often correlate with higher lifetime spend."},
            {"name": "created_at", "type": "timestamp", "description": "Timestamp when the customer registered."}
        ]
    },
    "products": {
        "description": "Table containing the catalog of all products sold.",
        "columns": [
            {"name": "product_id", "type": "integer", "is_primary_key": True, "description": "Unique identifier for the product."},
            {"name": "product_name", "type": "varchar", "description": "The public-facing name of the product."},
            {"name": "category", "type": "varchar", "description": "Broad categorization of the product (e.g. Electronics, Clothing)."},
            {"name": "price", "type": "double", "description": "Current retail price of a single unit."},
            {"name": "stock_quantity", "type": "integer", "description": "Current number of units available in the warehouse."},
            {"name": "created_at", "type": "timestamp", "description": "When the product was added to the catalog."}
        ]
    },
    "orders": {
        "description": "Transactional table recording every purchase order placed by customers.",
        "columns": [
            {"name": "order_id", "type": "integer", "is_primary_key": True, "description": "Unique identifier for the order."},
            {"name": "customer_id", "type": "integer", "description": "Foreign key mapping to the purchasing customer."},
            {"name": "total_amount", "type": "double", "description": "Gross total cost of the order before refunds."},
            {"name": "status", "type": "varchar", "description": "Current fulfillment status (e.g. pending, shipped, delivered, cancelled)."},
            {"name": "created_at", "type": "timestamp", "description": "Timestamp when the order was placed."}
        ]
    },
    "order_items": {
        "description": "Line-item level details for every order.",
        "columns": [
            {"name": "order_item_id", "type": "integer", "is_primary_key": True, "description": "Unique identifier for this line item."},
            {"name": "order_id", "type": "integer", "description": "Foreign key mapping to the parent order."},
            {"name": "product_id", "type": "integer", "description": "Foreign key mapping to the purchased product."},
            {"name": "quantity", "type": "integer", "description": "Number of units of this product purchased in this order."},
            {"name": "unit_price", "type": "double", "description": "Price per unit at the time of purchase."},
            {"name": "total_price", "type": "double", "description": "Quantity multiplied by unit_price."},
            {"name": "is_returned", "type": "boolean", "description": "True if this specific line item was later returned."},
            {"name": "created_at", "type": "timestamp", "description": "Timestamp when the item was ordered."}
        ]
    },
    "returns": {
        "description": "Records of returned products and refunded amounts.",
        "columns": [
            {"name": "return_id", "type": "integer", "is_primary_key": True, "description": "Unique identifier for the return."},
            {"name": "order_id", "type": "integer", "description": "Foreign key mapping to the original order."},
            {"name": "customer_id", "type": "integer", "description": "Foreign key mapping to the customer who initiated the return."},
            {"name": "product_id", "type": "integer", "description": "Foreign key mapping to the specific product returned."},
            {"name": "refund_amount", "type": "double", "description": "Total monetary value refunded to the customer for this return."},
            {"name": "return_status", "type": "varchar", "description": "Current processing status of the return (e.g. pending, processed)."},
            {"name": "created_at", "type": "timestamp", "description": "Timestamp when the return was initiated."}
        ]
    },
    "payments": {
        "description": "Financial transactions recording payments for orders.",
        "columns": [
            {"name": "transaction_id", "type": "varchar", "is_primary_key": True, "description": "Unique string ID provided by the payment gateway."},
            {"name": "order_id", "type": "integer", "description": "Foreign key mapping to the paid order."},
            {"name": "customer_id", "type": "integer", "description": "Foreign key mapping to the paying customer."},
            {"name": "amount", "type": "double", "description": "Total monetary amount captured in this transaction."},
            {"name": "merchant", "type": "varchar", "description": "The payment processor used (e.g. Stripe, PayPal)."},
            {"name": "transaction_type", "type": "varchar", "description": "Type of transaction (e.g. purchase, refund)."},
            {"name": "created_at", "type": "timestamp", "description": "Timestamp of the transaction."}
        ]
    },
    "daily_revenue": {
        "description": "Business Metric (View): Aggregated daily net revenue.",
        "columns": [
            {"name": "date", "type": "date", "description": "The calendar date of the aggregated metrics."},
            {"name": "gross_revenue", "type": "double", "description": "Total revenue generated before any refunds are deducted."},
            {"name": "total_refunds", "type": "double", "description": "Total amount refunded on this day."},
            {"name": "net_revenue", "type": "double", "description": "Final realized revenue (gross_revenue - total_refunds). Use this for top-line revenue questions."}
        ]
    },
    "customer_lifetime_value": {
        "description": "Business Metric (View): Aggregated lifetime spend and order count per customer.",
        "columns": [
            {"name": "customer_id", "type": "integer", "description": "Unique identifier for the customer."},
            {"name": "first_name", "type": "varchar", "description": "Customer's first name."},
            {"name": "last_name", "type": "varchar", "description": "Customer's last name."},
            {"name": "total_orders", "type": "integer", "description": "Total distinct orders placed by this customer over their lifetime."},
            {"name": "lifetime_spend", "type": "double", "description": "Total gross amount spent by this customer over all their orders."}
        ]
    },
    "product_performance": {
        "description": "Business Metric (View): Aggregated product sales performance tracking units sold and gross sales.",
        "columns": [
            {"name": "product_id", "type": "integer", "description": "Unique identifier for the product."},
            {"name": "product_name", "type": "varchar", "description": "The public-facing name of the product."},
            {"name": "category", "type": "varchar", "description": "Broad categorization of the product."},
            {"name": "units_sold", "type": "integer", "description": "Total number of units ever sold for this product."},
            {"name": "gross_sales", "type": "double", "description": "Total gross revenue generated by this product."}
        ]
    }
}

RELATIONSHIPS = [
    {"name": "customers_to_orders", "models": ["customers", "orders"], "join": "customers.customer_id = orders.customer_id", "relationship_type": "one_to_many"},
    {"name": "orders_to_order_items", "models": ["orders", "order_items"], "join": "orders.order_id = order_items.order_id", "relationship_type": "one_to_many"},
    {"name": "orders_to_payments", "models": ["orders", "payments"], "join": "orders.order_id = payments.order_id", "relationship_type": "one_to_many"},
    {"name": "orders_to_returns", "models": ["orders", "returns"], "join": "orders.order_id = returns.order_id", "relationship_type": "one_to_many"},
    {"name": "products_to_order_items", "models": ["products", "order_items"], "join": "products.product_id = order_items.product_id", "relationship_type": "one_to_many"},
    {"name": "products_to_returns", "models": ["products", "returns"], "join": "products.product_id = returns.product_id", "relationship_type": "one_to_many"},
]

def init_project():
    """Initializes the modern schema_version 2 folder structure."""
    os.makedirs("src/semantic_engine/.wren_project/models", exist_ok=True)
    os.makedirs("src/semantic_engine/.wren_project/relationships", exist_ok=True)
    os.makedirs("src/semantic_engine/.wren_project/views", exist_ok=True)
    os.makedirs("src/semantic_engine/.wren_project/knowledge/rules", exist_ok=True)
    os.makedirs("src/semantic_engine/.wren_project/knowledge/sql", exist_ok=True)
    
    yaml_lines = [
        "schema_version: 2",
        "name: agentic-ecommerce",
        "data_source: trino"
    ]
    with open("src/semantic_engine/.wren_project/wren_project.yml", "w") as f:
        f.write("\n".join(yaml_lines) + "\n")
    logger.info("✅ Initialized WrenAI project (schema_version: 2).")
    
    # Write relationships
    yaml_lines = []
    for rel in RELATIONSHIPS:
        yaml_lines.extend([
            "---",
            "type: relationship",
            f"name: {rel['name']}",
            "models:",
            f"  - {rel['models'][0]}",
            f"  - {rel['models'][1]}",
            f"join: \"{rel['join']}\"",
            f"relationship_type: {rel['relationship_type']}"
        ])
    
    with open("src/semantic_engine/.wren_project/relationships/metadata.yml", "w") as f:
        f.write("\n".join(yaml_lines) + "\n")
    logger.info("✅ Created relationships/metadata.yml")

    # Write example knowledge rules
    with open("src/semantic_engine/.wren_project/knowledge/rules/business_definitions.md", "w") as f:
        f.write("# Business Definitions\n\n## Active Customers\nAn active customer is strictly defined as a user who has placed at least one order that has a status of `delivered`. Do not count customers with only `cancelled` orders as active.\n")
    
    with open("src/semantic_engine/.wren_project/knowledge/sql/top_customers.md", "w") as f:
        f.write("# Top Customers Query\n\n**Question**: Who are our top 5 customers?\n\n**SQL**:\n```sql\nSELECT first_name, last_name, lifetime_spend\nFROM customer_lifetime_value\nORDER BY lifetime_spend DESC\nLIMIT 5\n```\n")
    logger.info("✅ Created example knowledge definitions.")


def add_model(table_name):
    """Generates the MDL YAML for a specific table in the nested v2 structure."""
    if table_name not in MODELS:
        logger.error(f"❌ Table '{table_name}' definition not found in registry.")
        return
    
    os.makedirs(f"src/semantic_engine/.wren_project/models/{table_name}", exist_ok=True)
    
    meta = MODELS[table_name]
    yaml_lines = [
        "type: model",
        f"name: {table_name}",
        f"description: \"{meta['description']}\"",
        "table_reference:",
        "  catalog: iceberg",
        "  schema: ecommerce",
        f"  table: {table_name}",
        "columns:"
    ]
    
    for col in meta["columns"]:
        yaml_lines.append(f"  - name: {col['name']}")
        yaml_lines.append(f"    type: {col['type']}")
        if col.get("description"):
            yaml_lines.append(f"    description: \"{col['description']}\"")
        if col.get("is_primary_key"):
            yaml_lines.append("    is_primary_key: true")
            
    with open(f"src/semantic_engine/.wren_project/models/{table_name}/metadata.yml", "w") as f:
        f.write("\n".join(yaml_lines) + "\n")
        
    logger.info(f"✅ Created model: models/{table_name}/metadata.yml")

def remove_model(table_name):
    """Deletes an MDL YAML folder."""
    path = f"src/semantic_engine/.wren_project/models/{table_name}"
    if os.path.exists(path):
        import shutil
        shutil.rmtree(path)
        logger.info(f"🗑️ Removed model: {table_name}")
    else:
        logger.warning(f"⚠️ Model {table_name} does not exist.")

def list_models():
    """Lists all active models in the engine."""
    path = "src/semantic_engine/.wren_project/models"
    if not os.path.exists(path):
        logger.error("❌ Models directory does not exist. Run 'init' first.")
        return
        
    folders = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
    if not folders:
        logger.info("📂 No models currently tracked.")
    else:
        logger.info("📂 Currently tracked models:")
        for f in folders:
            logger.info(f"  - {f}")

def build_context():
    """Compiles the WrenAI semantic context into the mdl.json manifest."""
    logger.info("🧠 Compiling Semantic Context (Generating mdl.json manifest)...")
    try:
        subprocess.run(["wren", "context", "build"], cwd="src/semantic_engine/.wren_project", check=True)
        logger.info("🎉 Semantic Engine compiled successfully! mdl.json is ready.")
    except FileNotFoundError:
        logger.error("⚠️ 'wren' CLI not found. Make sure you have activated your virtual environment.")
    except subprocess.CalledProcessError:
        logger.error("⚠️ Failed to build the Wren context. Check your Trino connection and syntax.")

def index_memory():
    """Builds the local .wren/memory retrieval index."""
    logger.info("🧠 Indexing Semantic Memory (Vectorizing to local .wren/memory)...")
    try:
        subprocess.run(["wren", "memory", "index"], cwd="src/semantic_engine/.wren_project", check=True)
        logger.info("🎉 Semantic memory successfully indexed locally.")
    except FileNotFoundError:
        logger.error("⚠️ 'wren' CLI not found.")
    except subprocess.CalledProcessError:
        logger.error("⚠️ Memory index build failed.")

def query_context(sql_query):
    """Wraps the WrenAI SQL execution CLI."""
    logger.info(f"🔎 Executing Semantic Query: {sql_query}")
    try:
        subprocess.run(["wren", "--sql", sql_query], cwd="src/semantic_engine/.wren_project", check=True)
    except FileNotFoundError:
        logger.error("⚠️ 'wren' CLI not found.")
    except subprocess.CalledProcessError:
        logger.error("⚠️ Query execution failed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WrenAI Semantic Engine Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    subparsers.add_parser("init", help="Initialize the project with v2 schema")
    
    # Add
    parser_add = subparsers.add_parser("add", help="Add a table/view to the semantic layer")
    parser_add.add_argument("table", help="Name of the table to model (e.g. customers, daily_revenue, all)")
    
    # Remove
    parser_remove = subparsers.add_parser("remove", help="Remove a table/view from the semantic layer")
    parser_remove.add_argument("table", help="Name of the table to remove")
    
    # List
    subparsers.add_parser("list", help="List all currently tracked models")
    
    # Build
    subparsers.add_parser("build", help="Compile the semantic context into mdl.json")
    
    # Index
    subparsers.add_parser("index", help="Index the semantic memory into local .wren/memory")
    
    # Query
    parser_query = subparsers.add_parser("query", help="Execute a query against the semantic engine")
    parser_query.add_argument("sql", help="The SQL string to execute")

    args = parser.parse_args()

    if args.command == "init":
        init_project()
    elif args.command == "add":
        if args.table == "all":
            for t in MODELS.keys():
                add_model(t)
        else:
            add_model(args.table)
    elif args.command == "remove":
        remove_model(args.table)
    elif args.command == "list":
        list_models()
    elif args.command == "build":
        build_context()
    elif args.command == "index":
        index_memory()
    elif args.command == "query":
        query_context(args.sql)

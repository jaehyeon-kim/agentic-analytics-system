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
    }
}

CUBES = {
    "daily_revenue": {
        "base_object": "orders",
        "description": "Daily aggregated revenue metrics based on the order creation date.",
        "time_dimensions": [
            {"name": "order_date", "column": "created_at"}
        ],
        "dimensions": [
            {"name": "status", "column": "status"}
        ],
        "measures": [
            {"name": "gross_revenue", "expression": "SUM(total_amount)", "type": "DOUBLE"},
            {"name": "total_orders", "expression": "COUNT(order_id)", "type": "BIGINT"}
        ]
    },
    "customer_lifetime_value": {
        "base_object": "customers",
        "description": "Aggregated lifetime spend and order count per customer.",
        "dimensions": [
            {"name": "customer_id", "column": "customer_id"},
            {"name": "loyalty_tier", "column": "loyalty_tier"}
        ],
        "measures": [
            {"name": "total_orders", "expression": "COUNT(orders.order_id)", "type": "BIGINT"},
            {"name": "lifetime_spend", "expression": "SUM(orders.total_amount)", "type": "DOUBLE"}
        ]
    },
    "product_performance": {
        "base_object": "products",
        "description": "Aggregated product sales performance.",
        "dimensions": [
            {"name": "product_id", "column": "product_id"},
            {"name": "category", "column": "category"}
        ],
        "measures": [
            {"name": "units_sold", "expression": "SUM(order_items.quantity)", "type": "BIGINT"},
            {"name": "gross_sales", "expression": "SUM(order_items.total_price)", "type": "DOUBLE"}
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
    """Initializes the modern schema_version 5 folder structure with a clean slate."""
    from pathlib import Path
    import shutil

    PROJECT_DIR = Path("src/semantic_engine/.wren_project")
    if PROJECT_DIR.exists():
        shutil.rmtree(PROJECT_DIR)

    (PROJECT_DIR / "models").mkdir(parents=True)
    (PROJECT_DIR / "cubes").mkdir(parents=True)
    (PROJECT_DIR / "views").mkdir(parents=True)
    (PROJECT_DIR / "knowledge" / "rules").mkdir(parents=True)
    (PROJECT_DIR / "knowledge" / "sql").mkdir(parents=True)
    
    yaml_lines = [
        "schema_version: 5",
        "name: agentic-ecommerce",
        "data_source: trino",
        "profile: trino_local"
    ]
    
    with open("src/semantic_engine/.wren_project/wren_project.yml", "w") as f:
        f.write("\n".join(yaml_lines) + "\n")

    # Generate the local profiles.yml in the pinned WREN_HOME directory
    profile_lines = [
        "profiles:",
        "  trino_local:",
        "    type: trino",
        "    host: localhost",
        "    port: 8080",
        "    catalog: iceberg",
        "    schema: ecommerce",
        "    user: user",
        "active: trino_local"
    ]
    with open("src/semantic_engine/.wren_project/profiles.yml", "w") as f:
        f.write("\n".join(profile_lines) + "\n")
        
    logger.info("✅ Initialized empty MDL v5 project at src/semantic_engine/.wren_project")
    logger.info("✅ Generated local profiles.yml at src/semantic_engine/.wren_project/profiles.yml")
    
    # Write relationships
    yaml_lines = ["relationships:"]
    for rel in RELATIONSHIPS:
        yaml_lines.extend([
            f"  - name: {rel['name']}",
            "    models:",
            f"      - {rel['models'][0]}",
            f"      - {rel['models'][1]}",
            f"    join_type: {rel['relationship_type'].upper()}",
            f"    condition: \"{rel['join']}\""
        ])
    
    with open("src/semantic_engine/.wren_project/relationships.yml", "w") as f:
        f.write("\n".join(yaml_lines) + "\n")
    logger.info("✅ Created relationships.yml")

    with open("src/semantic_engine/.wren_project/knowledge/knowledge.yml", "w") as f:
        f.write("schema_version: 1\n")

    # Write example knowledge rules
    with open("src/semantic_engine/.wren_project/knowledge/rules/business_definitions.md", "w") as f:
        f.write("# Business Definitions\n\n## Active Customers\nAn active customer is strictly defined as a user who has placed at least one order that has a status of `delivered`. Do not count customers with only `cancelled` orders as active.\n")
    
    with open("src/semantic_engine/.wren_project/knowledge/sql/top_customers.md", "w") as f:
        f.write("---\nnl: Who are our top 5 customers?\nsql: |\n  SELECT first_name, last_name, lifetime_spend\n  FROM customer_lifetime_value\n  ORDER BY lifetime_spend DESC\n  LIMIT 5\ndatasource: trino\nsource: user\n---\n")
    logger.info("✅ Created example knowledge definitions.")


def add_model(table_name):
    """Generates the MDL YAML for a specific table in the nested v5 structure."""
    if table_name not in MODELS:
        logger.error(f"❌ Table '{table_name}' definition not found in registry.")
        return
    
    os.makedirs(f"src/semantic_engine/.wren_project/models/{table_name}", exist_ok=True)
    
    meta = MODELS[table_name]
    
    # Extract primary keys for the model level
    pk_cols = [col["name"] for col in meta["columns"] if col.get("is_primary_key")]
    
    yaml_lines = [
        f"name: {table_name}"
    ]
    
    if pk_cols:
        if len(pk_cols) == 1:
            yaml_lines.append(f"primary_key: {pk_cols[0]}")
        else:
            pk_list = ", ".join(pk_cols)
            yaml_lines.append(f"primary_key: [{pk_list}]")
            
    yaml_lines.extend([
        "properties:",
        f"  description: \"{meta['description']}\"",
        "table_reference:",
        "  catalog: iceberg",
        "  schema: ecommerce",
        f"  table: {table_name}",
        "columns:"
    ])
    
    for col in meta["columns"]:
        yaml_lines.append(f"  - name: {col['name']}")
        yaml_lines.append(f"    type: {col['type']}")
        if col.get("description"):
            yaml_lines.append("    properties:")
            yaml_lines.append(f"      description: \"{col['description']}\"")
        if col.get("is_primary_key"):
            yaml_lines.append("    is_primary_key: true")
            
    with open(f"src/semantic_engine/.wren_project/models/{table_name}/metadata.yml", "w") as f:
        f.write("\n".join(yaml_lines) + "\n")
        
    logger.info(f"✅ Created model: models/{table_name}/metadata.yml")

def add_cube(cube_name):
    """Generates the MDL YAML for a semantic Cube."""
    if cube_name not in CUBES:
        logger.error(f"❌ Cube '{cube_name}' definition not found in registry.")
        return
    
    os.makedirs(f"src/semantic_engine/.wren_project/cubes/{cube_name}", exist_ok=True)
    
    meta = CUBES[cube_name]
    
    yaml_lines = [
        f"name: {cube_name}",
        f"base_object: {meta['base_object']}",
    ]
    
    if "dimensions" in meta:
        yaml_lines.append("dimensions:")
        for dim in meta["dimensions"]:
            yaml_lines.append(f"  - name: {dim['name']}")
            yaml_lines.append(f"    column: {dim['column']}")
            
    if "time_dimensions" in meta:
        yaml_lines.append("time_dimensions:")
        for tdim in meta["time_dimensions"]:
            yaml_lines.append(f"  - name: {tdim['name']}")
            yaml_lines.append(f"    column: {tdim['column']}")
            
    if "measures" in meta:
        yaml_lines.append("measures:")
        for meas in meta["measures"]:
            yaml_lines.append(f"  - name: {meas['name']}")
            yaml_lines.append(f"    expression: \"{meas['expression']}\"")
            yaml_lines.append(f"    type: {meas['type']}")
            
    with open(f"src/semantic_engine/.wren_project/cubes/{cube_name}/metadata.yml", "w") as f:
        f.write("\n".join(yaml_lines) + "\n")
        
    logger.info(f"✅ Created cube: cubes/{cube_name}/metadata.yml")

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
    """Lists all active models and cubes in the engine."""
    path = "src/semantic_engine/.wren_project/models"
    cubes_path = "src/semantic_engine/.wren_project/cubes"
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
            
    if os.path.exists(cubes_path):
        cube_folders = [f for f in os.listdir(cubes_path) if os.path.isdir(os.path.join(cubes_path, f))]
        if cube_folders:
            logger.info("📦 Currently tracked cubes:")
            for f in cube_folders:
                logger.info(f"  - {f}")

def build_context():
    """Compiles the WrenAI semantic context into the mdl.json manifest."""
    logger.info("🧠 Validating Semantic Context...")
    try:
        subprocess.run(["wren", "context", "validate"], cwd="src/semantic_engine/.wren_project", check=True)
        logger.info("🧠 Compiling Semantic Context (Generating mdl.json manifest)...")
        subprocess.run(["wren", "context", "build"], cwd="src/semantic_engine/.wren_project", check=True)
        logger.info("🎉 Semantic Engine compiled successfully! mdl.json is ready.")
    except FileNotFoundError as exc:
        logger.error("⚠️ 'wren' CLI not found. Make sure you have activated your virtual environment.")
        raise SystemExit(127) from exc
    except subprocess.CalledProcessError as exc:
        logger.error("⚠️ Failed to build the Wren context. Check your Trino connection and syntax.")
        raise SystemExit(exc.returncode) from exc

def index_memory():
    """Builds the local .wren/memory retrieval index."""
    logger.info("🧠 Indexing Semantic Memory (Vectorizing to local .wren/memory)...")
    try:
        subprocess.run(["wren", "memory", "index"], cwd="src/semantic_engine/.wren_project", check=True)
        logger.info("🎉 Semantic memory successfully indexed locally.")
    except FileNotFoundError as exc:
        logger.error("⚠️ 'wren' CLI not found.")
        raise SystemExit(127) from exc
    except subprocess.CalledProcessError as exc:
        logger.error("⚠️ Memory index build failed.")
        raise SystemExit(exc.returncode) from exc

def query_context(sql_query):
    """Wraps the WrenAI SQL execution CLI."""
    logger.info(f"🔎 Executing Semantic Query: {sql_query}")
    try:
        subprocess.run(["wren", "--sql", sql_query], cwd="src/semantic_engine/.wren_project", check=True)
    except FileNotFoundError as exc:
        logger.error("⚠️ 'wren' CLI not found.")
        raise SystemExit(127) from exc
    except subprocess.CalledProcessError as exc:
        logger.error("⚠️ Query execution failed.")
        raise SystemExit(exc.returncode) from exc

def watch_memory():
    """Runs the WrenAI dynamic memory indexing daemon."""
    logger.info("👀 Starting Memory Watch Daemon (auto-indexing every 2 seconds)...")
    try:
        subprocess.run(["wren", "memory", "watch", "-i", "2"], cwd="src/semantic_engine/.wren_project", check=True)
    except FileNotFoundError as exc:
        logger.error("⚠️ 'wren' CLI not found.")
        raise SystemExit(127) from exc
    except KeyboardInterrupt:
        logger.info("🛑 Memory Watch Daemon stopped.")
    except subprocess.CalledProcessError as exc:
        logger.error("⚠️ Memory watch daemon failed.")
        raise SystemExit(exc.returncode) from exc

def dry_plan(sql_query):
    """Validates the syntax and logic of a SQL query without executing it."""
    logger.info(f"🧪 Dry Planning Semantic Query: {sql_query}")
    try:
        subprocess.run(["wren", "dry-plan", "--sql", sql_query], cwd="src/semantic_engine/.wren_project", check=True)
        logger.info("✅ Dry plan successful. Query is valid.")
    except FileNotFoundError as exc:
        logger.error("⚠️ 'wren' CLI not found.")
        raise SystemExit(127) from exc
    except subprocess.CalledProcessError as exc:
        logger.error("⚠️ Dry plan failed. Invalid query syntax or semantics.")
        raise SystemExit(exc.returncode) from exc

def serve_mcp():
    """Runs the WrenAI native MCP server."""
    logger.info("🚀 Starting WrenAI native MCP server...")
    try:
        subprocess.run(["wren", "serve", "mcp"], cwd="src/semantic_engine/.wren_project", check=True)
    except FileNotFoundError as exc:
        logger.error("⚠️ 'wren' CLI not found. Is wrenai[mcp] installed?")
        raise SystemExit(127) from exc
    except KeyboardInterrupt:
        logger.info("🛑 MCP Server stopped.")
    except subprocess.CalledProcessError as exc:
        logger.error("⚠️ MCP server failed.")
        raise SystemExit(exc.returncode) from exc

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WrenAI Semantic Engine Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    subparsers.add_parser("init", help="Initialize the project with v5 schema")
    
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
    
    # Watch
    subparsers.add_parser("watch", help="Start the dynamic memory indexing daemon")
    
    # Query
    parser_query = subparsers.add_parser("query", help="Execute a query against the semantic engine")
    parser_query.add_argument("sql", help="The SQL string to execute")

    # Dry-plan
    parser_dry = subparsers.add_parser("dry-plan", help="Validate a SQL query without executing it")
    parser_dry.add_argument("sql", help="The SQL string to validate")

    # Serve MCP
    subparsers.add_parser("serve", help="Start the native WrenAI MCP server")

    args = parser.parse_args()

    if args.command == "init":
        init_project()
    elif args.command == "add":
        if args.table == "all":
            for t in MODELS.keys():
                add_model(t)
            for c in CUBES.keys():
                add_cube(c)
        else:
            if args.table in MODELS:
                add_model(args.table)
            elif args.table in CUBES:
                add_cube(args.table)
            else:
                logger.error(f"❌ '{args.table}' not found in MODELS or CUBES.")
    elif args.command == "remove":
        remove_model(args.table)
    elif args.command == "list":
        list_models()
    elif args.command == "build":
        build_context()
    elif args.command == "index":
        index_memory()
    elif args.command == "watch":
        watch_memory()
    elif args.command == "query":
        query_context(args.sql)
    elif args.command == "dry-plan":
        dry_plan(args.sql)
    elif args.command == "serve":
        serve_mcp()

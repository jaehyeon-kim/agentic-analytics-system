-- PostgreSQL initialization script (Translated from AWS Workshop MySQL)
-- Returns Fraud Analytics - Tracks customer return abuse patterns
-- Note: This is a placeholder that will later be replaced by dynamic-des Postgres Egress generation.

CREATE TABLE IF NOT EXISTS customers (
    customer_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(20),
    address VARCHAR(200),
    city VARCHAR(50),
    state VARCHAR(50),
    zip_code VARCHAR(10),
    country VARCHAR(50) DEFAULT 'USA',
    loyalty_tier VARCHAR(20) DEFAULT 'Bronze',
    total_purchases INT DEFAULT 0,
    total_returns INT DEFAULT 0,
    return_rate DECIMAL(5,2) DEFAULT 0.00,
    lifetime_value DECIMAL(10,2) DEFAULT 0.00,
    fraud_risk_score INT DEFAULT 0,
    account_status VARCHAR(20) DEFAULT 'active',
    last_fraud_check TIMESTAMP NULL,
    suspicious_activity_count INT DEFAULT 0,
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INT,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    shipping_address VARCHAR(200),
    has_return BOOLEAN DEFAULT FALSE,
    return_count INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    price DECIMAL(10,2) NOT NULL,
    description TEXT,
    stock_quantity INT DEFAULT 0,
    total_sold INT DEFAULT 0,
    total_returned INT DEFAULT 0,
    return_rate DECIMAL(5,2) DEFAULT 0.00,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INT,
    product_id INT,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    total_price DECIMAL(10,2) NOT NULL,
    is_returned BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS returns (
    return_id SERIAL PRIMARY KEY,
    order_id INT,
    customer_id INT,
    product_id INT,
    return_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    return_reason VARCHAR(100),
    return_category VARCHAR(50),
    refund_amount DECIMAL(10,2),
    restocking_fee DECIMAL(10,2) DEFAULT 0.00,
    return_status VARCHAR(20) DEFAULT 'pending',
    days_since_purchase INT,
    product_condition VARCHAR(50),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

INSERT INTO customers (customer_id, first_name, last_name, email, phone, address, city, state, zip_code, loyalty_tier, total_purchases, total_returns, return_rate, lifetime_value, fraud_risk_score, account_status, suspicious_activity_count) VALUES
(47, 'Sam', 'Parker', 'sam.parker@email.com', '555-0147', '980 Maple St', 'Omaha', 'NE', '68101', 'Silver', 19, 8, 42.10, 12450.00, 85, 'under_review', 3),
(23, 'Ulysses', 'Lewis', 'ulysses.lewis@email.com', '555-0123', '346 Elm Way', 'Fort Worth', 'TX', '76101', 'Bronze', 20, 12, 60.00, 8900.00, 75, 'active', 2),
(89, 'Jay', 'Flores', 'jay.flores@email.com', '555-0189', '632 Spruce Ave', 'Chandler', 'AZ', '85224', 'Platinum', 60, 2, 3.33, 45000.00, 10, 'active', 0)
ON CONFLICT (email) DO NOTHING;

SELECT setval('customers_customer_id_seq', (SELECT MAX(customer_id) FROM customers));

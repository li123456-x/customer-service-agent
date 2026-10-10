from config.database import get_connection
from database.migrate_live_support import migrate_live_support

def create_tables():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    order_no VARCHAR(50) UNIQUE NOT NULL,
                    customer_name VARCHAR(100) NOT NULL,
                    phone VARCHAR(30),
                    product_name VARCHAR(200) NOT NULL,
                    product_category VARCHAR(100),
                    order_status VARCHAR(50) NOT NULL,
                    paid_amount NUMERIC(10, 2) NOT NULL,
                    paid_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logistics (
                    id SERIAL PRIMARY KEY,
                    order_no VARCHAR(50) NOT NULL REFERENCES orders(order_no),
                    logistics_company VARCHAR(100),
                    tracking_no VARCHAR(100),
                    logistics_status VARCHAR(100) NOT NULL,
                    latest_location VARCHAR(200),
                    estimated_delivery_time VARCHAR(100),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS refund_requests (
                    id SERIAL PRIMARY KEY,
                    refund_no VARCHAR(50) UNIQUE NOT NULL,
                    order_no VARCHAR(50) NOT NULL REFERENCES orders(order_no),
                    refund_type VARCHAR(50) NOT NULL,
                    refund_reason TEXT,
                    refund_status VARCHAR(100) NOT NULL,
                    requested_amount NUMERIC(10, 2),
                    approved_amount NUMERIC(10, 2),
                    requires_human_review BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(100) UNIQUE NOT NULL,
                    customer_name VARCHAR(100),
                    phone VARCHAR(30),
                    status VARCHAR(50) DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(100) NOT NULL REFERENCES chat_sessions(session_id),
                    role VARCHAR(30) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_traces (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(100),
                    user_message TEXT NOT NULL,
                    intent VARCHAR(100),
                    order_no VARCHAR(50),
                    tools_called TEXT,
                    confidence NUMERIC(4, 3),
                    final_action VARCHAR(100),
                    final_reply TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS human_reviews (
                    id SERIAL PRIMARY KEY,
                    review_no VARCHAR(50) UNIQUE NOT NULL,
                    session_id VARCHAR(100),
                    order_no VARCHAR(50),
                    user_message TEXT NOT NULL,
                    agent_summary TEXT,
                    review_reason TEXT,
                    review_status VARCHAR(50) DEFAULT 'pending',
                    reviewer_name VARCHAR(100),
                    reviewer_reply TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

def insert_sample_data():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO orders (
                    order_no,
                    customer_name,
                    phone,
                    product_name,
                    product_category,
                    order_status,
                    paid_amount,
                    paid_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_no) DO NOTHING;
            """, [
                (
                    "DD10001",
                    "张三",
                    "13800000001",
                    "蓝牙耳机 Pro",
                    "数码配件",
                    "已发货",
                    299.00,
                    "2026-09-01 10:30:00",
                ),
                (
                    "DD10002",
                    "李四",
                    "13800000002",
                    "智能手表 S2",
                    "智能穿戴",
                    "已签收",
                    899.00,
                    "2026-08-30 15:20:00",
                ),
                (
                    "DD10003",
                    "王五",
                    "13800000003",
                    "机械键盘 K8",
                    "电脑外设",
                    "待发货",
                    399.00,
                    "2026-09-02 09:10:00",
                ),
            ])

            cursor.executemany("""
                INSERT INTO logistics (
                    order_no,
                    logistics_company,
                    tracking_no,
                    logistics_status,
                    latest_location,
                    estimated_delivery_time
                )
                VALUES (%s, %s, %s, %s, %s, %s);
            """, [
                (
                    "DD10001",
                    "顺丰速运",
                    "SF123456789",
                    "运输中",
                    "上海转运中心",
                    "预计明天送达",
                ),
                (
                    "DD10002",
                    "京东物流",
                    "JD987654321",
                    "已签收",
                    "客户本人签收",
                    "已完成配送",
                ),
                (
                    "DD10003",
                    None,
                    None,
                    "待发货",
                    "商家仓库",
                    "预计今晚发出",
                ),
            ])
            cursor.executemany("""
                INSERT INTO refund_requests (
                    refund_no,
                    order_no,
                    refund_type,
                    refund_reason,
                    refund_status,
                    requested_amount,
                    approved_amount,
                    requires_human_review
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (refund_no) DO NOTHING;
            """, [
                (
                    "TK10001",
                    "DD10001",
                    "仅退款",
                    "暂未申请",
                    "未申请退款",
                    0,
                    0,
                    False,
                ),
                (
                    "TK10002",
                    "DD10002",
                    "退货退款",
                    "商品不符合预期",
                    "退款审核中",
                    899.00,
                    None,
                    True,
                ),
            ])

def main():
    create_tables()
    migrate_live_support()
    insert_sample_data()
    print("企业级智能客服数据库初始化完成")

if __name__ == "__main__":
    main()

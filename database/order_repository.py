from config.database import get_connection

def find_order_by_no(order_no):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    order_no,
                    customer_name,
                    phone,
                    product_name,
                    product_category,
                    order_status,
                    paid_amount,
                    paid_at,
                    created_at
                FROM orders
                WHERE order_no = %s
                """,
                (order_no,),
            )
            return cursor.fetchone()
from config.database import get_connection

def find_logistics_by_order_no(order_no):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    order_no,
                    logistics_company,
                    tracking_no,
                    logistics_status,
                    latest_location,
                    estimated_delivery_time,
                    updated_at
                FROM logistics
                WHERE order_no = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (order_no,),
            )
            return cursor.fetchone()
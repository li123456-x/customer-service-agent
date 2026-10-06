from config.database import get_connection

def find_refund_by_order_no(order_no):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    refund_no,
                    order_no,
                    refund_type,
                    refund_reason,
                    refund_status,
                    requested_amount,
                    approved_amount,
                    requires_human_review,
                    created_at,
                    updated_at
                FROM refund_requests
                WHERE order_no = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (order_no,),
            )
            return cursor.fetchone()
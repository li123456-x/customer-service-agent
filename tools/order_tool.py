from database.order_repository import find_order_by_no


def search_order(order_no):
    order = find_order_by_no(order_no)
    if not order:
        return {
            "success": False,
            "message": f"没有查询到订单 {order_no}",
            "data": None,
        }
    return {
        "success": True,
        "message": "订单查询成功",
        "data": {
            "order_no": order["order_no"],
            "customer_name": order["customer_name"],
            "phone": order["phone"],
            "product_name": order["product_name"],
            "product_category": order["product_category"],
            "order_status": order["order_status"],
            "paid_amount": str(order["paid_amount"]),
            "paid_at": str(order["paid_at"]) if order["paid_at"] else None,
            "created_at": str(order["created_at"]) if order["created_at"] else None,
        },
    }
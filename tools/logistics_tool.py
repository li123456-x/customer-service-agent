from database.logistics_repository import find_logistics_by_order_no

def search_logistics(order_no):
    logistics = find_logistics_by_order_no(order_no)
    if not logistics:
        return {
            "success": False,
            "message": f"没有查询到订单 {order_no} 的物流信息",
            "data": None,
        }
    return {
        "success": True,
        "message": "物流查询成功",
        "data": {
            "order_no": logistics["order_no"],
            "logistics_company": logistics["logistics_company"],
            "tracking_no": logistics["tracking_no"],
            "logistics_status": logistics["logistics_status"],
            "latest_location": logistics["latest_location"],
            "estimated_delivery_time": logistics["estimated_delivery_time"],
            "updated_at": str(logistics["updated_at"]) if logistics["updated_at"] else None,
        },
    }
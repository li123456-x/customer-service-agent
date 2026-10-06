from database.refund_repository import find_refund_by_order_no


def search_refund(order_no):
    refund = find_refund_by_order_no(order_no)
    if not refund:
        return {
            "success": False,
            "message": f"没有查询到订单 {order_no} 的退款或售后记录",
            "data": None,
        }
    return {
        "success": True,
        "message": "退款/售后查询成功",
        "data": {
            "refund_no": refund["refund_no"],
            "order_no": refund["order_no"],
            "refund_type": refund["refund_type"],
            "refund_reason": refund["refund_reason"],
            "refund_status": refund["refund_status"],
            "requested_amount": str(refund["requested_amount"]) if refund["requested_amount"] is not None else None,
            "approved_amount": str(refund["approved_amount"]) if refund["approved_amount"] is not None else None,
            "requires_human_review": refund["requires_human_review"],
            "created_at": str(refund["created_at"]) if refund["created_at"] else None,
            "updated_at": str(refund["updated_at"]) if refund["updated_at"] else None,
        },
    }
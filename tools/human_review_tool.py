from database.chat_repository import save_chat_message
from database.human_review_repository import (
    complete_human_review,
    find_human_review_by_no,
    list_pending_human_reviews,
    reject_human_review,
)

def get_pending_reviews(limit=20):
    reviews = list_pending_human_reviews(limit)
    return {
        "success": True,
        "message": "待审核列表查询成功",
        "data": reviews,
    }

def get_review_detail(review_no):
    review = find_human_review_by_no(review_no)
    if not review:
        return {
            "success": False,
            "message": f"没有找到审核单 {review_no}",
            "data": None,
        }
    return {
        "success": True,
        "message": "审核单详情查询成功",
        "data": review,
    }

def approve_review(review_no, reviewer_name, reviewer_reply):
    old_review = find_human_review_by_no(review_no)
    if not old_review:
        return {
            "success": False,
            "message": f"没有找到审核单 {review_no}",
            "data": None,
        }
    review = complete_human_review(review_no, reviewer_name, reviewer_reply)
    if old_review["session_id"]:
        save_chat_message(
            old_review["session_id"],
            "human",
            f"{reviewer_name}：{reviewer_reply}",
        )
    return {
        "success": True,
        "message": "审核单已处理完成，并已写回聊天记录",
        "data": review,
    }

def reject_review(review_no, reviewer_name, reviewer_reply):
    old_review = find_human_review_by_no(review_no)
    if not old_review:
        return {
            "success": False,
            "message": f"没有找到审核单 {review_no}",
            "data": None,
        }
    review = reject_human_review(review_no, reviewer_name, reviewer_reply)
    if old_review["session_id"]:
        save_chat_message(
            old_review["session_id"],
            "human",
            f"{reviewer_name}：{reviewer_reply}",
        )
    return {
        "success": True,
        "message": "审核单已驳回，并已写回聊天记录",
        "data": review,
    }
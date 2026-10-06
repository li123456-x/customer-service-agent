from fastapi import APIRouter
from api.response import serialize_value
from api.schemas import ReviewActionRequest
from tools.human_review_tool import (
    approve_review,
    get_pending_reviews,
    get_review_detail,
    reject_review,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])

def normalize_tool_result(result):
    return {
        "success": result["success"],
        "message": result["message"],
        "data": serialize_value(result["data"]),
    }

@router.get("/pending")
def list_pending_reviews(limit: int = 20):
    return normalize_tool_result(get_pending_reviews(limit=limit))

@router.get("/{review_no}")
def review_detail(review_no: str):
    return normalize_tool_result(get_review_detail(review_no))

@router.post("/approve")
def approve_review_api(request: ReviewActionRequest):
    return normalize_tool_result(
        approve_review(
            review_no=request.review_no,
            reviewer_name=request.reviewer_name,
            reviewer_reply=request.reviewer_reply,
        )
    )

@router.post("/reject")
def reject_review_api(request: ReviewActionRequest):
    return normalize_tool_result(
        reject_review(
            review_no=request.review_no,
            reviewer_name=request.reviewer_name,
            reviewer_reply=request.reviewer_reply,
        )
    )
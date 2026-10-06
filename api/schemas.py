from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息不能为空")
    session_id: str | None = Field(default=None, description="会话ID，可为空")

class ReviewActionRequest(BaseModel):
    review_no: str = Field(..., min_length=1, description="审核单号不能为空")
    reviewer_name: str = Field(..., min_length=1, description="审核人不能为空")
    reviewer_reply: str = Field(..., min_length=1, description="审核回复不能为空")
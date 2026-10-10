from uuid import UUID
from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息不能为空")
    session_id: str | None = Field(default=None, description="会话ID，可为空")

class ReviewActionRequest(BaseModel):
    review_no: str = Field(..., min_length=1, description="审核单号不能为空")
    reviewer_name: str = Field(..., min_length=1, description="审核人不能为空")
    reviewer_reply: str = Field(..., min_length=1, description="审核回复不能为空")


class HandoffRequest(BaseModel):
    session_id: str | None = Field(default=None, min_length=1, max_length=100)


class SupportClaimRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=100)

    @field_validator("agent_name")
    @classmethod
    def strip_agent_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("客服名称不能为空")
        return value


class SupportActionRequest(SupportClaimRequest):
    handoff_version: int = Field(ge=1)


class SupportMessageRequest(SupportActionRequest):
    message: str = Field(min_length=1, max_length=4000)
    request_id: UUID

    @field_validator("message")
    @classmethod
    def strip_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("消息不能为空")
        return value

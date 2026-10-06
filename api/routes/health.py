from fastapi import APIRouter
from api.response import success_response

router = APIRouter()

@router.get("/health")
def health_check():
    return success_response(
        message="服务运行正常",
        data={
            "service": "customer-service-agent-api",
            "version": "0.1.0",
        },
    )
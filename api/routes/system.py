from fastapi import APIRouter
from api.response import serialize_value
from tools.system_check_tool import run_system_check

router = APIRouter(prefix="/system", tags=["system"])

@router.get("/check")
def system_check():
    result = run_system_check()
    return {
        "success": result["success"],
        "message": result["message"],
        "data": serialize_value(result["data"]),
    }
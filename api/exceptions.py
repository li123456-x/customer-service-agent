from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from api.response import error_response

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first_error = errors[0] if errors else {}
    field = first_error.get("loc", ["body"])[-1]
    message = first_error.get("msg", "请求参数错误")
    return JSONResponse(
        status_code=422,
        content=error_response(
            message=f"参数错误：{field} {message}",
            data=errors,
        ),
    )

async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=error_response(
            message=f"服务器内部错误：{str(exc)}",
            data=None,
        ),
    )
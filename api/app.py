from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from api.routes.system import router as system_router
from api.exceptions import global_exception_handler, validation_exception_handler
from api.routes.chat import router as chat_router
from api.routes.health import router as health_router
from api.routes.review import router as review_router
from api.routes.session import router as session_router
from api.routes.trace import router as trace_router
from api.routes.knowledge import router as knowledge_router
from api.routes.support import router as support_router
app = FastAPI(
    title="小想企业级智能客服 Agent API",
    description="基于 LangGraph、RAG、PostgreSQL、Milvus 的企业级智能客服后端",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)
app.include_router(health_router, tags=["health"])
app.include_router(chat_router, tags=["chat"])
app.include_router(review_router)
app.include_router(session_router)
app.include_router(system_router)
app.include_router(trace_router)
app.include_router(knowledge_router)
app.include_router(support_router)

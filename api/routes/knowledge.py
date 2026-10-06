from fastapi import APIRouter
from api.response import serialize_value
from tools.knowledge_admin_tool import (
    list_knowledge_files,
    reindex_knowledge,
    search_knowledge_for_admin,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

def normalize_tool_result(result):
    return {
        "success": result["success"],
        "message": result["message"],
        "data": serialize_value(result["data"]),
    }

@router.get("/files")
def knowledge_files():
    return normalize_tool_result(list_knowledge_files())

@router.get("/search")
def knowledge_search(query: str, top_k: int = 3):
    return normalize_tool_result(
        search_knowledge_for_admin(
            query=query,
            top_k=top_k,
        )
    )

@router.post("/reindex")
def knowledge_reindex():
    return normalize_tool_result(reindex_knowledge())
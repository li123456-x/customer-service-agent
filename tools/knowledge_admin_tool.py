from rag.ingest_knowledge import KNOWLEDGE_DIR, ingest_knowledge
from rag.retriever import search_knowledge

def list_knowledge_files():
    files = []
    if not KNOWLEDGE_DIR.exists():
        return {
            "success": True,
            "message": "知识库目录不存在",
            "data": [],
        }
    for file_path in KNOWLEDGE_DIR.glob("*.txt"):
        files.append(
            {
                "file_name": file_path.name,
                "path": str(file_path),
                "size": file_path.stat().st_size,
                "updated_at": file_path.stat().st_mtime,
            }
        )
    return {
        "success": True,
        "message": "知识库文件列表查询成功",
        "data": files,
    }

def search_knowledge_for_admin(query, top_k=None):
    if not query.strip():
        return {
            "success": False,
            "message": "检索问题不能为空",
            "data": [],
        }
    documents = search_knowledge(query, top_k=top_k)
    return {
        "success": True,
        "message": "知识库检索完成",
        "data": documents,
    }

def reindex_knowledge():
    ingest_knowledge()
    return {
        "success": True,
        "message": "知识库重建完成",
        "data": None,
    }

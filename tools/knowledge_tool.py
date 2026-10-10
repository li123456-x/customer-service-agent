from rag.retriever import search_knowledge

def search_policy_knowledge(query):
    documents = search_knowledge(query)
    if not documents:
        return {
            "success": False,
            "message": "没有检索到足够相关的企业知识库内容",
            "data": [],
        }
    return {
        "success": True,
        "message": "知识库检索成功",
        "data": documents,
    }

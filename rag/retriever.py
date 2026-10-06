from config.settings import settings
from langchain_community.embeddings import DashScopeEmbeddings
from pymilvus import MilvusClient
from config.milvus import get_milvus_config

def get_embeddings():
    if not settings.dashscope_api_key:
        raise RuntimeError("缺少必要环境变量：DASHSCOPE_API_KEY")
    return DashScopeEmbeddings(
        model="text-embedding-v3",
        dashscope_api_key=settings.dashscope_api_key,
    )

def search_knowledge(query, top_k=3):
    milvus_config = get_milvus_config()
    embeddings = get_embeddings()
    query_vector = embeddings.embed_query(query)
    client = MilvusClient(
        uri=milvus_config["uri"],
        db_name=milvus_config["db_name"],
    )
    collection_name = milvus_config["collection_name"]
    if not client.has_collection(collection_name):
        return []
    results = client.search(
        collection_name=collection_name,
        data=[query_vector],
        limit=top_k,
        output_fields=["text", "source", "path"],
        search_params={
            "metric_type": "COSINE",
            "params": {},
        },
    )
    documents = []
    for item in results[0]:
        entity = item.get("entity", {})
        documents.append(
            {
                "score": item.get("distance"),
                "text": entity.get("text"),
                "source": entity.get("source"),
                "path": entity.get("path"),
            }
        )
    return documents
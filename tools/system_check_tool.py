from config.database import get_connection
from config.milvus import get_milvus_config
from config.settings import settings
from pymilvus import MilvusClient


def check_postgres():
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                row = cursor.fetchone()
        return {
            "success": row["ok"] == 1,
            "message": "PostgreSQL 连接正常",
        }
    except Exception as error:
        return {
            "success": False,
            "message": f"PostgreSQL 连接失败：{error}",
        }

def check_milvus():
    try:
        milvus_config = get_milvus_config()
        client = MilvusClient(
            uri=milvus_config["uri"],
            db_name=milvus_config["db_name"],
        )
        collection_name = milvus_config["collection_name"]
        has_collection = client.has_collection(collection_name)
        return {
            "success": has_collection,
            "message": "Milvus 连接正常，知识库 Collection 存在" if has_collection else "Milvus 连接正常，但知识库 Collection 不存在",
            "data": {
                "uri": milvus_config["uri"],
                "db_name": milvus_config["db_name"],
                "collection_name": collection_name,
                "has_collection": has_collection,
            },
        }
    except Exception as error:
        return {
            "success": False,
            "message": f"Milvus 连接失败：{error}",
            "data": None,
        }

def check_llm_config():
    return {
        "success": bool(settings.deepseek_api_key),
        "message": "DeepSeek 配置存在" if settings.deepseek_api_key else "缺少 DEEPSEEK_API_KEY",
        "data": {
            "model_provider": "deepseek",
            "model": "deepseek-v4-flash",
        },
    }

def check_embedding_config():
    return {
        "success": bool(settings.dashscope_api_key),
        "message": "DashScope Embedding 配置存在" if settings.dashscope_api_key else "缺少 DASHSCOPE_API_KEY",
        "data": {
            "embedding_model": "text-embedding-v3",
        },
    }

def run_system_check():
    checks = {
        "postgres": check_postgres(),
        "milvus": check_milvus(),
        "llm": check_llm_config(),
        "embedding": check_embedding_config(),
    }
    success = all(item["success"] for item in checks.values())
    return {
        "success": success,
        "message": "系统自检通过" if success else "系统自检未完全通过",
        "data": checks,
    }
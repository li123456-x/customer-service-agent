from config.settings import settings

def get_milvus_config():
    return {
        "uri": settings.milvus_uri,
        "db_name": settings.milvus_db_name,
        "collection_name": settings.milvus_collection_name,
    }
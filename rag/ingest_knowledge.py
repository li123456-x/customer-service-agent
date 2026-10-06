from pathlib import Path
from config.settings import settings
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import MilvusClient
from config.milvus import get_milvus_config

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "data" / "knowledge"

def load_knowledge_documents():
    documents = []
    for file_path in KNOWLEDGE_DIR.glob("*.txt"):
        content = file_path.read_text(encoding="utf-8")
        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source": file_path.name,
                    "path": str(file_path),
                },
            )
        )
    return documents

def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,
        separators=["\n\n", "\n", "。", "；", "，", " "],
    )
    return splitter.split_documents(documents)

def get_embeddings():
    if not settings.dashscope_api_key:
        raise RuntimeError("缺少必要环境变量：DASHSCOPE_API_KEY")
    return DashScopeEmbeddings(
        model="text-embedding-v3",
        dashscope_api_key=settings.dashscope_api_key,
    )

def build_rows(chunks, vectors):
    rows = []
    for index, chunk in enumerate(chunks):
        rows.append(
            {
                "id": index + 1,
                "text": chunk.page_content,
                "vector": vectors[index],
                "source": chunk.metadata.get("source"),
                "path": chunk.metadata.get("path"),
            }
        )
    return rows

def ingest_knowledge():
    milvus_config = get_milvus_config()
    documents = load_knowledge_documents()
    if not documents:
        raise RuntimeError(f"没有找到知识库文件：{KNOWLEDGE_DIR}")
    chunks = split_documents(documents)
    texts = [chunk.page_content for chunk in chunks]
    embeddings = get_embeddings()
    vectors = embeddings.embed_documents(texts)
    dimension = len(vectors[0])
    client = MilvusClient(
        uri=milvus_config["uri"],
        db_name=milvus_config["db_name"],
    )
    collection_name = milvus_config["collection_name"]
    if client.has_collection(collection_name):
        client.drop_collection(collection_name)
    client.create_collection(
        collection_name=collection_name,
        dimension=dimension,
        primary_field_name="id",
        id_type="int",
        vector_field_name="vector",
        metric_type="COSINE",
        auto_id=False,
    )
    rows = build_rows(chunks, vectors)
    client.insert(
        collection_name=collection_name,
        data=rows,
    )
    print(f"知识库原始文档数量：{len(documents)}")
    print(f"知识库切分片段数量：{len(chunks)}")
    print(f"向量维度：{dimension}")
    print(f"Milvus Database：{milvus_config['db_name']}")
    print(f"Milvus Collection：{collection_name}")
    print("RAG 知识库入库完成")

if __name__ == "__main__":
    ingest_knowledge()
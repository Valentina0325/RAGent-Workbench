# ========== ingest.py - 将文档切片并存入 ChromaDB ==========
import chromadb
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")
EMBED_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

def sliding_window_chunk(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end]
        chunks.append(chunk)
        if end == text_len:
            break
        start = end - overlap
    return chunks

def get_embedding(text):
    headers = {"Authorization": f"Bearer {ZHIPU_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "embedding-2", "input": text}
    resp = requests.post(EMBED_URL, headers=headers, json=data)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]

# 1. 读取文档并切片（请确保 test.txt 存在）按行切分成多个片段（每行作为一个 chunk）
with open("test.txt", "r", encoding="utf-8") as f:
    lines = f.readlines()
chunks = [line.strip() for line in lines if line.strip()]  # 过滤空行
print(f"生成了 {len(chunks)} 个文档片段")

# 2. 连接 ChromaDB
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="docs")

# 可选：清空旧数据（如果你想完全替换知识库，取消下面注释）
# collection.delete(where={})

# 3. 存入向量库
ids = [f"doc_{i}" for i in range(len(chunks))]
for i, chunk in enumerate(chunks):
    emb = get_embedding(chunk)
    collection.upsert(
        ids=[ids[i]],
        embeddings=[emb],
        documents=[chunk]
    )
    print(f"✓ 已存入: {chunk[:30]}...")

print("✅ 所有文档嵌入完成！")

# 4. 保存 chunks 到 JSON 供 main.py 使用
with open("chunks.json", "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)
print("✅ chunks.json 已保存")
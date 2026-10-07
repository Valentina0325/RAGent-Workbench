# ========== ingest.py - 使用 ModelScope 可用模型 ==========
import chromadb
import json
from sentence_transformers import SentenceTransformer
from modelscope.hub.snapshot_download import snapshot_download
import os

# 1. 使用 ModelScope 下载模型（选择可用模型）
model_name = 'AI-ModelScope/bge-large-zh-v1.5'   # 或 'damo/nlp_corom_sentence-embedding_chinese-base'
cache_dir = './model_cache'

print("正在从 ModelScope 下载/加载模型...")
try:
    model_dir = snapshot_download(model_name, cache_dir=cache_dir)
    print(f"模型目录: {model_dir}")
    model = SentenceTransformer(model_dir)
    print("模型加载成功")
except Exception as e:
    print(f"模型加载失败: {e}")
    # 可以尝试其他备选模型
    print("尝试备选模型: damo/nlp_corom_sentence-embedding_chinese-base")
    try:
        model_dir = snapshot_download('damo/nlp_corom_sentence-embedding_chinese-base', cache_dir=cache_dir)
        model = SentenceTransformer(model_dir)
        print("备选模型加载成功")
    except Exception as e2:
        print(f"备选模型也加载失败: {e2}")
        exit(1)

# 2. 读取文档
with open("test.txt", "r", encoding="utf-8") as f:
    lines = f.readlines()
chunks = [line.strip() for line in lines if line.strip()]
print(f"生成了 {len(chunks)} 个文档片段")

# 3. 批量生成向量（带进度条）
print("正在生成向量...")
embeddings = model.encode(chunks, normalize_embeddings=True, show_progress_bar=True).tolist()
print("向量生成完成")

# 4. 连接 ChromaDB
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="docs")

# 清空旧数据
existing_ids = collection.get()['ids']
if existing_ids:
    collection.delete(ids=existing_ids)
    print(f"已删除 {len(existing_ids)} 条旧记录")

# 5. 存入向量库
ids = [f"doc_{i}" for i in range(len(chunks))]
collection.upsert(ids=ids, embeddings=embeddings, documents=chunks)
print("✅ 所有文档嵌入完成！")

# 6. 保存 chunks.json
with open("chunks.json", "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)
print("✅ chunks.json 已保存")
# -*- coding: utf-8 -*-
"""
一次性脚本：用新的统一切分标准（换行/句号边界）重建已有知识库的全部切块。

背景：旧的 _chunk_text 是滑动窗口 + 就近找边界，可能从句中截断、切块位置飘忽。
新标准：先按换行/句末标点切原子句，再按 chunk_size 合并，块间整句重叠。

做法：对每个 KB，把每个文档的现有 chunk 按 chunk_index 顺序拼回全文，
删除旧集合后用新逻辑重新切分、重新向量化写入。

用法：cd backend && D:/ch4/pyt/python.exe rechunk.py
"""
import chromadb
from main import kb_manager  # 复用已加载的 embedding 模型与新版 _chunk_text

client = chromadb.PersistentClient(path="./chroma_db")

kbs = kb_manager.list_kbs()
print(f"共发现 {len(kbs)} 个知识库：{[k['name'] for k in kbs]}")

for kb in kbs:
    name = kb["name"]
    col = kb_manager._collection(name)
    data = col.get()
    docs, metas = data.get("documents", []), data.get("metadatas", [])
    if not docs:
        print(f"[{name}] 空，跳过")
        continue

    # 按文档分组，chunk_index 排序拼回全文
    grouped = {}
    for doc, meta in zip(docs, metas or [{}] * len(docs)):
        meta = meta or {}
        src = meta.get("source", "未知")
        idx = int(meta.get("chunk_index", 0))
        grouped.setdefault(src, []).append((idx, doc))

    old_total = len(docs)
    print(f"\n[{name}] 文档 {len(grouped)} 个，旧切块 {old_total} 个")

    # 删除旧集合（upload_document 会自动重建）
    kb_manager.delete_kb(name)

    for src, items in grouped.items():
        items.sort(key=lambda x: x[0])
        full_text = "\n".join(d for _, d in items)
        n = kb_manager.upload_document(name, full_text, source_name=src)
        # 展示新切块边界预览
        preview = kb_manager._chunk_text(full_text)
        boundaries = [c[:24].replace("\n", "⏎") + "…" for c in preview[:3]]
        print(f"  - {src}: {len(items)} 块 → {n} 块 | 首块预览: {boundaries}")

print("\n重切完成。")

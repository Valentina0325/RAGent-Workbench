# -*- coding: utf-8 -*-
"""校准脚本：对比相关/不相关问题对「项目」知识库的检索分数分布，确定相关度阈值"""
import sys
sys.path.insert(0, r"D:\ch4\Efficient\RAGent-Workbench\backend")
import numpy as np
import jieba
from main import kb_manager, get_embedding

KB = "项目"

# 内容词提取：过滤停用词与单字符
STOP = set("""
的了是在有和就不再什么怎么如何请问可以需要注意哪些这个那个为对与及或如果因为所以但是还也很都吗呢吧啊嗯呀哦我你他她它们
的一是了我有和在就不人都一一个上也这到说要去你会着没有看好自己
""".split())


def content_tokens(text):
    return set(t for t in jieba.cut(text) if len(t.strip()) >= 2 and t.strip() not in STOP)


def analyze(q):
    col = kb_manager._collection(KB)
    cached = kb_manager._get_chunks(KB, col)
    chunks = cached["documents"]
    if not chunks:
        print("空知识库")
        return
    ids = cached["ids"]
    q_emb = get_embedding(q)
    n = min(len(chunks), 20)
    results = col.query(query_embeddings=[q_emb], n_results=n)
    q_ids = results.get('ids', [[]])[0] or []
    q_dist = results.get('distances', [[]])[0] or []
    id2dist = {q_ids[j]: q_dist[j] for j in range(min(len(q_ids), len(q_dist)))}
    vec_raw = np.array([1 / (1 + id2dist.get(cid, 10.0)) for cid in ids])
    vec_norm = kb_manager._normalize(vec_raw)

    query_tokens = list(jieba.cut(q))
    bm25 = kb_manager._get_bm25(KB, chunks)
    bm25_raw = np.array(bm25.get_scores(query_tokens))
    bm25_norm = kb_manager._normalize(bm25_raw)
    combined = 0.6 * vec_norm + 0.4 * bm25_norm

    order = np.argsort(combined)[-3:][::-1]
    q_tokens = content_tokens(q)
    print(f"\n问题: {q}")
    for rank, i in enumerate(order):
        c_tokens = content_tokens(chunks[i])
        overlap = q_tokens & c_tokens
        print(f"  top{rank+1}: vec_raw={vec_raw[i]:.4f} vec_norm={vec_norm[i]:.4f} "
              f"bm25_raw={bm25_raw[i]:.2f} bm25_norm={bm25_norm[i]:.4f} combined={combined[i]:.4f} "
              f"| 词重叠({len(overlap)}): {sorted(overlap)[:8] if overlap else '无'}")
        if rank == 0:
            print(f"        top1 chunk 片段: {chunks[i][:60]!r}")


relevant_qs = [
    "Redis缓存淘汰策略",
    "Session超时是怎么配置的",
    "RAG是什么",
    "项目的Agent规划流程",
]
irrelevant_qs = [
    "牙痛需要注意什么",
    "减脂期，晚饭怎么吃",
    "番茄可以生吃吗",
    "北京明天天气怎么样",
    "现在几点了",
    "画个柱状图",
    "失眠怎么调理",
]

print("=" * 70)
print("【应判为相关】")
for q in relevant_qs:
    analyze(q)
print("=" * 70)
print("【应判为不相关】")
for q in irrelevant_qs:
    analyze(q)

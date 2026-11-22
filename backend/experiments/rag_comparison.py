# -*- coding: utf-8 -*-
"""有/无 RAG 增强的问答效果对比实验（论文第5章用）

设计原则：
- 不修改任何业务代码，仅导入 main.py 的 KBManager / call_llm / _kb_hit 等真实函数。
- 两组对照：A=无 RAG（直接问 LLM），B=有 RAG（混合检索 top-k 注入上下文后问 LLM）。
- 问题集分三类：
  1) knowledge  —— 答案明确存在于知识库（项目SOP / Agent技术文档），考"事实准确性"。
  2) irrelevant —— 与知识库无关的生活常识，考"无关问题误触发检索率"（检索先行路由）。
  3) general    —— 通用问题，知识库无相关内容，考"无知识可用时是否劣化"。
- 评分口径全部程序化，避免主观打分：
  * 准确率：答案包含人工标定的标准答案要点（keywords 任一命中即得分，逐要点统计）。
  * 幻觉：无关知识库问题时，答案是否出现了知识库专有术语（杜撰依据）。
  * 引用命中：检索结果中是否包含含标准答案的片段（仅 B 组）。
  * 耗时：端到端秒数（含检索与 LLM 调用，A/B 同口径）。

运行：
    cd backend
    D:/ch4/pyt/python.exe experiments/rag_comparison.py

输出：
    experiments/results/rag_comparison_raw.json   —— 每题原始记录（论文数据留档）
    experiments/results/rag_comparison_summary.md —— 汇总表（可直接粘进论文）
    experiments/results/rag_comparison_summary.csv —— 汇总表 CSV（Excel 画图用）
"""
import os
import sys
import json
import csv
import time
import datetime

# 保证从仓库任意目录运行都能 import 到 main
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from main import kb_manager, call_llm, _kb_hit, LLM_MODEL  # noqa: E402

OUT_DIR = os.path.join(BACKEND_DIR, "experiments", "results")
os.makedirs(OUT_DIR, exist_ok=True)

# ============ 问题集（依据实际知识库内容人工标定）============
# kb: 使用的知识库名；category: knowledge / irrelevant / general
# keywords: 标准答案要点（每个要点是一组等价说法，命中任一即算该要点正确）
QUESTIONS = [
    # ---- 项目SOP知识库：答案明确存在于文档 ----
    {"id": "K01", "kb": "项目", "category": "knowledge",
     "question": "这份运维SOP的文档编号是什么？",
     "keywords": [["KB-IT-2026-08-30"]]},
    {"id": "K02", "kb": "项目", "category": "knowledge",
     "question": "文档要求的故障恢复SLA承诺时间是多少？",
     "keywords": [["15分钟", "15 分钟"]]},
    {"id": "K03", "kb": "项目", "category": "knowledge",
     "question": "黄金指标包括哪四类？",
     "keywords": [["延迟"], ["流量"], ["错误"], ["饱和度"]]},
    {"id": "K04", "kb": "项目", "category": "knowledge",
     "question": "P0级故障的定义示例是什么？",
     "keywords": [["全链路超时"], ["90%"]]},
    {"id": "K05", "kb": "项目", "category": "knowledge",
     "question": "应急工具包本地需要安装哪些工具？",
     "keywords": [["curl"], ["dig"], ["tcpdump"], ["arthas"]]},
    {"id": "K06", "kb": "项目", "category": "knowledge",
     "question": "Redis连接超时的常见根因和解决方法是什么？",
     "keywords": [["连接池泄露", "连接池"], ["maxclients"]]},
    {"id": "K07", "kb": "项目", "category": "knowledge",
     "question": "故障排查超过阈值后，K8s环境如何回滚到稳定版本？",
     "keywords": [["kubectl rollout undo"], ["deployment"]]},
    {"id": "K08", "kb": "项目", "category": "knowledge",
     "question": "5-Whys分析中，数据库连接超时的直接原因是什么？",
     "keywords": [["连接数满", "连接数"]]},
    # ---- Agent技术知识库 ----
    {"id": "K09", "kb": "Agent", "category": "knowledge",
     "question": "ChromaDB适合什么场景？它支持什么向量索引算法？",
     "keywords": [["HNSW"], ["嵌入式", "本地开发"]]},
    {"id": "K10", "kb": "Agent", "category": "knowledge",
     "question": "混合检索（Hybrid Search）是如何工作的？",
     "keywords": [["向量"], ["关键词", "BM25"], ["权重", "合并排序"]]},
    {"id": "K11", "kb": "Agent", "category": "knowledge",
     "question": "GLM-4-Flash模型的上下文窗口有多大？",
     "keywords": [["128K", "128k"]]},
    {"id": "K12", "kb": "Agent", "category": "knowledge",
     "question": "构建RAG系统时，文档切片需要注意哪些要点？",
     "keywords": [["256-512", "256"], ["重叠", "overlap"], ["元数据"]]},
    # ---- 无关问题：检索先行路由应判为不相关，不得注入检索结果 ----
    {"id": "I01", "kb": "项目", "category": "irrelevant",
     "question": "牙痛需要注意什么？", "keywords": []},
    {"id": "I02", "kb": "项目", "category": "irrelevant",
     "question": "减脂期，晚饭怎么吃比较合适？", "keywords": []},
    {"id": "I03", "kb": "Agent", "category": "irrelevant",
     "question": "番茄可以生吃吗？", "keywords": []},
    {"id": "I04", "kb": "Agent", "category": "irrelevant",
     "question": "失眠应该怎么调理？", "keywords": []},
    # ---- 通用问题：知识库无相关内容，考 RAG 是否劣化 ----
    {"id": "G01", "kb": "项目", "category": "general",
     "question": "Python中列表和元组的主要区别是什么？",
     "keywords": [["可变"], ["不可变", "元组"]]},
    {"id": "G02", "kb": "Agent", "category": "general",
     "question": "HTTP状态码404表示什么？",
     "keywords": [["找不到", "不存在", "未找到"]]},
]

SYSTEM_PROMPT = "你是 RAGent 智能工作台助手，请用准确、简洁的中文回答用户问题。"

# 无关问题判幻觉用：知识库专有术语，若出现在无关题答案中即视为误引用
KB_JARGON = ["KB-IT-2026", "HNSW", "maxclients", "kubectl", "SLA", "黄金指标", "5-Whys", "BM25", "ChromaDB"]


def norm(text):
    """归一化：去空白、小写，便于匹配（中文不受影响）"""
    return "".join(str(text).split()).lower()


def hit_keywords(answer, keywords):
    """逐要点判定命中，返回 (命中数, 要点总数)"""
    if not keywords:
        return 0, 0
    a = norm(answer)
    got = sum(1 for group in keywords if any(norm(k) in a for k in group))
    return got, len(keywords)


def build_rag_prompt(question, contexts):
    """与 main.py /chat/stream 第916行完全一致的 RAG 提示词模板"""
    ref_text = "\n\n".join(f"[{j+1}] {c}" for j, c in enumerate(contexts))
    return (f"以下是从知识库检索到的参考资料（带编号）：\n\n{ref_text}\n\n"
            f"问题：{question}\n\n请基于参考资料回答。注意：不要在回答中添加 [1]、[2] 之类的引用编号，"
            f"直接用自然语言作答。若参考资料与问题实际无关，请直接说明并基于通用知识回答。回答：")


def source_has_answer(sources, keywords):
    """引用命中：检索片段中是否含有标准答案要点"""
    if not keywords:
        return None
    blob = norm(" ".join(s.get("text", "") for s in sources))
    return any(any(norm(k) in blob for k in group) for group in keywords)


def run_experiment():
    records = []
    for item in QUESTIONS:
        q = item["question"]
        kb = item["kb"]
        rec = dict(item)
        rec["run_at"] = datetime.datetime.now().isoformat(timespec="seconds")

        # -------- 先做一次检索（B组用；同时记录路由判定）--------
        t0 = time.perf_counter()
        contexts, sources = kb_manager.query(kb, q, top_k=3)
        retrieve_sec = time.perf_counter() - t0
        routed = bool(contexts) and _kb_hit(q, contexts)
        rec["retrieved_chunks"] = len(contexts)
        rec["retrieve_sec"] = round(retrieve_sec, 3)
        rec["routed_to_rag"] = routed

        # -------- A组：无 RAG，直接问 LLM --------
        t0 = time.perf_counter()
        try:
            ans_a = call_llm(q, system_prompt=SYSTEM_PROMPT, temperature=0.7)
            err_a = ""
        except Exception as e:
            ans_a, err_a = "", f"{type(e).__name__}: {e}"
        rec["answer_no_rag"] = ans_a
        rec["sec_no_rag"] = round(time.perf_counter() - t0, 3)
        rec["error_no_rag"] = err_a

        # -------- B组：有 RAG，只有路由命中才注入检索结果 --------
        t0 = time.perf_counter()
        try:
            if routed:
                ans_b = call_llm(build_rag_prompt(q, contexts), system_prompt=SYSTEM_PROMPT, temperature=0.7)
            else:
                # 路由判为不相关时，与 A 组同口径（体现检索先行路由不误伤）
                ans_b = call_llm(q, system_prompt=SYSTEM_PROMPT, temperature=0.7)
            err_b = ""
        except Exception as e:
            ans_b, err_b = "", f"{type(e).__name__}: {e}"
        rec["answer_rag"] = ans_b
        rec["sec_rag"] = round(time.perf_counter() - t0 + retrieve_sec, 3)  # 含检索耗时
        rec["error_rag"] = err_b

        # -------- 评分 --------
        ka, na = hit_keywords(ans_a, item["keywords"])
        kb_hit, nb = hit_keywords(ans_b, item["keywords"])
        rec["accuracy_no_rag"] = round(ka / na, 4) if na else None
        rec["accuracy_rag"] = round(kb_hit / nb, 4) if nb else None
        rec["points_no_rag"] = f"{ka}/{na}" if na else "-"
        rec["points_rag"] = f"{kb_hit}/{nb}" if nb else "-"
        rec["citation_hit"] = source_has_answer(sources, item["keywords"])
        if item["category"] == "irrelevant":
            rec["hallucination_no_rag"] = any(norm(j) in norm(ans_a) for j in KB_JARGON)
            rec["hallucination_rag"] = any(norm(j) in norm(ans_b) for j in KB_JARGON)
        else:
            rec["hallucination_no_rag"] = None
            rec["hallucination_rag"] = None

        # 期望路由：knowledge → 应命中；irrelevant/general → 应不命中
        rec["route_correct"] = routed if item["category"] == "knowledge" else (not routed)

        flag = "OK" if not (err_a or err_b) else "ERR"
        print(f"[{flag}] {item['id']} {item['category']:10s} 路由={'RAG' if routed else '通用':4s} "
              f"要点 A={rec['points_no_rag']:4s} B={rec['points_rag']:4s} "
              f"耗时 A={rec['sec_no_rag']:5.2f}s B={rec['sec_rag']:5.2f}s")
        records.append(rec)

    return records


def avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def summarize(records):
    lines = []
    lines.append("# 有/无 RAG 增强问答效果对比实验结果\n")
    lines.append(f"- 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 大模型：智谱 API `{LLM_MODEL}`（temperature=0.7）")
    lines.append("- 检索：bge-large-zh-v1.5 向量(0.6) + jieba/BM25 关键词(0.4)，top_k=3")
    lines.append(f"- 题目数：{len(records)}（知识库题 {sum(1 for r in records if r['category']=='knowledge')}、"
                 f"无关题 {sum(1 for r in records if r['category']=='irrelevant')}、"
                 f"通用题 {sum(1 for r in records if r['category']=='general')}）\n")

    lines.append("## 1. 按题型汇总\n")
    lines.append("| 题型 | 题数 | 无RAG准确率 | 有RAG准确率 | 提升 | 无RAG平均耗时(s) | 有RAG平均耗时(s) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    summary_rows = []
    for cat, name in [("knowledge", "知识库事实题"), ("irrelevant", "无关问题"), ("general", "通用问题")]:
        rs = [r for r in records if r["category"] == cat]
        a = avg([r["accuracy_no_rag"] for r in rs])
        b = avg([r["accuracy_rag"] for r in rs])
        sa = avg([r["sec_no_rag"] for r in rs])
        sb = avg([r["sec_rag"] for r in rs])
        delta = round(b - a, 4) if (a is not None and b is not None) else None
        fmt = lambda x: "—" if x is None else (f"{x*100:.1f}%" if x < 2 else f"{x:.2f}")
        lines.append(f"| {name} | {len(rs)} | {fmt(a)} | {fmt(b)} | {fmt(delta)} | {fmt(sa)} | {fmt(sb)} |")
        summary_rows.append([name, len(rs), a, b, delta, sa, sb])

    all_r = records
    a_all, b_all = avg([r["accuracy_no_rag"] for r in all_r]), avg([r["accuracy_rag"] for r in all_r])
    lines.append(f"\n> 说明：无关题/通用题无标准要点，准确率栏记为「—」，其效果见第 3、4 节。")

    lines.append("\n## 2. 知识库事实题逐题明细\n")
    lines.append("| 编号 | 知识库 | 问题 | 无RAG | 有RAG | 引用命中 |")
    lines.append("|---|---|---|---|---|---|")
    for r in all_r:
        if r["category"] != "knowledge":
            continue
        lines.append(f"| {r['id']} | {r['kb']} | {r['question']} | {r['points_no_rag']} | "
                     f"{r['points_rag']} | {'是' if r['citation_hit'] else '否'} |")

    lines.append("\n## 3. 检索先行路由（无关问题误触发率）\n")
    irr = [r for r in all_r if r["category"] == "irrelevant"]
    rec_hit = sum(1 for r in irr if r["routed_to_rag"])
    rec_hall_a = sum(1 for r in irr if r["hallucination_no_rag"])
    rec_hall_b = sum(1 for r in irr if r["hallucination_rag"])
    lines.append(f"- 无关问题数：{len(irr)}；误判为知识库相关：{rec_hit} 题，误触发率 {rec_hit/len(irr)*100:.1f}%")
    lines.append(f"- 无RAG组出现知识库专有术语（杜撰依据）：{rec_hall_a} 题")
    lines.append(f"- 有RAG组出现知识库专有术语：{rec_hall_b} 题")
    lines.append("\n| 编号 | 问题 | 是否误触发 | 无RAG术语误引 | 有RAG术语误引 |")
    lines.append("|---|---|---|---|---|")
    for r in irr:
        lines.append(f"| {r['id']} | {r['question']} | {'是' if r['routed_to_rag'] else '否'} | "
                     f"{'是' if r['hallucination_no_rag'] else '否'} | {'是' if r['hallucination_rag'] else '否'} |")

    lines.append("\n## 4. 通用问题（RAG 是否劣化）\n")
    lines.append("| 编号 | 问题 | 无RAG要点 | 有RAG要点 | 是否误触发检索 |")
    lines.append("|---|---|---|---|---|")
    for r in all_r:
        if r["category"] != "general":
            continue
        lines.append(f"| {r['id']} | {r['question']} | {r['points_no_rag']} | {r['points_rag']} | "
                     f"{'是' if r['routed_to_rag'] else '否'} |")

    route_ok = sum(1 for r in all_r if r["route_correct"])
    know = [r for r in all_r if r["category"] == "knowledge"]
    cite = [r["citation_hit"] for r in know if r["citation_hit"] is not None]
    lines.append("\n## 5. 总体指标\n")
    lines.append(f"- 路由判定正确率：{route_ok}/{len(all_r)} = {route_ok/len(all_r)*100:.1f}%")
    lines.append(f"- 知识库事实题引用命中率：{sum(1 for x in cite if x)}/{len(cite)} = "
                 f"{sum(1 for x in cite if x)/len(cite)*100:.1f}%")
    lines.append(f"- 知识库事实题平均准确率：无RAG {avg([r['accuracy_no_rag'] for r in know])*100:.1f}% → "
                 f"有RAG {avg([r['accuracy_rag'] for r in know])*100:.1f}%")
    lines.append(f"- 全部题目平均耗时：无RAG {avg([r['sec_no_rag'] for r in all_r]):.2f}s → "
                 f"有RAG {avg([r['sec_rag'] for r in all_r]):.2f}s（含检索开销）")

    md = "\n".join(lines) + "\n"
    with open(os.path.join(OUT_DIR, "rag_comparison_summary.md"), "w", encoding="utf-8") as f:
        f.write(md)

    csv_path = os.path.join(OUT_DIR, "rag_comparison_summary.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["题型", "题数", "无RAG准确率", "有RAG准确率", "提升", "无RAG平均耗时s", "有RAG平均耗时s"])
        for row in summary_rows:
            w.writerow([("" if x is None else (round(x, 4) if isinstance(x, float) else x)) for x in row])

    return md, summary_rows


def main():
    print("=" * 70)
    print("有/无 RAG 对比实验开始（每题调用智谱 API 两次，请耐心等待）")
    print("=" * 70)
    records = run_experiment()
    raw_path = os.path.join(OUT_DIR, "rag_comparison_raw.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({"model": LLM_MODEL, "generated_at": datetime.datetime.now().isoformat(),
                   "records": records}, f, ensure_ascii=False, indent=2)
    md, _ = summarize(records)
    print("=" * 70)
    print(md)
    print(f"原始数据：{raw_path}")


if __name__ == "__main__":
    main()

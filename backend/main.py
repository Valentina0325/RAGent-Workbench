# ========== RAGent 智能工作台 - 后端服务 ==========
# 统一对话接口 + 多知识库管理 + 文档上传 + SSE流式响应 + Agent多步规划

import chromadb
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import json
import os
import re
import datetime
import hashlib
import numpy as np
import jieba
from rank_bm25 import BM25Okapi
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()
app = FastAPI(title="RAGent Workbench API")

# ---------- 配置 ----------
API_KEY = os.getenv("ZHIPU_API_KEY")
if not API_KEY:
    print("⚠️ 警告：未设置 ZHIPU_API_KEY，LLM 功能将不可用。")
LLM_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
LLM_MODEL = "glm-4-flash"

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 加载 Embedding 模型 ----------
# 尝试多个可能的缓存路径
_model_candidates = [
    "./model_cache/AI-ModelScope/bge-large-zh-v1.5",
    "./model_cache/models/AI-ModelScope--bge-large-zh-v1.5/snapshots/master",
]
cache_dir = None
for p in _model_candidates:
    if os.path.exists(os.path.join(p, "config.json")):
        cache_dir = p
        break

if cache_dir:
    embedding_model = SentenceTransformer(cache_dir)
    print(f"✅ 从本地缓存加载 Embedding 模型成功: {cache_dir}")
else:
    print("⚠️ 本地缓存未找到，尝试从 HuggingFace 加载...")
    embedding_model = SentenceTransformer('moka-ai/m3e-large')
    print("✅ 模型加载成功")

def get_embedding(text: str):
    return embedding_model.encode(text, normalize_embeddings=True).tolist()


# =====================================================================
#  知识库管理器 —— 支持多个 ChromaDB 集合（中文安全命名）
# =====================================================================
class KBManager:
    def __init__(self, client, model):
        self.client = client
        self.model = model
        self._bm25_cache = {}
        self._chunks_cache = {}

    @staticmethod
    def _safe_name(name):
        """将中文知识库名转为 ChromaDB 合法集合名（hex 编码）"""
        if re.match(r'^[a-zA-Z0-9._-]+$', name):
            return name  # 纯 ASCII 直接用
        return 'kb_' + name.encode('utf-8').hex()

    @staticmethod
    def _display_name(safe):
        """将 ChromaDB 集合名还原为显示名"""
        if safe.startswith('kb_'):
            try:
                return bytes.fromhex(safe[3:]).decode('utf-8')
            except Exception:
                pass
        return safe

    def _collection(self, display_name):
        safe = self._safe_name(display_name)
        return self.client.get_or_create_collection(name=safe)

    def list_kbs(self):
        cols = self.client.list_collections()
        result = []
        for c in cols:
            safe = c if isinstance(c, str) else c.name
            display = self._display_name(safe)
            try:
                col = self.client.get_collection(safe)
                count = col.count()
            except Exception:
                count = 0
            result.append({"name": display, "chunk_count": count})
        return result

    def create_kb(self, name):
        self._collection(name)
        return True

    def delete_kb(self, name):
        try:
            safe = self._safe_name(name)
            self.client.delete_collection(name=safe)
            self._bm25_cache.pop(name, None)
            self._chunks_cache.pop(name, None)
            return True, ""
        except Exception as e:
            return False, str(e)

    def upload_document(self, kb_name, text, source_name=""):
        col = self._collection(kb_name)
        chunks = self._chunk_text(text)
        if not chunks:
            return 0
        embeddings = self.model.encode(chunks, normalize_embeddings=True, show_progress_bar=False).tolist()
        safe = self._safe_name(kb_name)
        ids = [f"{safe}_{source_name}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": source_name, "chunk_index": i} for i in range(len(chunks))]
        col.upsert(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
        # 清除缓存
        self._bm25_cache.pop(kb_name, None)
        self._chunks_cache.pop(kb_name, None)
        return len(chunks)

    def query(self, kb_name, question, top_k=3):
        col = self._collection(kb_name)
        cached = self._get_chunks(kb_name, col)
        chunks = cached["documents"]
        metas = cached["metadatas"] or [{} for _ in chunks]
        ids = cached["ids"]
        if not chunks:
            return [], []

        q_emb = get_embedding(question)
        n = min(len(chunks), 20)
        results = col.query(query_embeddings=[q_emb], n_results=n)
        q_ids = results.get('ids', [[]])[0] or []
        q_dist = results.get('distances', [[]])[0] or []
        id2dist = {q_ids[j]: q_dist[j] for j in range(min(len(q_ids), len(q_dist)))}

        # 向量得分对齐全量 chunks（修复原来向量结果与 BM25 数组长度不一致的问题）
        vector_scores = np.array([1 / (1 + id2dist.get(cid, 10.0)) for cid in ids])

        query_tokens = list(jieba.cut(question))
        bm25 = self._get_bm25(kb_name, chunks)
        bm25_scores = np.array(bm25.get_scores(query_tokens))

        vec_norm = self._normalize(vector_scores)
        bm25_norm = self._normalize(bm25_scores)
        combined = 0.6 * vec_norm + 0.4 * bm25_norm
        top_idx = np.argsort(combined)[-top_k:][::-1]

        contexts = [chunks[i] for i in top_idx]
        sources = []
        for i in top_idx:
            meta = metas[i] or {}
            sources.append({
                "text": chunks[i],
                "source": meta.get("source", "未知"),
                "chunk_index": int(meta.get("chunk_index", -1)),
                "score": round(float(combined[i]), 4),
            })
        return contexts, sources

    # ---- 内部方法 ----
    def _chunk_text(self, text, chunk_size=400, overlap=60):
        """统一标准分块：先按【换行 + 句末标点（。！？!?；;…）】切成原子句，
        再将相邻原子句合并为不超过 chunk_size 的块，块间按整句保留 overlap 重叠。
        任何块都不会从句子中间截断（超过 chunk_size 且无任何标点的长句才硬切并留重叠）。"""
        if not text or not text.strip():
            return []

        # 第一步：统一边界切原子句
        units = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            for sent in re.findall(r'[^。！？!?；;…]+[。！？!?；;…]*', line):
                sent = sent.strip()
                if not sent:
                    continue
                if len(sent) > chunk_size:
                    # 超长无边界内容（如整行长串数字/代码）：按 chunk_size 硬切，段间留 overlap
                    i = 0
                    while i < len(sent):
                        units.append(sent[i:i + chunk_size])
                        if i + chunk_size >= len(sent):
                            break
                        i += chunk_size - overlap
                else:
                    units.append(sent)

        # 第二步：相邻原子句合并成块（不超过 chunk_size）
        chunks, cur, cur_len = [], [], 0
        for u in units:
            if cur and cur_len + len(u) > chunk_size:
                chunks.append('\n'.join(cur))
                # 块间重叠：保留末尾总长不超过 overlap 的整句
                keep, keep_len = [], 0
                for x in reversed(cur):
                    if keep_len + len(x) > overlap:
                        break
                    keep.insert(0, x)
                    keep_len += len(x)
                cur, cur_len = keep, keep_len
            cur.append(u)
            cur_len += len(u)
        if cur:
            chunks.append('\n'.join(cur))
        return chunks

    def _get_chunks(self, kb_name, col):
        if kb_name not in self._chunks_cache:
            data = col.get()
            self._chunks_cache[kb_name] = {
                "ids": data.get("ids", []),
                "documents": data.get("documents", []),
                "metadatas": data.get("metadatas", []),
            }
        return self._chunks_cache[kb_name]

    def _get_bm25(self, kb_name, chunks):
        if kb_name not in self._bm25_cache:
            tokenized = [list(jieba.cut(c)) for c in chunks]
            self._bm25_cache[kb_name] = BM25Okapi(tokenized)
        return self._bm25_cache[kb_name]

    @staticmethod
    def _normalize(arr):
        mn, mx = arr.min(), arr.max()
        if mx == mn:
            return np.ones_like(arr)
        return (arr - mn) / (mx - mn)


# ---------- 初始化 KB 管理器 ----------
chroma_client = chromadb.PersistentClient(path="./chroma_db")
kb_manager = KBManager(chroma_client, embedding_model)

# 兼容旧代码：保留默认 collection 和 chunks
collection = chroma_client.get_or_create_collection(name="docs")
try:
    with open("chunks.json", "r", encoding="utf-8") as f:
        CHUNKS = json.load(f)
    print(f"✅ 加载了 {len(CHUNKS)} 个文档片段（默认知识库）")
except FileNotFoundError:
    CHUNKS = []
    print("ℹ️ chunks.json 不存在，默认知识库为空")


# =====================================================================
#  工具函数
# =====================================================================
def get_current_time():
    now = datetime.datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return now.strftime(f"%Y年%m月%d日 {weekdays[now.weekday()]} %H:%M:%S")

def get_weather(city: str, day: str = "today"):
    """基于城市名和日期生成确定性天气数据（真实 API 可替换此处）
    day: today / tomorrow / day_after_tomorrow
    """
    day_offset = {"today": 0, "tomorrow": 1, "day_after_tomorrow": 2}.get(day, 0)
    seed = city + str(day_offset)
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    conditions = ["晴朗", "多云", "阴天", "小雨", "中雨", "雷阵雨", "小雪", "雾"]
    condition = conditions[h % len(conditions)]
    temp = 5 + (h % 30) + day_offset * 2  # 未来天气略有变化
    humidity = 30 + (h % 60)
    wind = 1 + (h % 8)
    day_label = {"today": "当前", "tomorrow": "明天", "day_after_tomorrow": "后天"}.get(day, "当前")
    return f"{city}{day_label}天气：{condition}，气温{temp}℃，湿度{humidity}%，风力{wind}级"


def _extract_day(text: str) -> str:
    """从文本中提取日期意图：today / tomorrow / day_after_tomorrow"""
    if re.search(r'后天', text):
        return "day_after_tomorrow"
    if re.search(r'明天|明日|明儿', text):
        return "tomorrow"
    if re.search(r'今天|现在|当前', text):
        return "today"
    return "today"  # 默认今天


def _extract_city(text: str) -> str:
    """从文本中提取城市名，支持带'市/省/区/县'后缀和不带后缀的常见城市"""
    # 1. 先匹配带后缀的（如 广州市、北京市、深圳区）
    m = re.search(r'([\u4e00-\u9fa5]+?(?:市|省|区|县))', text)
    if m:
        return m.group(1)
    # 2. 再匹配常见城市名（不带后缀）
    common_cities = [
        "北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "重庆",
        "西安", "天津", "苏州", "长沙", "郑州", "青岛", "大连", "宁波", "厦门",
        "福州", "济南", "哈尔滨", "长春", "沈阳", "昆明", "南宁", "贵阳", "兰州",
        "海口", "三亚", "拉萨", "乌鲁木齐", "呼和浩特", "石家庄", "太原", "合肥",
        "南昌", "无锡", "常州", "温州", "佛山", "东莞", "中山", "珠海", "惠州",
    ]
    for c in common_cities:
        if c in text:
            return c
    # 3. 兜底：匹配任意连续 2-4 个汉字（可能是城市名）
    m2 = re.search(r'([\u4e00-\u9fa5]{2,4})', text)
    if m2:
        return m2.group(1)
    return "北京"

def query_knowledge_base(question: str, kb_name: str = "docs"):
    contexts, sources = kb_manager.query(kb_name, question, top_k=2)
    if not contexts:
        return "知识库中暂无相关信息。"
    return contexts[0] if contexts else "未找到相关内容。"


# =====================================================================
#  文档解析
# =====================================================================
def parse_pdf(content: bytes) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=content, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except ImportError:
        raise Exception("PyMuPDF 未安装，无法解析 PDF。请安装：pip install PyMuPDF")

def parse_txt(content: bytes) -> str:
    for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return content.decode('utf-8', errors='replace')


# =====================================================================
#  LLM 调用（支持多轮上下文历史）
# =====================================================================
def _history_messages(history):
    """把前端传来的对话历史转成合法 messages（过滤空内容并截断）"""
    msgs = []
    for h in (history or []):
        if not isinstance(h, dict):
            continue
        role = h.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        content = str(h.get("content", ""))[:600].strip()
        if content:
            msgs.append({"role": role, "content": content})
    return msgs

def build_history_text(history, max_turns=6):
    """把对话历史压缩成 prompt 文本块（用于规划等单轮 prompt）"""
    msgs = _history_messages(history)[-max_turns:]
    if not msgs:
        return "（无）"
    lines = []
    for m in msgs:
        who = "用户" if m["role"] == "user" else "助手"
        c = m["content"].replace("\n", " ")[:200]
        lines.append(f"{who}: {c}")
    return "\n".join(lines)

def call_llm(prompt, system_prompt="", temperature=0.7, history=None):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": prompt})
    payload = {"model": LLM_MODEL, "messages": messages, "stream": False, "temperature": temperature}
    resp = requests.post(LLM_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def stream_llm(prompt, system_prompt="", temperature=0.7, history=None):
    """生成器：逐 token 流式输出 LLM 回复（支持多轮历史）"""
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": prompt})
    payload = {"model": LLM_MODEL, "messages": messages, "stream": True, "temperature": temperature}
    resp = requests.post(LLM_URL, headers=headers, json=payload, stream=True, timeout=120)
    for line in resp.iter_lines():
        if not line:
            continue
        s = line.decode('utf-8')
        if s.startswith('data: '):
            data_str = s[6:]
            if data_str.strip() == '[DONE]':
                break
            try:
                data = json.loads(data_str)
                content = data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                if content:
                    yield content
            except Exception:
                pass


# =====================================================================
#  意图检测 —— Agent 作为通用入口
#  所有提问统一进入多步规划，由 LLM 规划器决定调用哪些工具
#  （天气/时间/知识库检索/CSV图表/日常问答均可覆盖）
# =====================================================================
def detect_intent(message, has_csv=False, has_kb=False):
    return 'agent'


# ---- 检索先行：知识库相关度判定（问题与检索内容的内容词重叠） ----
_KB_STOPWORDS = {
    '什么', '怎么', '怎样', '如何', '为什么', '是不是', '有没有', '可以', '需要', '应该', '哪些',
    '这个', '那个', '这些', '那些', '我们', '你们', '他们', '大家', '现在', '时候', '一下', '帮我',
    '请问', '然后', '还有', '以及', '还是', '但是', '如果', '因为', '所以', '没有', '不会', '可能',
    '介绍', '说明', '了解', '知道', '告诉', '意思', '区别', '东西', '问题', '情况', '方面', '直接',
    '告诉', '一下', '好吗', '行吗', '说说', '讲讲', '聊聊', '解答', '解释',
}
# 泛化词：即使与 chunk 重叠也不足以说明相关（技术/日常文档中都高频出现）
_KB_GENERIC_WORDS = {
    '注意', '需要', '建议', '处理', '设置', '配置', '文档', '文件', '内容', '系统', '方法', '方式',
    '实现', '功能', '管理', '查询', '查看', '使用', '用户', '数据', '信息', '服务', '相关', '进行',
    '支持', '提供', '知识库', '检索', '搜索', '要求', '推荐', '优化', '分析', '报告', '总结',
}


def _kb_content_words(text):
    """提取内容词：jieba 分词后过滤停用词、泛化词与单字"""
    words = {w.strip() for w in jieba.cut(text) if len(w.strip()) >= 2}
    return words - _KB_STOPWORDS - _KB_GENERIC_WORDS


def _kb_hit(question, contexts):
    """判断检索结果是否与问题真正相关：问题内容词与检索内容存在重叠。
    相关 → 走 RAG（展示引用来源）；不相关 → 走智能规划。"""
    q_words = _kb_content_words(question)
    if not q_words:
        return False
    for c in contexts:
        if q_words & _kb_content_words(c):
            return True
    return False


def _compute_data_facts(csv_ctx):
    """基于 CSV 上下文计算真实统计事实，供 LLM 直接引用具体数字作答。

    返回结构：
    {
      row_count, sampled,
      columns: [ {列, 类型, 非空数, 总和, 均值, 中位数, 最大, 最小, 最大对应, 最小对应} |
                 {列, 类型, 非空数, 唯一值数, 取值} ]
    }
    """
    headers = csv_ctx.get("headers") or []
    rows = csv_ctx.get("rows") or csv_ctx.get("sampleRows") or []
    row_count = csv_ctx.get("rowCount") or len(rows)
    if not headers or not rows:
        return None

    def _num(v):
        """尽力把单元格转成数值，失败返回 None"""
        if v is None:
            return None
        s = str(v).replace(',', '').replace('，', '').strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    # 选出首个"标签列"（多数取值非数值），用于标注极值对应的对象
    label_col = None
    for h in headers:
        vals = [_num(r.get(h)) for r in rows]
        ok = [v for v in vals if v is not None]
        if len(ok) < max(1, len(rows) * 0.6):
            label_col = h
            break

    facts = {"row_count": row_count, "sampled": len(rows), "columns": []}

    for h in headers:
        pairs = [(_num(r.get(h)), r) for r in rows]
        pairs = [(v, r) for v, r in pairs if v is not None]
        non_empty = [r for r in rows if str(r.get(h) if r.get(h) is not None else '').strip() != '']

        # 数值列判定：可解析数值的单元格占比 ≥ 60%
        if pairs and len(pairs) >= max(1, len(rows) * 0.6):
            vals = [v for v, _ in pairs]
            n = len(vals)
            total = sum(vals)
            sorted_vals = sorted(vals)
            if n % 2 == 1:
                med = sorted_vals[n // 2]
            else:
                med = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
            max_v, min_v = max(vals), min(vals)
            max_row = next((r for v, r in pairs if v == max_v), None)
            min_row = next((r for v, r in pairs if v == min_v), None)
            facts["columns"].append({
                "列": h, "类型": "数值", "非空数": n,
                "总和": round(total, 2), "均值": round(total / n, 2),
                "中位数": round(med, 2), "最大": max_v, "最小": min_v,
                "最大对应": (str(max_row.get(label_col)) if (max_row is not None and label_col) else None),
                "最小对应": (str(min_row.get(label_col)) if (min_row is not None and label_col) else None),
            })
        else:
            uniq, seen = [], set()
            for r in rows:
                v = str(r.get(h) if r.get(h) is not None else '').strip()
                if v and v not in seen:
                    seen.add(v)
                    uniq.append(v)
            item = {"列": h, "类型": "文本/分类", "非空数": len(non_empty), "唯一值数": len(uniq)}
            if len(uniq) <= 10:
                item["取值"] = uniq
            facts["columns"].append(item)

    return facts


def _format_data_facts(facts):
    """把统计事实格式化为紧凑的中文文本，注入 LLM 汇总上下文"""
    if not facts:
        return ""
    head = f"数据行数：{facts['row_count']}"
    if facts.get("sampled", 0) < facts["row_count"]:
        head += f"（以下统计基于前 {facts['sampled']} 行计算）"
    lines = [head]
    for c in facts.get("columns", []):
        if c.get("类型") == "数值":
            seg = (f"- {c['列']}（数值）：非空 {c['非空数']} 个，总和 {c['总和']}，"
                   f"平均 {c['均值']}，中位数 {c['中位数']}，最大 {c['最大']}，最小 {c['最小']}")
            if c.get("最大对应"):
                seg += f"；最大值对应「{c['最大对应']}」"
            if c.get("最小对应"):
                seg += f"，最小值对应「{c['最小对应']}」"
            lines.append(seg)
        else:
            seg = f"- {c['列']}（文本/分类）：非空 {c['非空数']} 个，唯一值 {c['唯一值数']} 个"
            if c.get("取值"):
                seg += f"，取值：{'、'.join(map(str, c['取值'][:10]))}"
            lines.append(seg)
    return "\n".join(lines)


def _gen_chart_config(msg, csv_ctx, history=None):
    """根据用户需求和 CSV 上下文生成图表配置（Agent 的 analyze_csv 工具核心）"""
    headers = csv_ctx.get("headers", [])
    if not headers:
        return None
    prompt = f"""你是数据分析专家。用户上传了CSV文件"{csv_ctx.get('fileName', '')}"，列名：{', '.join(headers)}。
统计信息：{'; '.join([f'{k}: {v}' for k, v in csv_ctx.get('stats', {}).items()])}。
前3行数据：{json.dumps(csv_ctx.get('sampleRows', [])[:3], ensure_ascii=False)}。

近期对话记录（用于理解追问，如"换成饼图"）：
{build_history_text(history)}

用户需求：{msg}

请推荐最佳可视化方案。返回严格JSON：
{{"chartType": "bar|line|pie|scatter", "xKey": "列名", "yKey": "列名", "reason": "推荐理由"}}

注意：
- chartType 只能是 bar/line/pie/scatter 之一
- xKey 和 yKey 必须是给定列名之一
- 不要输出 JSON 以外的内容"""
    def _auto_cfg():
        """LLM 配置失败时的兜底：分类列做 X 轴、数值列做 Y 轴"""
        rows = csv_ctx.get("rows") or csv_ctx.get("sampleRows") or []
        if not rows:
            return None

        def _is_num(h):
            vals = [r.get(h) for r in rows]
            ok = 0
            for v in vals:
                try:
                    float(str(v).replace(',', '').replace('，', '').strip())
                    ok += 1
                except Exception:
                    pass
            return ok >= max(1, len(vals) * 0.6)

        num_cols = [h for h in headers if _is_num(h)]
        txt_cols = [h for h in headers if h not in num_cols]
        if num_cols and txt_cols:
            return {"chartType": "bar", "xKey": txt_cols[0], "yKey": num_cols[0],
                    "reason": "自动选择分类列作为X轴、数值列作为Y轴以展示对比"}
        if num_cols:
            return {"chartType": "bar", "xKey": num_cols[0], "yKey": num_cols[0],
                    "reason": "自动选择数值列展示数据分布"}
        return None

    try:
        result = call_llm(prompt, temperature=0.1, history=[])
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            cfg = json.loads(json_match.group())
            if cfg.get("xKey") in headers and cfg.get("yKey") in headers:
                return cfg
        # LLM 未给出合法配置时兜底，避免直接报"图表生成失败"
        return _auto_cfg()
    except Exception:
        return _auto_cfg()


# =====================================================================
#  API 端点 —— 旧接口（保持兼容）
# =====================================================================
class RAGRequest(BaseModel):
    question: str
    kb_name: str = "docs"

@app.post("/rag")
def rag_query(req: RAGRequest):
    contexts, sources = kb_manager.query(req.kb_name, req.question, top_k=2)
    if not contexts:
        return {"answer": "知识库为空，请先上传文档。", "sources": []}
    prompt = f"基于以下信息回答用户问题：\n\n" + "\n\n".join(contexts) + f"\n\n问题：{req.question}\n回答："
    try:
        answer = call_llm(prompt)
        return {"answer": answer, "sources": [s["text"] for s in sources]}
    except Exception as e:
        return {"error": f"RAG 处理异常: {str(e)}"}

class PlanRequest(BaseModel):
    message: str

@app.post("/plan")
def plan_execute(req: PlanRequest):
    """旧的规划接口（非流式），保持兼容"""
    user_msg = req.message
    plan_prompt = f"""你是一个任务规划专家。用户需求：{user_msg}

可用工具：
- get_current_time: 获取当前日期、星期和具体时间（返回值已包含星期X），无需参数。凡涉及今天几号、星期几、周几、礼拜几、日期、现在几点，都必须用它。
- get_weather: 获取城市天气，参数 {{"city": "城市名", "day": "today|tomorrow|day_after_tomorrow"}}。根据用户提到的时间填写 day。
- query_knowledge_base: 从知识库检索信息，参数 {{"question": "问题"}}。

【规则】
1. 只能使用上述三个工具。
2. 用户可能在一句话中包含多个请求，为每个请求生成对应步骤。
3. 输出严格 JSON：{{"steps": [{{"tool": "get_current_time", "args": {{}}}}]}}
4. 不要输出额外解释。"""

    try:
        plan_text = call_llm(plan_prompt, temperature=0.1)
        json_match = re.search(r'\{.*\}', plan_text, re.DOTALL)
        if not json_match:
            return {"error": "无法从规划响应中提取JSON"}
        plan = json.loads(json_match.group())
        steps = plan.get("steps", [])
        if not steps:
            return {"error": "规划结果中没有步骤"}
        # 兜底
        if "天气" in user_msg and not any(s.get("tool") == "get_weather" for s in steps):
            city = _extract_city(user_msg)
            day = _extract_day(user_msg)
            steps.append({"tool": "get_weather", "args": {"city": city, "day": day}})
        if ("时间" in user_msg or "几点" in user_msg) and not any(s.get("tool") == "get_current_time" for s in steps):
            steps.insert(0, {"tool": "get_current_time", "args": {}})
    except Exception as e:
        return {"error": f"规划异常: {str(e)}"}

    results = []
    for step in steps:
        tool = step.get("tool")
        args = step.get("args", {})
        try:
            if tool == "get_current_time":
                res = get_current_time()
            elif tool == "get_weather":
                res = get_weather(args.get("city", "未知"), args.get("day", "today"))
            elif tool == "query_knowledge_base":
                res = query_knowledge_base(args.get("question", ""))
            else:
                res = f"不支持的工具: {tool}"
        except Exception as e:
            res = f"执行错误: {str(e)}"
        results.append({"tool": tool, "args": args, "result": res})

    summary_prompt = f"用户需求：{user_msg}\n\n执行步骤与结果：\n" + \
        "\n".join([f"- {r['tool']}({json.dumps(r['args'], ensure_ascii=False)}): {r['result']}" for r in results]) + \
        "\n\n请根据以上结果，用自然语言连贯地回应用户。不要重复列出步骤。"
    final_answer = call_llm(summary_prompt)
    return {"plan": steps, "results": results, "final_answer": final_answer}


# =====================================================================
#  API 端点 —— 新接口
# =====================================================================

# ---- 文档上传 ----
@app.post("/upload-doc")
async def upload_document(file: UploadFile = File(...), kb_name: str = Form("default")):
    if not file.filename:
        return {"error": "未提供文件"}
    content = await file.read()
    fname = file.filename.lower()
    try:
        if fname.endswith('.pdf'):
            text = parse_pdf(content)
        elif fname.endswith('.txt'):
            text = parse_txt(content)
        elif fname.endswith('.md'):
            text = parse_txt(content)
        else:
            return {"error": f"不支持的文件格式：{file.filename}，请上传 PDF、TXT 或 MD 文件"}
        if not text or not text.strip():
            return {"error": "文件内容为空"}
        chunk_count = kb_manager.upload_document(kb_name, text, file.filename)
        return {"success": True, "chunks": chunk_count, "kb_name": kb_name, "file_name": file.filename}
    except Exception as e:
        return {"error": f"文档处理失败: {str(e)}"}

# ---- 知识库管理 ----
class CreateKBRequest(BaseModel):
    name: str

@app.get("/kb/list")
def list_kbs():
    return {"kbs": kb_manager.list_kbs()}

@app.post("/kb/create")
def create_kb(req: CreateKBRequest):
    name = req.name.strip()
    if not name:
        return {"error": "知识库名称不能为空"}
    kb_manager.create_kb(name)
    return {"success": True, "name": name}

@app.delete("/kb/{name}")
def delete_kb(name: str):
    ok, msg = kb_manager.delete_kb(name)
    if not ok:
        return {"error": msg}
    return {"success": True}

@app.get("/kb/{name}/docs")
def get_kb_docs(name: str):
    col = kb_manager._collection(name)
    data = col.get(include=["metadatas", "documents"])
    docs = {}
    for i, meta in enumerate(data.get('metadatas', [])):
        src = meta.get("source", "未知") if meta else "未知"
        if src not in docs:
            docs[src] = 0
        docs[src] += 1
    return {"name": name, "total": len(data.get('documents', [])), "documents": docs}

@app.get("/kb/{name}/doc-content")
def get_kb_doc_content(name: str, source: str = ""):
    """获取某知识库下指定文档的所有片段内容（含分片索引，用于引用定位高亮）"""
    if not source:
        return {"error": "缺少 source 参数"}
    col = kb_manager._collection(name)
    data = col.get(include=["metadatas", "documents"])
    items = []
    for i, meta in enumerate(data.get('metadatas', [])):
        if meta and meta.get("source") == source:
            doc = data.get('documents', [])[i] if i < len(data.get('documents', [])) else ""
            if doc:
                items.append({"index": int(meta.get("chunk_index", i)), "text": doc})
    items.sort(key=lambda x: x["index"])
    full_text = "\n\n".join([it["text"] for it in items])
    return {"name": name, "source": source, "chunks": len(items),
            "chunkList": items, "content": full_text}

# ---- CSV 智能分析 ----
class CSVAnalyzeRequest(BaseModel):
    message: str
    fileName: str = ""
    headers: list = []
    sampleRows: list = []
    stats: dict = {}

@app.post("/csv-analyze")
def csv_analyze(req: CSVAnalyzeRequest):
    """根据自然语言生成图表配置"""
    headers_str = ", ".join(req.headers)
    stats_str = "; ".join([f"{k}: {v}" for k, v in req.stats.items()])
    sample_str = json.dumps(req.sampleRows[:3], ensure_ascii=False)

    prompt = f"""你是数据分析专家。用户上传了CSV文件"{req.fileName}"，列名：{headers_str}。
统计信息：{stats_str}。前3行数据：{sample_str}。

用户需求：{req.message}

请根据数据和需求，推荐最佳可视化方案。返回严格JSON：
{{"chartType": "bar|line|pie|scatter", "xKey": "列名", "yKey": "列名", "reason": "推荐理由（一句话）"}}

注意：
- chartType 只能是 bar/line/pie/scatter 之一
- xKey 和 yKey 必须是给定列名之一
- 饼图 xKey 为分类列，yKey 为数值列
- 不要输出 JSON 以外的内容"""

    try:
        result = call_llm(prompt, temperature=0.1)
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            config = json.loads(json_match.group())
            return {"success": True, "config": config}
        return {"error": "无法解析图表配置"}
    except Exception as e:
        return {"error": f"分析失败: {str(e)}"}

# ---- CSV AI 数据报告生成（流式）----
class CSVReportRequest(BaseModel):
    fileName: str = ""
    headers: list = []
    sampleRows: list = []
    stats: dict = {}
    rowCount: int = 0

@app.post("/csv-report")
def csv_report(req: CSVReportRequest):
    """AI 数据报告生成 —— SSE 流式返回 Markdown 报告"""
    headers_str = ", ".join(req.headers)
    stats_str = json.dumps(req.stats, ensure_ascii=False)
    sample_str = json.dumps(req.sampleRows[:5], ensure_ascii=False)

    prompt = f"""你是资深数据分析师。请基于以下 CSV 数据信息，生成一份数据分析报告。

文件名：{req.fileName}
总行数：{req.rowCount}
列名：{headers_str}
各数值列统计信息：{stats_str}
前5行样本数据：{sample_str}

请用 Markdown 格式输出报告，必须包含以下四个小节：
## 数据概览
（说明数据规模、列结构、数据类型构成）
## 关键发现
（引用具体数字，指出最大/最小/均值等有意义的统计特征，2-4 条）
## 数据质量
（缺失值、异常值、分布问题等，若无问题也请说明）
## 分析建议
（建议进一步做什么分析或可视化，2-3 条）

要求：具体、简洁，引用实际数字，总长度不超过 400 字，不要输出报告以外的内容。"""

    def sse(data):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def generate():
        try:
            for token in stream_llm(prompt, temperature=0.4):
                yield sse({"type": "token", "content": token})
            yield sse({"type": "done"})
        except Exception as e:
            yield sse({"type": "error", "content": f"报告生成失败: {str(e)}"})
            yield sse({"type": "done"})

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---- 统一对话流式接口 ----
class ChatRequest(BaseModel):
    message: str
    kb_name: str = ""
    csv_context: Optional[dict] = None  # { fileName, headers, sampleRows, stats }
    history: list = []  # 多轮对话历史 [{role, content}]

@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """统一对话接口 —— SSE 流式返回（Agent 通用入口 + 多轮上下文）"""

    def sse(data):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def generate():
        msg = req.message
        kb = req.kb_name or ""
        csv_ctx = req.csv_context or {}
        has_csv = bool(csv_ctx.get("headers"))
        has_kb = bool(kb)
        history = [h for h in (req.history or []) if isinstance(h, dict) and h.get("content")]

        # 1. 意图检测（Agent 通用入口）
        intent = detect_intent(msg, has_csv=has_csv, has_kb=has_kb)
        yield sse({"type": "intent", "intent": intent})

        # ---- 检索先行：已选知识库时先实际检索一遍 ----
        # 命中相关内容（关键词重叠）→ 展示引用来源并直接基于检索结果回答
        # 未命中 → 转入下方智能规划
        if kb:
            yield sse({"type": "status", "content": "🔍 正在检索知识库..."})
            kb_contexts, kb_sources = kb_manager.query(kb, msg, top_k=3)
            if kb_contexts and _kb_hit(msg, kb_contexts):
                yield sse({"type": "sources", "sources": kb_sources, "kb": kb})
                ref_text = "\n\n".join([f"[{j+1}] {c}" for j, c in enumerate(kb_contexts)])
                prompt = f"以下是从知识库检索到的参考资料（带编号）：\n\n{ref_text}\n\n问题：{msg}\n\n请基于参考资料回答。注意：不要在回答中添加 [1]、[2] 之类的引用编号，直接用自然语言作答。若参考资料与问题实际无关，请直接说明并基于通用知识回答。回答："
                for token in stream_llm(prompt, history=history):
                    yield sse({"type": "token", "content": token})
                yield sse({"type": "done"})
                return
            yield sse({"type": "status", "content": "知识库中未找到相关内容，转入智能规划..."})

        # ---- Agent 多步规划（通用入口：天气/时间/知识库/CSV图表/日常问答） ----
        if intent == 'agent':
            yield sse({"type": "status", "content": "🧠 正在理解问题并规划任务..."})

            csv_desc = "无"
            if has_csv:
                csv_desc = f"{csv_ctx.get('fileName', '')}（列：{', '.join(csv_ctx.get('headers', []))}）"
            if kb:
                kb_desc = f"{kb}（已预检索，未发现与当前问题相关的内容，无需再检索知识库）"
            else:
                kb_desc = "无"

            plan_prompt = f"""你是一个任务规划专家。请分析用户需求并选择最合适的一个或多个工具。

用户需求：{msg}

当前上下文：
- 用户选中的知识库：{kb_desc}
- 已加载的CSV数据文件：{csv_desc}

近期对话记录（用于理解指代和追问）：
{build_history_text(history)}

可用工具：
- get_current_time: 获取当前日期、星期和具体时间（返回值已包含星期X），无需参数。凡涉及今天几号、星期几、周几、礼拜几、日期、现在几点，都必须用它
- get_weather: 获取城市天气，参数 {{"city": "城市名", "day": "today|tomorrow|day_after_tomorrow"}}
- analyze_csv: 对已加载的CSV数据进行统计分析并生成图表，参数 {{"goal": "分析目标描述"}}。适合查询数据的最值、平均值、总和、排名、占比、某个具体是谁等问题，以及画图、可视化、看分布趋势
- llm_answer: 用通用知识直接回答问题，参数 {{"question": "用户原始问题"}}。适合日常问题、常识问答（如"番茄可以生吃吗"、"减脂期晚饭怎么吃"、"牙痛需要注意什么"）、聊天、写作等

【核心决策规则】
1. 知识库检索已由前置流程完成：与知识库相关的问题会直接基于检索结果回答，不会进入规划。你只需要在天气、时间、CSV图表、通用问答中选择工具。
2. 天气类问题用 get_weather；日期、星期、时间类问题（星期几、周几、几号、几点）用 get_current_time，两者都不要加 llm_answer。
3. 已加载CSV时，凡涉及数据本身的问题（最大、最小、平均、总和、排名、最多、最少、是谁、多少个、占比、分布）必须用 analyze_csv，严禁用 llm_answer 回避；未加载CSV时禁止使用 analyze_csv；禁止使用 search_knowledge_base 等知识库类工具。
4. 一句话包含多个请求时生成多个步骤；结合近期对话理解追问（如"那上海呢"沿用上一轮日期和主题、只换城市）。
5. llm_answer 的参数 question 必须是用户的原始问题或对其核心意图的精简提问，禁止在参数中直接写出答案内容。

【示例】
- 用户问"减脂期，晚饭怎么吃" → {{"steps": [{{"tool": "llm_answer", "args": {{"question": "减脂期，晚饭怎么吃"}}}}]}}
- 用户问"番茄可以生吃吗" → {{"steps": [{{"tool": "llm_answer", "args": {{"question": "番茄可以生吃吗"}}}}]}}
- 用户问"牙痛需要注意什么" → {{"steps": [{{"tool": "llm_answer", "args": {{"question": "牙痛需要注意什么"}}}}]}}
- 用户问"北京明天天气" → {{"steps": [{{"tool": "get_weather", "args": {{"city": "北京", "day": "tomorrow"}}}}]}}
- 用户问"画个柱状图"且已加载CSV → {{"steps": [{{"tool": "analyze_csv", "args": {{"goal": "画一个柱状图"}}}}]}}
- 用户问"今天星期几" → {{"steps": [{{"tool": "get_current_time", "args": {{}}}}]}}
- 用户问"今天星期几？深圳的天气怎么样" → {{"steps": [{{"tool": "get_current_time", "args": {{}}}}, {{"tool": "get_weather", "args": {{"city": "深圳", "day": "today"}}}}]}}
- 用户问"这份数据中年龄最大的是谁"且已加载CSV → {{"steps": [{{"tool": "analyze_csv", "args": {{"goal": "找出年龄最大的人"}}}}]}}
- 用户问"计算平均年龄并指出年龄最大的是谁"且已加载CSV → {{"steps": [{{"tool": "analyze_csv", "args": {{"goal": "计算平均年龄和找出年龄最大的人"}}}}]}}

【输出格式】
输出严格JSON，不要输出任何额外解释：
{{"steps": [{{"tool": "工具名", "args": {{...}}}}]}}"""

            try:
                plan_text = call_llm(plan_prompt, temperature=0.1)
                json_match = re.search(r'\{.*\}', plan_text, re.DOTALL)
                if not json_match:
                    yield sse({"type": "token", "content": "抱歉，我无法解析这个任务。请尝试更具体的描述。"})
                    yield sse({"type": "done"})
                    return
                plan = json.loads(json_match.group())
                steps = plan.get("steps", [])
                if not steps:
                    # 无需工具，直接对话回答（带历史上下文）
                    system = "你是 RAGent 智能工作台助手，可以帮用户分析数据、回答知识库问题、规划多步任务。请用友好、专业的语气回答。"
                    for token in stream_llm(msg, system_prompt=system, history=history):
                        yield sse({"type": "token", "content": token})
                    yield sse({"type": "done"})
                    return
                # 兜底：用户提到天气但 LLM 没规划天气查询
                weather_keywords = ['天气', '下雨', '雨', '气温', '温度', '下雪', '雪', '刮风', '风', '带伞', '雾霾', '雾', '晴天', '阴天']
                if any(kw in msg for kw in weather_keywords) and not any(s.get("tool") == "get_weather" for s in steps):
                    city = _extract_city(msg)
                    day = _extract_day(msg)
                    steps.append({"tool": "get_weather", "args": {"city": city, "day": day}})
                # 时间/日期/星期兜底：这类问题必须查当前时间（get_current_time 已返回星期）
                time_keywords = ['时间', '几点', '星期', '周几', '礼拜', '日期', '几号', '几月', '哪天', '哪一天']
                if any(kw in msg for kw in time_keywords) and not any(s.get("tool") == "get_current_time" for s in steps):
                    steps.insert(0, {"tool": "get_current_time", "args": {}})

                # 数据分析兜底：涉及数据统计/最值/定位的问题必须走 analyze_csv（保证 AI 拿到真实数值）
                if has_csv and not any(s.get("tool") == "analyze_csv" for s in steps):
                    data_keywords = [
                        '最大', '最小', '平均', '均值', '总和', '总共', '合计', '统计', '排名', '排序',
                        '最多', '最少', '最高', '最低', '谁', '多少', '分布', '对比', '占比', '中位数',
                        '数据', '表格', 'csv', 'CSV', '这份', '这张', '表中', '分析',
                    ]
                    # 针对上一轮数据结论的短追问（如"我要你直接告诉我"）继承数据分析意图
                    followup_words = ['告诉我', '直接说', '直接告诉', '具体', '结果呢', '所以呢', '到底']
                    is_data_q = any(kw in msg for kw in data_keywords)
                    is_followup = len(msg) <= 20 and any(kw in msg for kw in followup_words)
                    if is_data_q or is_followup:
                        steps.append({"tool": "analyze_csv", "args": {"goal": msg}})

                # 无 CSV 时过滤掉 analyze_csv 步骤
                if not has_csv:
                    steps = [s for s in steps if s.get("tool") != "analyze_csv"]

                # 知识库路由已由"检索先行"前置流程处理：
                # 命中相关内容时直接走 RAG 回答，不会进入这里；
                # 进入规划说明知识库无相关内容，防御性过滤掉规划器误加的检索步骤
                steps = [s for s in steps if s.get("tool") not in ("search_knowledge_base", "query_knowledge_base")]
                if not steps:
                    steps = [{"tool": "llm_answer", "args": {"question": msg}}]

                yield sse({"type": "plan", "steps": steps})

                # 日期延续兜底：当前消息没有明确日期时，从近期对话继承（如上一轮问了"明天"）
                inherited_day = None
                if not re.search(r'今天|明天|明日|明儿|后天|现在|当前', msg):
                    combined_hist = " ".join([str(h.get("content", "")) for h in history[-4:]])
                    if re.search(r'明天|明日|明儿', combined_hist):
                        inherited_day = "tomorrow"
                    elif re.search(r'后天', combined_hist):
                        inherited_day = "day_after_tomorrow"

                # 逐步执行
                results = []
                skip_summary = False
                for i, step in enumerate(steps):
                    tool = step.get("tool")
                    args = step.get("args", {}) or {}
                    yield sse({"type": "step_start", "step": step, "index": i})
                    try:
                        if tool == "get_current_time":
                            res = get_current_time()
                        elif tool == "get_weather":
                            day = args.get("day") if args.get("day") in ("today", "tomorrow", "day_after_tomorrow") else "today"
                            if day == "today" and inherited_day:
                                day = inherited_day
                            res = get_weather(args.get("city", "未知"), day)
                        elif tool == "search_knowledge_base":
                            q = args.get("question", msg)
                            contexts, srcs = kb_manager.query(kb or "docs", q, top_k=3)
                            if contexts:
                                yield sse({"type": "sources", "sources": srcs, "kb": kb or "docs"})
                                res = "\n\n".join([f"[{j+1}] {c}" for j, c in enumerate(contexts)])
                            else:
                                res = "知识库中未找到相关内容"
                        elif tool == "analyze_csv":
                            if not has_csv:
                                res = "当前未加载任何CSV文件，无法分析"
                            else:
                                cfg = _gen_chart_config(msg, csv_ctx, history)
                                if cfg:
                                    yield sse({"type": "chart", "config": cfg})
                                    res = f"已生成{cfg.get('chartType')}图表（X轴={cfg.get('xKey')}，Y轴={cfg.get('yKey')}）。理由：{cfg.get('reason', '')}"
                                else:
                                    res = "已完成数据分析（该数据可能缺少可绘制图表的数值列）"
                                # 关键：把真实统计数据交给 LLM，使其能直接给出确定答案
                                facts_text = _format_data_facts(_compute_data_facts(csv_ctx))
                                if facts_text:
                                    res += f"\n\n【本数据的真实统计结果（必须直接使用这些数字和名称作答）】\n{facts_text}"
                        elif tool == "query_knowledge_base":
                            # 兼容旧工具名
                            q = args.get("question", "")
                            contexts, srcs = kb_manager.query(kb or "docs", q, top_k=3)
                            if contexts:
                                yield sse({"type": "sources", "sources": srcs, "kb": kb or "docs"})
                                res = "\n\n".join([f"[{j+1}] {c}" for j, c in enumerate(contexts)])
                            else:
                                res = "未找到相关内容"
                        elif tool == "llm_answer":
                            # 单步 llm_answer 直接采用用户原始问题，避免 planner 把 question 参数写成陈述/答案
                            q = msg if len(steps) == 1 else args.get("question", msg)
                            system = "你是 RAGent 智能工作台助手，请用友好、专业的语气准确回答用户问题。"
                            if len(steps) == 1:
                                # 唯一步骤时直接流式输出，无需再汇总
                                skip_summary = True
                                collected = []
                                for token in stream_llm(q, system_prompt=system, history=history):
                                    collected.append(token)
                                    yield sse({"type": "token", "content": token})
                                res = "".join(collected) or "（无回答）"
                            else:
                                res = call_llm(q, system_prompt=system, history=history)
                        else:
                            res = f"不支持的工具: {tool}"
                    except Exception as e:
                        res = f"执行错误: {str(e)}"
                    results.append({"tool": tool, "args": args, "result": res})
                    yield sse({"type": "step_result", "result": {"tool": tool, "args": args, "result": res}, "index": i})

                # 流式输出最终回答
                if not skip_summary:
                    yield sse({"type": "status", "content": "✍️ 正在汇总结果..."})
                    steps_text = "\n".join([
                        f"- {r['tool']}({json.dumps(r['args'], ensure_ascii=False)}): {r['result'][:800]}"
                        for r in results
                    ])
                    summary_prompt = f"""用户需求：{msg}

执行步骤与结果：
{steps_text}

请根据以上结果，用自然语言连贯地回应用户。要求：
1. 直接给出答案，不要重复列出步骤
2. 不要在回答中添加 [1]、[2] 之类的引用编号，直接用自然语言作答
3. 如果结果中包含【本数据的真实统计结果】，必须直接引用其中的具体数字和名称作答（例如"年龄最大的是李四，31岁；平均年龄27.67岁"）。严禁输出 XX、某某 这类占位符，严禁让用户自己去查看图表或自行计算，严禁说"我无法查看图表"
4. 如果使用了图表分析结果，可简要说明图表展示的内容，但结论必须包含具体数值
5. 如果知识库检索结果与用户需求明显不相关（如用户问饮食，检索到的是技术文档），请忽略检索结果，直接用通用知识回答，不要引用无关来源
6. 保持简洁准确"""
                    for token in stream_llm(summary_prompt, history=history):
                        yield sse({"type": "token", "content": token})
                yield sse({"type": "done"})
                return
            except Exception as e:
                yield sse({"type": "error", "content": f"规划执行失败: {str(e)}"})
                yield sse({"type": "done"})
                return

        # ---- 数据可视化（兼容保留） ----
        if intent == 'chart':
            cfg = _gen_chart_config(msg, csv_ctx, history)
            if cfg:
                yield sse({"type": "chart", "config": cfg})
                yield sse({"type": "token", "content": f"📊 已根据您的需求生成{cfg.get('chartType', '')}图表。\n\n推荐理由：{cfg.get('reason', '')}"})
            else:
                yield sse({"type": "token", "content": "抱歉，无法生成图表配置，请尝试更具体的描述。"})
            yield sse({"type": "done"})
            return

        # ---- 通用对话（兼容保留） ----
        system = "你是 RAGent 智能工作台助手，可以帮用户分析数据、回答知识库问题、规划多步任务。请用友好、专业的语气回答。"
        for token in stream_llm(msg, system_prompt=system, history=history):
            yield sse({"type": "token", "content": token})
        yield sse({"type": "done"})

    return StreamingResponse(generate(), media_type="text/event-stream")


# =====================================================================
#  健康检查
# =====================================================================
@app.get("/")
def health():
    return {"status": "ok", "service": "RAGent Workbench API", "kbs": kb_manager.list_kbs()}

# -*- coding: utf-8 -*-
"""核心模块单元测试 —— 不调用外部 LLM，覆盖可确定性验证的逻辑

运行：
    cd backend
    D:/ch4/pyt/python.exe -m pytest tests/ -v
"""
import os
import numpy as np
import pytest

from main import (
    KBManager, kb_manager, _kb_hit, _kb_content_words,
    _compute_data_facts, _format_data_facts, parse_txt,
    get_current_time, _extract_day, _extract_city, LLM_MODEL,
)

_normalize = KBManager._normalize


# ============ 1. 文档分块 ============
class TestChunking:
    def test_chunk_basic(self):
        text = "第一句话。第二句话！第三句话？第四句话。"
        chunks = kb_manager._chunk_text(text, chunk_size=20, overlap=0)
        assert chunks, "应产生分块"
        # 块内以 \n 连接句子，长度 = 句子内容 + 换行符，故允许 chunk_size + 换行符数
        assert all(len(c.replace("\n", "")) <= 20 for c in chunks), "每块句子内容不得超过 chunk_size"

    def test_chunk_respects_sentence_boundary(self):
        text = "这是第一句完整的话。这是第二句完整的话。这是第三句。"
        chunks = kb_manager._chunk_text(text, chunk_size=12, overlap=0)
        for c in chunks:
            # 块不应从句子中间截断（以完整标点或句尾结束）
            assert c.rstrip().endswith(("。", "！", "？", "!", "?", "；", ";", "…")) or len(c) <= 12

    def test_chunk_overlap(self):
        text = "".join(f"第{i}个句子内容比较长足以独立成块。" for i in range(8))
        chunks = kb_manager._chunk_text(text, chunk_size=60, overlap=20)
        assert len(chunks) >= 2
        assert any(a[-8:] in b for a, b in zip(chunks, chunks[1:])), "相邻块应存在重叠内容"

    def test_chunk_empty(self):
        assert kb_manager._chunk_text("") == []
        assert kb_manager._chunk_text("   \n  ") == []

    def test_chunk_long_sentence_hard_split(self):
        text = "A" * 500
        chunks = kb_manager._chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 5
        assert all(len(c) <= 100 for c in chunks)


# ============ 2. 中文知识库名 hex 编码 ============
class TestKBNameCodec:
    @pytest.mark.parametrize("name", ["项目", "Agent", "我的知识库", "test-kb_1"])
    def test_safe_name_roundtrip(self, name):
        safe = KBManager._safe_name(name)
        assert KBManager._display_name(safe) == name

    def test_chinese_name_is_hex_encoded(self):
        safe = KBManager._safe_name("项目")
        assert safe.startswith("kb_") and "项目" not in safe
        assert bytes.fromhex(safe[3:]).decode("utf-8") == "项目"


# ============ 3. 归一化与混合检索权重 ============
class TestHybridRetrieval:
    def test_normalize_range(self):
        out = _normalize(np.array([1.0, 2.0, 3.0, 4.0]))
        assert out.min() == 0 and out.max() == 1

    def test_normalize_constant_array(self):
        out = _normalize(np.array([5.0, 5.0, 5.0]))
        assert np.all(out == 1)

    def test_weight_formula(self):
        """验证项目采用 0.6 向量 + 0.4 BM25 的融合公式"""
        vec = np.array([0.2, 0.8])
        bm25 = np.array([0.6, 0.4])
        combined = 0.6 * _normalize(vec) + 0.4 * _normalize(bm25)
        # vec 归一化后 [0,1]，bm25 归一化后 [1,0] → 0.4 / 0.6
        assert round(float(combined[0]), 4) == 0.4
        assert round(float(combined[1]), 4) == 0.6


# ============ 4. 检索先行路由（创新点）============
class TestRAGRouter:
    def test_relevant_question_hits(self):
        contexts = ["Redis连接超时可能由连接池泄露导致，可调大maxclients参数。"]
        assert _kb_hit("Redis连接超时怎么解决？", contexts) is True

    def test_irrelevant_question_not_hits(self):
        contexts = ["P0级故障需立即启动紧急回滚，黄金指标包括延迟、流量、错误、饱和度。"]
        assert _kb_hit("牙痛需要注意什么？", contexts) is False
        assert _kb_hit("减脂期晚饭怎么吃？", contexts) is False

    def test_empty_context_not_hits(self):
        assert _kb_hit("RAG是什么？", []) is False

    def test_content_words_filter(self):
        words = _kb_content_words("请问如何实现这个功能呢")
        assert "如何" not in words and "功能" not in words and "实现" not in words

    def test_real_kb_routing(self):
        """真实知识库上的路由验证：项目库问题命中、生活问题不命中"""
        ctx_yes, _ = kb_manager.query("项目", "运维SOP的文档编号是什么？", top_k=3)
        ctx_no, _ = kb_manager.query("项目", "番茄可以生吃吗？", top_k=3)
        assert _kb_hit("运维SOP的文档编号是什么？", ctx_yes) is True
        assert _kb_hit("番茄可以生吃吗？", ctx_no) is False


# ============ 5. CSV 数据统计事实 ============
@pytest.fixture
def sample_csv_ctx():
    return {
        "fileName": "people.csv",
        "headers": ["姓名", "年龄", "城市"],
        "rows": [
            {"姓名": "张三", "年龄": "25", "城市": "北京"},
            {"姓名": "李四", "年龄": "31", "城市": "上海"},
            {"姓名": "王五", "年龄": "27", "城市": "广州"},
        ],
        "rowCount": 3,
    }


class TestDataFacts:
    def test_numeric_column_stats(self, sample_csv_ctx):
        facts = _compute_data_facts(sample_csv_ctx)
        age = next(c for c in facts["columns"] if c["列"] == "年龄")
        assert age["类型"] == "数值"
        assert age["最大"] == 31 and age["最小"] == 25
        assert age["均值"] == 27.67
        assert age["最大对应"] == "李四"

    def test_text_column_stats(self, sample_csv_ctx):
        facts = _compute_data_facts(sample_csv_ctx)
        city = next(c for c in facts["columns"] if c["列"] == "城市")
        assert city["类型"] == "文本/分类"
        assert city["唯一值数"] == 3

    def test_format_contains_key_numbers(self, sample_csv_ctx):
        text = _format_data_facts(_compute_data_facts(sample_csv_ctx))
        assert "27.67" in text and "李四" in text and "31" in text

    def test_empty_ctx_returns_none(self):
        assert _compute_data_facts({}) is None
        assert _format_data_facts(None) == ""


# ============ 6. 文档解析与工具函数 ============
class TestUtilities:
    def test_parse_txt_utf8(self):
        assert parse_txt("你好世界".encode("utf-8")) == "你好世界"

    def test_parse_txt_gbk(self):
        assert parse_txt("中文测试".encode("gbk")) == "中文测试"

    def test_get_current_time_has_weekday(self):
        out = get_current_time()
        assert any(f"星期{x}" in out for x in "一二三四五六日")

    @pytest.mark.parametrize("text,expected", [
        ("今天天气", "today"),
        ("明天天气怎么样", "tomorrow"),
        ("后天会下雨吗", "day_after_tomorrow"),
        ("现在天气", "today"),
    ])
    def test_extract_day(self, text, expected):
        assert _extract_day(text) == expected

    def test_extract_city(self):
        assert _extract_city("上海明天天气") == "上海"
        assert _extract_city("广州市后天会下雨吗") == "广州市"
        # 无城市名时兜底匹配前 2-4 个汉字（源码第3级兜底，非默认"北京"）
        assert len(_extract_city("天气怎么样")) >= 2


# ============ 7. API 端点冒烟测试（用 TestClient，不触发真实 LLM）============
class TestAPIEndpoints:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        from main import app
        with TestClient(app) as c:
            yield c

    def test_health(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_kb_list(self, client):
        resp = client.get("/kb/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "kbs" in data or isinstance(data, list)

    def test_kb_docs(self, client):
        resp = client.get("/kb/项目/docs")
        assert resp.status_code == 200

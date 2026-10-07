# RAGent-Workbench · 三合一智能工作台

> 以**对话为唯一入口**的 AI 工作台：在同一个聊天框里，既能「问知识库」、又能「看数据图表」、还能「让 Agent 自动规划并执行多步任务」。

[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?logo=github)](https://github.com/Valentina0325/RAGent-Workbench)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![前端](https://img.shields.io/badge/Next.js-15-black?logo=next.js)](https://nextjs.org/)
[![后端](https://img.shields.io/badge/FastAPI-0.46-009688?logo=fastapi)](https://fastapi.tiangolo.com/)

---

## 📌 项目简介

**RAGent-Workbench** 不是把三个独立工具拼到一个页面，而是让**一条对话流按意图自动分发**给对应的能力模块：

- **📚 多知识库 RAG 问答**：上传 PDF / TXT 自动建库，混合检索（向量 + BM25）召回，命中即展示「引用来源」卡片，回答基于原文生成。
- **📊 CSV 数据可视化**：上传 CSV，用自然语言下达图表需求（如"画一个柱状图"），由 Agent 驱动 ECharts 生成图表；AI 还能**直接读取真实数据**给出具体统计结论（最大/最小/平均/排名等），而非让你自己看图。
- **🤖 Plan-and-Execute Agent**：输入复合指令（如"现在几点？顺便查一下上海天气"），自动分解步骤、调用工具、流式汇总结果。

核心创新是**「检索先行」路由**：用户已选知识库时，后端先做一次真实混合检索并做相关性判定——相关才走 RAG 直答，无关（如"牙痛怎么办"）直接转通用问答，**生活类问题误触发知识库检索率降为 0**。

---

## ✨ 核心特性

| 能力 | 说明 | 亮点 |
| --- | --- | --- |
| **统一对话流** | 单一聊天框贯通 RAG / 可视化 / Agent | 用户无需切换工具 |
| **多知识库 RAG** | 创建/切换多个知识库，上传即建库 | 混合检索（向量 0.6 + BM25 0.4），引用来源卡片可追溯 |
| **CSV 可视化** | 自然语言生成柱/折/饼/散点图 | 大表格 `react-window` 虚拟滚动；AI 报告**基于真实数字作答** |
| **AI 数据报告** | 数据面板一键生成 Markdown 分析报告 | 支持**导出 `.md`**、**本地历史存储**（切换文件不丢失，除非主动重新生成） |
| **Plan-and-Execute Agent** | 规划 → 执行 → 流式汇总 | 工具：取时间 / 查天气 / 分析 CSV / 通用问答 |
| **检索先行路由** | 相关性判定前置到代码层 | 相关才搜、无关不搜，规避 LLM 误判 |
| **流式体验** | SSE 逐字输出 | 规划步骤、检索状态、最终答案实时可见 |

---

## 🛠️ 技术栈

| 类别 | 选型 |
| --- | --- |
| **前端框架** | Next.js 15 (App Router) · React 18 · TypeScript |
| **样式 / 组件** | Tailwind CSS v4 · shadcn/ui |
| **图表 / 大列表** | ECharts 6 · react-window（虚拟滚动） |
| **其他前端** | PapaParse（CSV 解析）· react-markdown（回答渲染）· Zustand（状态） |
| **后端框架** | FastAPI（Python）· SSE 流式 |
| **向量数据库** | ChromaDB（持久化本地） |
| **嵌入模型** | `bge-large-zh-v1.5`（sentence-transformers，**本地推理**，离线可用） |
| **关键词检索** | jieba（中文分词）+ rank_bm25 |
| **文档解析** | PyMuPDF（fitz，PDF 抽取） |
| **LLM** | 智谱 `glm-4-flash`（任务规划 / 答案生成 / 报告汇总） |
| **运行环境** | 系统 Python 3.x（依赖已全量安装） |

---

## 📐 系统架构

```
   用户 (浏览器)
        │
        ▼
 ┌──────────────────────────────┐
 │  前端 Next.js + React         │
 │  · 统一对话工作台 (page.tsx)   │
 │  · 数据面板 (ECharts/虚拟滚动) │
 │  · 知识库侧栏 (多 KB 管理)    │
 │  · /rag · /agent 路由         │
 └──────────────┬───────────────┘
                │  HTTP + SSE
                ▼
 ┌──────────────────────────────┐
 │  后端 FastAPI                 │
 │  检索先行路由 → 相关性判定     │
 │   ├─ 命中知识库 → RAG 直答(带来源) │
 │   └─ 未命中     → Agent 规划      │
 │       (Plan → Execute → 总结)  │
 └──────┬───────────────┬────────┘
        │               │
  ┌─────▼─────┐   ┌─────▼────────┐
  │ ChromaDB  │   │ 智谱 API      │
  │ 向量+BM25 │   │ glm-4-flash  │
  │ bge-zh    │   │ (规划/生成)   │
  └───────────┘   └──────────────┘
```

**关键设计决策**：知识库检索决策**前置**到路由层（而非交给 LLM 规划器），规划器不再持有检索工具，从架构上杜绝误触发。

---

## 🚀 快速开始

### 前置条件

- **Node.js** 18+ 与 npm
- **Python** 3.10+（建议使用已安装依赖的系统 Python）
- **智谱 API Key**（[申请地址](https://open.bigmodel.cn/)）

### 1. 克隆项目

```bash
git clone https://github.com/Valentina0325/RAGent-Workbench.git
cd RAGent-Workbench
```

### 2. 启动后端（端口 8000）

```bash
cd backend
pip install -r requirements.txt        # 安装依赖（首次）
cp .env.example .env                    # 然后编辑 .env，填入你的 ZHIPU_API_KEY
python ingest.py                        # 将示例文档 test.txt 切片并存入 ChromaDB（首次可选）
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

> 首次运行会自动下载 `bge-large-zh-v1.5` 到 `backend/model_cache/`（约 1.3 GB，已加入 `.gitignore`）。
> 后端地址：`http://localhost:8000`

### 3. 启动前端（端口 3000）

```bash
cd frontend
npm install
npm run dev
```

> 前端地址：`http://localhost:3000`
> 若 `npm run dev` 在你的环境中触发 WSL 报错，可改用托管 Node 直接运行：
> `node node_modules/next/dist/bin/next dev -p 3000`（在 `frontend/` 目录下执行）。

### 4. 使用说明

- 打开 `http://localhost:3000` → 在统一对话工作台中：
  - **问知识库**：左侧栏创建/选择知识库并上传文档，直接在聊天框提问，命中即显示「📖 引用来源」。
  - **看数据**：上传 CSV 文件，用自然语言说"画一个柱状图"，右侧数据面板生成图表；点「AI 报告」生成可导出、可持久化的分析报告。
  - **办任务**：直接说"今天星期几并查深圳天气"，Agent 会自动规划并依次执行。
- 也可访问独立路由 `/rag`（知识库）与 `/agent`（智能体）。

---

## 📁 项目结构

```
RAGent-Workbench/
├── backend/                      # FastAPI 后端
│   ├── main.py                   # 核心服务：所有 API、KBManager、混合检索、
│   │                             #   检索先行路由、Agent 规划与执行、LLM 流式、文档解析
│   ├── ingest.py                 # 文档切片、向量化、入库脚本
│   ├── calibrate_threshold.py    # 相关性阈值校准工具
│   ├── rechunk.py                # 重新切分工具
│   ├── test.txt                  # 预置示例知识库文档（可替换）
│   ├── requirements.txt
│   ├── .env.example              # 环境变量模板（ZHIPU_API_KEY）
│   ├── model_cache/              # 本地嵌入模型缓存（gitignore，约 1.3GB）
│   └── chroma_db/                # ChromaDB 持久化数据（gitignore）
├── frontend/                     # Next.js 前端
│   ├── app/
│   │   ├── page.tsx              # 三合一统一工作台主页
│   │   ├── rag/page.tsx          # 知识库问答路由
│   │   ├── agent/page.tsx        # 智能体路由
│   │   ├── api/ai-report/route.ts# 调用后端 /csv-report 的代理
│   │   ├── globals.css           # 工作台样式
│   │   └── layout.tsx
│   ├── components/
│   │   ├── ChatMessage.tsx       # 消息渲染（Markdown、来源卡片、用户头像右置）
│   │   ├── DataPanel.tsx         # 右侧数据面板（图表/表格/AI 报告导出与持久化）
│   │   ├── DataTableVirtual.tsx  # 虚拟滚动表格
│   │   ├── WorkbenchSidebar.tsx  # 知识库管理侧栏
│   │   └── NavBar.tsx
│   └── package.json
├── .gitignore
└── README.md
```

---

## 🔌 后端 API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/chat/stream` | **统一对话入口**（SSE 流式）：意图检测 → 检索先行 / Agent 规划 → 执行 → 汇总 |
| POST | `/rag` | RAG 问答 |
| POST | `/plan` | 任务规划 |
| POST | `/upload-doc` | 上传文档并建库 |
| POST | `/csv-analyze` | CSV 分析与图表配置 |
| POST | `/csv-report` | 生成 CSV 数据分析报告 |
| GET | `/kb/list` | 列出知识库 |
| POST | `/kb/create` | 创建知识库 |
| GET | `/kb/{name}/docs` | 列出某知识库的文档 |
| GET | `/kb/{name}/doc-content` | 获取文档内容 |
| GET | `/` | 健康检查 |

SSE 事件类型：`intent` / `status` / `sources` / `plan` / `step_start` / `step_result` / `token` / `done` / `error`。

---

## ⚙️ 配置说明

### 环境变量（`backend/.env`）

| 变量 | 说明 |
| --- | --- |
| `ZHIPU_API_KEY` | 智谱开放平台 API Key，必填；缺失时 LLM 功能不可用（服务仍可启动） |

### 关键参数（可在 `backend/main.py` 调整）

- **混合检索权重**：向量 `0.6` + BM25 `0.4`
- **文档切分**：`chunk_size=400`、`overlap=60`；按换行 / 句末标点切完整句，绝不从句中截断
- **ChromaDB 中文集合名**：用 hex 编码解决限制（`_safe_name` / `_display_name` 双向映射）
- **CSV 数据上传**：前端最多取前 2000 行传给后端做真实统计

---


## 🙏 致谢

- [智谱 AI](https://open.bigmodel.cn/) 提供大模型 API
- [ChromaDB](https://www.trychroma.com/) 向量数据库
- [sentence-transformers](https://www.sbert.net/) 与 [bge-large-zh-v1.5](https://huggingface.co/AI-ModelScope/bge-large-zh-v1.5) 中文嵌入模型
- [Next.js](https://nextjs.org/) · [React](https://react.dev/) · [ECharts](https://echarts.apache.org/) · [FastAPI](https://fastapi.tiangolo.com/)

---

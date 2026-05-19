# RAGent 智能工作台

> 一站式 AI 前端应用：CSV 数据可视化 + RAG 知识库问答 + Agent 多步任务编排

[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?logo=github)](https://github.com/Valentina0325/RAGent-Workbench)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 📌 项目简介

**RAGent 智能工作台** 是一个集成三大 AI 能力的前端应用：

- **数据仪表盘**：上传 CSV 文件，动态生成图表，AI 自动生成数据分析报告
- **RAG 知识库**：上传文档（PDF/TXT），基于混合检索进行智能问答，并显示引用来源
- **Agent 智能体**：输入复合指令（如“查北京天气并告诉我雾霾防护知识”），自动分解步骤、调用工具、汇总结果

本项目可作为 **前端 AI 开发** 或 **AI 应用开发** 的实习作品，展示 React/Next.js 工程化能力、AI 接口集成、RAG 与 Agent 实践。

---

## ✨ 功能模块

| 模块                 | 核心功能                                                     | 亮点                                      |
| -------------------- | ------------------------------------------------------------ | ----------------------------------------- |
| **📊 CSV 数据仪表盘** | 多文件上传、图表生成（柱/折/饼/散点）、AI 数据报告、虚拟滚动表格、图表导出 PNG | 支持 5MB 以内 CSV，1000+ 行数据滚动流畅   |
| **📚 RAG 知识库**     | 文档上传（PDF/TXT）、智能问答、引用溯源、历史记录存储（20 条） | 混合检索（向量 + BM25），关键词召回更准确 |
| **🤖 Agent 智能体**   | 多步规划（Plan‑and‑Execute）、工具调用（天气/时间/知识库）、可视化执行步骤 | 可处理“查天气 + 检索知识”等复合指令       |

---

## 🛠️ 技术栈

| 类别           | 技术                                          |
| -------------- | --------------------------------------------- |
| **前端框架**   | React 18, Next.js 14 (App Router), TypeScript |
| **状态管理**   | Zustand, useLocalStorage 自定义 Hook          |
| **UI 库**      | Tailwind CSS, shadcn/ui, ECharts              |
| **CSV 解析**   | PapaParse                                     |
| **虚拟滚动**   | react-window                                  |
| **后端框架**   | FastAPI (Python)                              |
| **向量数据库** | ChromaDB                                      |
| **AI 模型**    | 智谱 GLM-4-Flash, Embedding-2                 |
| **其他**       | SSE 流式处理, jieba 分词, rank_bm25           |

---

## 🚀 快速开始

### 前置条件

- Node.js 18+ & npm
- Python 3.10+
- 智谱 API Key（[申请地址](https://open.bigmodel.cn/)）

### 1. 克隆项目

```bash
git clone https://github.com/Valentina0325/RAGent-Workbench.git
cd RAGent-Workbench
```

### 2. 后端配置与运行

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填写你的 ZHIPU_API_KEY
python ingest.py        # 将 test.txt 中的文档切片并存入 ChromaDB
python -m uvicorn main:app --reload
```

后端服务将运行在 `http://localhost:8000`

### 3. 前端配置与运行

```bash
cd frontend
npm install
npm run dev
```

前端将运行在 `http://localhost:3000`

### 4. 使用说明

- 访问首页 → 上传 CSV 文件 → 选择 X/Y 轴 → 生成图表 → 点击“AI 报告”
- 访问 `/rag` → 上传文档（可选）→ 输入问题 → 获得带引用的答案
- 访问 `/agent` → 输入复合指令（如“现在几点？顺便查一下上海天气”）→ 查看规划步骤与结果

---

## 📁 项目结构

```
RAGent-Workbench/
├── frontend/                # Next.js 前端
│   ├── app/                 # 页面路由
│   │   ├── page.tsx         # 仪表盘
│   │   ├── rag/page.tsx     # RAG 知识库
│   │   ├── agent/page.tsx   # Agent 智能体
│   │   ├── api/             # Next.js API 代理（调用后端）
│   │   └── layout.tsx
│   ├── components/          # 可复用组件（NavBar, DataTableVirtual）
│   ├── hooks/               # useLocalStorage 等自定义 Hook
│   └── package.json
├── backend/                 # FastAPI 后端
│   ├── main.py              # 主服务（/rag, /function, /plan 接口）
│   ├── ingest.py            # 文档切片、向量化、入库脚本
│   ├── test.txt             # 预置知识库文档（可替换）
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

---

## 🧪 演示视频

- [点击观看 3 分钟操作录屏](https://pan.baidu.com/s/1463jjyuxB1ZKbs7DdWY4rA?pwd=1234)（提取码：1234）

---

## 🙏 致谢

- [智谱 AI](https://open.bigmodel.cn/) 提供免费大模型 API
- [ChromaDB](https://www.trychroma.com/) 向量数据库
- [Next.js](https://nextjs.org/) & [FastAPI](https://fastapi.tiangolo.com/)

---

## 📄 License

 - MIT © [Valentina0325](https://github.com/Valentina0325)

---

##如有问题或建议，欢迎提交 Issue 或联系 3641130398@qq.com
=======


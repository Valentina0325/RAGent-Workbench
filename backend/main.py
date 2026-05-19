# ========== 导入依赖 ==========
import chromadb               # 向量数据库，用于存储和检索文档向量
from fastapi import FastAPI   # Web 框架
import requests               # 发送 HTTP 请求（调用智谱 API）
import json                   # 解析 JSON
import os                     # 读取环境变量
import datetime               # 获取当前时间
from dotenv import load_dotenv  # 加载 .env 文件中的环境变量
from pydantic import BaseModel  # 定义请求体的数据结构（类型校验）
from fastapi.middleware.cors import CORSMiddleware  # 处理跨域
import numpy as np
import jieba
from rank_bm25 import BM25Okapi
import re

load_dotenv()                 # 加载 .env 文件（里面要有 ZHIPU_API_KEY）
app = FastAPI()               # 创建 FastAPI 应用实例
API_KEY = os.getenv("ZHIPU_API_KEY")  # 从环境变量获取智谱 API 密钥
URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# ========== 配置跨域（CORS） ==========
# 允许前端（运行在 localhost:3000）调用本后端，否则浏览器会阻止请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],   # 开发环境允许 Next.js 地址
    allow_methods=["*"],                       # 允许所有 HTTP 方法（GET,POST...）
    allow_headers=["*"],                       # 允许所有请求头
)

# ========== 初始化 ChromaDB ==========
# ChromaDB 是一个轻量级向量数据库，用于存储文档的向量表示
# PersistentClient 表示数据持久化到磁盘上的 ./chroma_db 文件夹
client = chromadb.PersistentClient(path="./chroma_db")
# 获取或创建名为 "docs" 的集合（Collection），类似 SQL 中的表
collection = client.get_or_create_collection(name="docs")

# 加载原始文档片段列表
with open("chunks.json", "r", encoding="utf-8") as f:
    CHUNKS = json.load(f)

# 对每个片段进行中文分词（BM25需要）
tokenized_chunks = [list(jieba.cut(chunk)) for chunk in CHUNKS]
bm25 = BM25Okapi(tokenized_chunks)

# ========== 智谱 Embedding 接口地址 ==========
# embedding 模型的作用：将文本转换成一串数字（向量），用于语义相似度计算
EMBED_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

def get_embedding(text: str):
    """调用智谱的 embedding-2 模型，将文本转为 768 维向量"""
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {"model": "embedding-2", "input": text}
    resp = requests.post(EMBED_URL, headers=headers, json=data)
    resp.raise_for_status()                     # 如果请求失败，抛出异常
    return resp.json()["data"][0]["embedding"]  # 返回向量列表

# ========== 定义 /rag 接口的请求体结构 ==========
class RAGRequest(BaseModel):
    question: str   # 用户问题

@app.post("/rag")
def rag_query(req: RAGRequest):
    question = req.question
    try:
        # 1. 获取问题的向量
        q_emb = get_embedding(question)
        
        # 2. 向量检索：取所有片段（为了混合重排，先全部取出）
        all_results = collection.query(query_embeddings=[q_emb], n_results=len(CHUNKS))
        vector_docs = all_results['documents'][0]      # 片段列表
        distances = all_results['distances'][0]         # 距离值（越小越相似）
        
        # 距离转相似度得分（距离越小得分越高）
        vector_scores = 1 / (1 + np.array(distances))
        
        # 3. BM25 检索
        query_tokens = list(jieba.cut(question))
        bm25_scores = np.array(bm25.get_scores(query_tokens))
        
        # 4. 归一化（使两种得分在相同尺度）
        def normalize(arr):
            arr_min, arr_max = arr.min(), arr.max()
            if arr_max == arr_min:
                return np.ones_like(arr)
            return (arr - arr_min) / (arr_max - arr_min)
        
        vec_norm = normalize(vector_scores)
        bm25_norm = normalize(bm25_scores)
        
        # 5. 加权融合（α=0.6 向量权重）
        alpha = 0.6
        combined = alpha * vec_norm + (1 - alpha) * bm25_norm
        
        # 6. 取 top-2 索引
        top_indices = np.argsort(combined)[-2:][::-1]
        contexts = [CHUNKS[i] for i in top_indices]
        
        if not contexts:
            return {"answer": "知识库中暂无相关信息。", "sources": []}
        
        # 7. 构造 prompt 并调用大模型（与你原来相同）
        prompt = f"基于以下信息回答用户问题：\n\n" + "\n\n".join(contexts) + f"\n\n问题：{question}\n回答："
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "glm-4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }
        resp = requests.post(URL,headers=headers, json=payload)
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"]
        
        print("返回的 contexts:", contexts)
        return {"answer": answer, "sources": contexts}
    
    except Exception as e:
        return {"error": str(e)}

# ========== 工具函数（用于 /function 接口） ==========
def get_current_time():
    """返回当前日期时间字符串"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_weather(city: str):
    """模拟获取天气（实际应调用真实天气 API）"""
    return f"{city}当前天气：晴朗，25℃"

# ========== 将 RAG 封装为一个工具函数（供 Agent 调用） ==========
def query_knowledge_base(question: str):
    """
    直接调用本文件中的 rag_query 函数，避免循环导入。
    注意：rag_query 需要接收一个 RAGRequest 对象，返回字典。
    """
    # 构造请求对象
    req = RAGRequest(question=question)
    # 调用 rag_query 获取结果
    result = rag_query(req)
    # 提取 answer 字段，如果没有则返回默认消息
    return result.get("answer", "知识库中未找到相关信息。")

@app.post("/function")
def function_call(req: dict):
    """
    带函数调用（Function Calling）的接口：
    1. 定义 tools 列表，告诉模型它可以调用哪些函数
    2. 将用户消息和 tools 一起发给智谱模型
    3. 如果模型返回 tool_calls，则执行对应的本地函数（获取时间/天气）
    4. 将函数执行结果再次发给模型，让模型生成自然语言回复
    5. 返回最终回复以及使用了哪个工具、结果是什么
    """
    user_msg = req.get("message")
    if not user_msg:
        return {"error": "缺少 message 字段"}
    
    # 定义可供模型调用的工具（函数）
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "获取当前日期和时间",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取某个城市的天气",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名，如北京"}
                    },
                    "required": ["city"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_knowledge_base",
                "description": "从知识库中检索信息，回答技术问题",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "用户的问题"}
                    },
                    "required": ["question"]
                }
            }
        }
    ]

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    # 第一次调用：让模型判断是否需要调用工具
    payload = {
        "model": "glm-4-flash",
        "messages": [
            {"role": "system", "content": "你是一个助手，必须使用提供的工具来回答用户问题。当用户问时间、日期时调用 get_current_time；当用户问某个城市的天气时调用 get_weather；当用户问技术概念、知识性问题时，优先调用 query_knowledge_base。"},
            {"role": "user", "content": user_msg}
        ],
        "tools": tools,
        "tool_choice": "auto"   # auto 表示模型自主决定是否调用工具
    }

    try:
        resp = requests.post(URL, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            return {"error": f"智谱API调用失败: {resp.text}"}

        data = resp.json()
        choice = data["choices"][0]
        message = choice["message"]
        
        # 检查模型是否要求调用工具
        if "tool_calls" in message and message["tool_calls"]:
            tool_call = message["tool_calls"][0]
            func_name = tool_call["function"]["name"]
            args = json.loads(tool_call["function"]["arguments"])
            
            # 执行对应的本地函数
           # 执行对应的本地函数
            if func_name == "get_current_time":
                result = get_current_time()          # 复用函数
            elif func_name == "get_weather":
                city = args.get("city", "未知城市")
                result = get_weather(city)   # 已经复用
            elif func_name == "query_knowledge_base":
                result = query_knowledge_base(args.get("question"))     
            else:
                result = "未知工具"
            
            # 第二次调用：把工具执行结果发给模型，让它生成最终的自然语言回复
            # 构造完整的对话历史：用户消息 -> 模型第一次回复（包含 tool_calls）-> 工具执行结果
            messages = [
                {"role": "user", "content": user_msg},
                message,   # 模型的第一次回复（包含 tool_calls）
                {"role": "tool", "tool_call_id": tool_call["id"], "content": result}
            ]
            payload2 = {
                "model": "glm-4-flash",
                "messages": messages,
                "stream": False
            }
            resp2 = requests.post(URL, headers=headers, json=payload2, timeout=30)
            if resp2.status_code != 200:
                return {"error": f"第二轮调用失败: {resp2.text}"}
            
            final_reply = resp2.json()["choices"][0]["message"]["content"]
            # 返回最终回复、使用的工具名称、工具结果（便于前端展示调用过程）
            return {"reply": final_reply, "tool_used": func_name, "tool_result": result}
        else:
            # 模型没有调用工具（可能问题不涉及时间/天气），则直接返回模型回复
            # 为了更鲁棒，可以手动解析关键词（兜底逻辑）
            if "天气" in user_msg:
                # 简单提取城市（实际应更智能）
                city = "北京"
                result = get_weather(city)
                return {"reply": result, "tool_used": "get_weather(forced)", "tool_result": result}
            else:
                return {"reply": message["content"]}
    
    except Exception as e:
        return {"error": f"服务器内部错误: {str(e)}"}
    
# ========== 多步规划接口（Plan-and-Execute） ==========
class PlanRequest(BaseModel):
    message: str

@app.post("/plan")
def plan_execute(req: PlanRequest):
    user_msg = req.message

    # 1. 调用大模型生成任务计划（输出 JSON 步骤数组）
    plan_prompt = f"""你是一个任务规划专家。用户需求：{user_msg}

可用工具：
- get_current_time: 获取当前时间，无需参数。
- get_weather: 获取城市天气，参数 {{"city": "城市名"}}。
- query_knowledge_base: 从知识库检索信息，参数 {{"question": "问题"}}。

【重要规则】
1.只能使用上述三个工具。不要生成任何其他工具，例如“保存备忘录”等。如果用户需求超出能力范围，请直接返回空步骤并在最终答案中说明无法完成。
2. 用户可能在一句话中包含多个独立请求，例如“现在几点？顺便查一下上海天气”。你必须为每一个请求生成一个对应的工具调用步骤。
3. 输出格式必须是严格的 JSON，例如：
   {{"steps": [{{"tool": "get_current_time", "args": {{}}}}, {{"tool": "get_weather", "args": {{"city": "上海"}}}}]}}
4. 不要输出任何额外解释，只输出 JSON 对象。

请严格按照上述规则输出。"""

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload_plan = {
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": plan_prompt}],
        "temperature": 0.1,   # 降低随机性
        "stream": False
    }
    try:
        resp_plan = requests.post(URL, headers=headers, json=payload_plan, timeout=30)
        if resp_plan.status_code != 200:
            return {"error": f"规划失败: {resp_plan.text}"}
        plan_text = resp_plan.json()["choices"][0]["message"]["content"]
        # 提取 JSON（兼容 markdown 包裹）
        import re
        json_match = re.search(r'\{.*\}', plan_text, re.DOTALL)
        if not json_match:
            return {"error": "无法从规划响应中提取JSON"}
        plan = json.loads(json_match.group())
        steps = plan.get("steps", [])
        if not steps:
            return {"error": "规划结果中没有步骤"}

        # ==== 兜底：如果用户问天气但没有规划天气工具 ====
        if "天气" in user_msg and not any(step.get("tool") == "get_weather" for step in steps):
            city_match = re.search(r'([\u4e00-\u9fa5]+?(?:市|省|区|县))', user_msg)
            city = city_match.group(1) if city_match else "北京"
            steps.append({"tool": "get_weather", "args": {"city": city}})
        
        # 可选：如果用户问时间但没有规划时间工具（较少见，也可添加）
        if ("时间" in user_msg or "几点" in user_msg) and not any(step.get("tool") == "get_current_time" for step in steps):
            steps.insert(0, {"tool": "get_current_time", "args": {}})

    except Exception as e:
        return {"error": f"规划解析异常: {str(e)}"}

    # 2. 顺序执行每个步骤
    results = []
    for step in steps:
        tool = step.get("tool")
        args = step.get("args", {})
        try:
            if tool == "get_current_time":
                res = get_current_time()
            elif tool == "get_weather":
                city = args.get("city", "未知城市")
                res = get_weather(city)
            elif tool == "query_knowledge_base":
                question = args.get("question", "")
                res = query_knowledge_base(question)
            else:
                res = f"不支持的工具: {tool}"
        except Exception as e:
            res = f"执行错误: {str(e)}"
        results.append({
            "tool": tool,
            "args": args,
            "result": res
        })

    # 3. 将所有执行结果汇总，让大模型生成最终自然语言回答
    summary_prompt = f"""用户需求：{user_msg}

执行步骤与结果：
{chr(10).join([f"- {r['tool']}({json.dumps(r['args'], ensure_ascii=False)}): {r['result']}" for r in results])}

请根据以上结果，用自然语言、连贯地回应用户。不要重复列出步骤，直接给出最终答案。"""

    payload_summary = {
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": summary_prompt}],
        "stream": False
    }
    resp_summary = requests.post(URL, headers=headers, json=payload_summary, timeout=30)
    if resp_summary.status_code != 200:
        return {"error": f"生成最终回答失败: {resp_summary.text}"}
    final_answer = resp_summary.json()["choices"][0]["message"]["content"]

    return {
        "plan": steps,
        "results": results,
        "final_answer": final_answer
    }
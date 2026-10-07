import requests
import json
import time
import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("ZHIPU_API_KEY")

URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

headers = {
    "Authorization":f"Bearer {API_KEY}",
    "Content-Type":"application/json"
}

arrays =[
     {
        "name": "代码解释器",
        "system": "你是一个代码解释专家。用户会给你一段代码，请用通俗易懂的中文解释这段代码做了什么，逐行说明。",
        "user": "print('Hello World')"
    },
    {
        "name": "SQL生成器",
        "system": "你是一个SQL专家。用户用自然语言描述查询需求，你只输出SQL语句，不要任何额外解释。",
        "user": "查询年龄大于18岁的所有用户的名字和邮箱"
    },
    {
        "name": "简历描述优化",
        "system": "你是资深HR。帮我优化一段项目经历描述，使其更专业、量化、简洁。输出优化后的版本。",
        "user": "做了一个智能AI对话助手，实现SSE流式响应，支持中止生成以及网络异常提示，支持上传pdf,word,excle,txt"
    },
    {
        "name": "产品命名器",
        "system": "你是一个创意营销专家。根据用户输入的产品特点，给出5个中文产品名字，并附上一句话解释每个名字的寓意。",
        "user": "一款帮助程序员快速写文档的AI工具"
    },
    {
        "name": "情绪安抚助手",
        "system": "你是一个善解人意的好朋友。用户会倾诉负面情绪，请用鼓励、共情的方式回复，不要给建议，不要解决问题，只需要表达理解和安慰。",
        "user": "我今天投了30份简历，一个面试都没有，觉得自己好没用。"
    }
]

results =[]

for idx, t in enumerate(arrays,1):
    print(f"\n==== 测试 {idx}.{t['name']} ====")
    data = {
        "model":"glm-4-flash",
        "messages":[ 
        {"role":"system","content":t["system"]},

        {"role":"user","content":t["user"]}
        ],
        "stream":False
    }

    try:
        response = requests.post(URL,headers=headers,json=data,timeout=30)

        if response.status_code == 200:
            result = response.json()
            reply = result["choices"][0]["message"]["content"]
            print("AI回复：",reply)
            results.append({
                "场景": t["name"],
                "用户输入": t["user"],
                "AI回复": reply,
                "状态码": response.status_code,
            })
        else:
            error_msg = f"状态码{response.status_code}:{response.text}"
            print(error_msg)
            results.append({
                "场景": t["name"],
                "用户输入": t["user"],
                "AI回复": error_msg,
                "状态码": "失败",
            })
    except Exception as e:
        print("请求异常：", e)
        print(error_msg)
        results.append({
            "场景": t["name"],
            "用户输入": t["user"],
            "AI输出": f"异常：{str(e)}",
            "状态码": "异常"})

        time.sleep(1)

with open("results.json","w",encoding="utf-8") as f:
        json.dump(results,f,ensure_ascii=False,indent=2)

with open("results.md","w",encoding="utf-8") as f:
    f.write("#Prompts测试结果\n\n")
    for result in results:
        f.write(f"## {result['场景']}\n")
        f.write(f"用户输入：{result['用户输入']}\n")
        f.write(f"AI回复：{result['AI回复']}\n")
        f.write(f"状态码：{result['状态码']}\n")
        f.write("\n\n")
        
print("测试完成，结果已保存到results.json和results.md")
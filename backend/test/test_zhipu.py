import requests
import json

API_KEY = "09fb7ca7fc604a2abba0f2fffd3153e7.yaRAaSl2L3sbWGZW"
URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

headers = {
    "Authorization":f"Bearer {API_KEY}",
    "Content-Type":"application/json"
}

data = {
    "model":"glm-4-flash",
    "messages":[ 
       {"role":"user","content":"请用一句话鼓励正在学习AI的人。"}
    ],
    "stream":False
}

response = requests.post(URL,headers=headers,json=data)

if response.status_code == 200:
    result = response.json()
    reply = result["choices"][0]["message"]["content"]
    print("AI回复：",reply)
else:
    print("状态码：",response.status_code)
    print(response.text)
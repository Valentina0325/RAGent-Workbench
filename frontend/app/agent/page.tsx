'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

interface Step {
  tool: string;
  args: Record<string, any>;
}

interface ResultItem {
  tool: string;
  args: Record<string, any>;
  result: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  plan?: Step[];
  results?: ResultItem[];
}

export default function AgentPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [mounted, setMounted] = useState(false);

  // 加载 localStorage 中的数据
  useEffect(() => {
    const saved = localStorage.getItem('agent_messages');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setMessages(parsed);
      } catch (e) {}
    }
    setMounted(true);
  }, []);

  // 保存到 localStorage
  useEffect(() => {
    if (mounted) {
      localStorage.setItem('agent_messages', JSON.stringify(messages));
    }
  }, [messages, mounted]);

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
    };
    setMessages(prev => [...prev, userMsg]);
    const currentInput = input;
    setInput('');
    setLoading(true);
    setError('');

    try {
      const res = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: currentInput }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }

      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.final_answer || '已完成',
        plan: data.plan,
        results: data.results,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: any) {
      setError(err.message || '请求失败');
    } finally {
      setLoading(false);
    }
  };

  const deleteMessage = (id: string) => {
    setMessages(prev => prev.filter(msg => msg.id !== id));
  };

  const clearAllMessages = () => {
    setMessages([]);
  };

  return (
    <div className="dashboard-container">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <Link href="/" className="text-blue-600 hover:underline">
            ← 返回仪表盘
          </Link>
        </div>

        <div className="flex justify-between items-center mb-4">
          <h1 className="title-gradient text-center">🤖 智能助手 (Agent) - 多步规划</h1>
          {mounted && messages.length > 0 && (
            <button
              onClick={clearAllMessages}
              className="px-3 py-1 bg-red-500 text-white rounded-lg text-sm hover:bg-red-600 transition"
            >
              清空对话
            </button>
          )}
        </div>
        <p className="subtitle text-center mb-8">
          我可以自动分解复杂任务，依次调用工具（时间/天气/知识库），并汇总结果。
        </p>

        <div className="white-card mb-6 h-[600px] flex flex-col">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {mounted && messages.length === 0 && (
              <div className="text-center text-gray-400 mt-20">
                💬 试试问我：<br />
                “查一下北京天气，然后告诉我知识库里有没有关于雾霾的信息”<br />
                “现在几点了？顺便查一下上海天气”<br />
                “什么是混合检索？”
              </div>
            )}
            {messages.map(msg => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} group relative`}
              >
                <div
                  className={`max-w-[85%] rounded-lg p-3 ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {msg.role === 'assistant' && msg.plan && msg.plan.length > 0 && (
                    <div className="text-xs text-gray-500 mb-2 pb-2 border-b border-gray-200 space-y-1">
                      <div className="font-medium">📋 规划步骤：</div>
                      {msg.plan.map((step, idx) => (
                        <div key={idx}>
                          {idx + 1}. {step.tool} {JSON.stringify(step.args)}
                        </div>
                      ))}
                      {msg.results && (
                        <div className="mt-2 pt-1">
                          <div className="font-medium">🔧 执行结果：</div>
                          {msg.results.map((res, idx) => (
                            <div key={idx}>
                              {res.tool} → {res.result.substring(0, 100)}...
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
                <button
                  onClick={() => deleteMessage(msg.id)}
                  className="ml-2 opacity-0 group-hover:opacity-100 transition-opacity text-red-500 hover:text-red-700"
                  aria-label="删除"
                >
                  🗑️
                </button>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-lg p-3 text-gray-500">
                  🤔 思考中...
                </div>
              </div>
            )}
          </div>

          <form onSubmit={sendMessage} className="border-t p-4 flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入复杂任务，例如：查北京天气并告诉我雾霾防护知识"
              className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="btn-primary"
            >
              发送
            </button>
          </form>
        </div>

        {error && (
          <div className="error-alert">
            ⚠️ {error}
          </div>
        )}
      </div>
    </div>
  );
}
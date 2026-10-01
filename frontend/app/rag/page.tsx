'use client';

import { useState, useEffect } from 'react';
import { useLocalStorage } from '@/app/hooks/useLocalStorage';

interface HistoryItem {
  question: string;
  answer: string;
  sources: string[];
  timestamp: number;
}

export default function RAGPage() {
  const [history, setHistory] = useLocalStorage<HistoryItem[]>('rag_history', []);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError('');
    setAnswer('');
    setSources([]);

    try {
      const res = await fetch('/api/rag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || '请求失败');
      }

      setAnswer(data.answer);
      setSources(data.sources || []);

      const newItem: HistoryItem = {
        question,
        answer: data.answer,
        sources: data.sources || [],
        timestamp: Date.now(),
      };
      setHistory(prev => [newItem, ...prev].slice(0, 20));
      setQuestion('');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const viewHistory = (item: HistoryItem) => {
    setAnswer(item.answer);
    setSources(item.sources);
  };

  const deleteHistoryItem = (index: number) => {
    setHistory(prev => prev.filter((_, i) => i !== index));
    // 如果删除的是当前正在查看的记录，则清空显示区域
    if (answer === history[index]?.answer && sources === history[index]?.sources) {
      setAnswer('');
      setSources([]);
    }
  };

  const clearAllHistory = () => {
    setHistory([]);
    setAnswer('');
    setSources([]);
  };

  return (
    <div className="dashboard-container">
      <div className="max-w-7xl mx-auto">
        <h1 className="title-gradient text-center mb-4">📚 知识库问答 (RAG)</h1>
        <p className="subtitle text-center mb-8">
          基于预置文档，智能回答你的问题，并显示引用来源
        </p>

        <div className="card">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="question" className="block text-sm font-medium text-gray-700 mb-1">
                你的问题
              </label>
              <textarea
                id="question"
                rows={3}
                className="w-full border border-gray-300 rounded-lg p-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="例如：什么是RAG？"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={loading}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full justify-center"
            >
              {loading ? '🤔 思考中...' : '🚀 提问'}
            </button>
          </form>
        </div>

        {mounted && history.length > 0 && (
          <div className="card mt-6">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-medium text-gray-800">📜 最近提问</h3>
              <button
                onClick={clearAllHistory}
                className="text-sm text-red-600 hover:text-red-800"
              >
                清空全部
              </button>
            </div>
            <ul className="space-y-2">
              {history.map((item, idx) => (
                <li key={idx} className="border-b pb-2 flex justify-between items-start">
                  <div
                    className="flex-1 cursor-pointer hover:bg-gray-50 p-1 rounded"
                    onClick={() => viewHistory(item)}
                  >
                    <div className="text-blue-600 hover:underline">{item.question}</div>
                    <div className="text-xs text-gray-500 truncate">
                      回答：{item.answer.substring(0, 60)}...
                    </div>
                  </div>
                  <button
                    onClick={() => deleteHistoryItem(idx)}
                    className="ml-2 text-red-500 hover:text-red-700 text-sm"
                    aria-label="删除"
                  >
                    🗑️
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {error && (
          <div className="error-alert mt-6">
            ⚠️ {error}
          </div>
        )}

        {answer && (
          <div className="ai-report-card mt-6">
            <h3 className="text-xl font-semibold text-indigo-800 flex items-center gap-2 mb-3">
              🤖 回答
            </h3>
            <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{answer}</p>

            {sources.length > 0 && (
              <div className="mt-4 pt-4 border-t border-indigo-200">
                <h4 className="font-medium text-gray-700 mb-2">📖 引用来源：</h4>
                <ul className="list-disc list-inside space-y-1 text-sm text-gray-600">
                  {sources.map((src, idx) => (
                    <li key={idx}>{src}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
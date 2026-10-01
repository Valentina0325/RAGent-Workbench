/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Papa from 'papaparse';
import WorkbenchSidebar from '@/components/WorkbenchSidebar';
import ChatMessage, { type Message } from '@/components/ChatMessage';
import DataPanel from '@/components/DataPanel';

// ---- 类型 ----
interface KBInfo {
  name: string;
  chunk_count: number;
}

interface CSVFile {
  id: string;
  name: string;
  headers: string[];
  rows: any[];
}

interface DocChunk {
  index: number;
  text: string;
}

interface DocPreview {
  kbName: string;
  source: string;
  content: string;
  chunkList: DocChunk[];
  highlightIndex: number | null;
}

interface Session {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
}

// ---- 会话工具函数 ----
function createEmptySession(): Session {
  const now = Date.now();
  return {
    id: `s-${now}-${Math.random().toString(36).slice(2, 8)}`,
    title: '新对话',
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

function deriveSessionTitle(msgs: Message[]): string {
  const firstUser = msgs.find(m => m.role === 'user' && m.content.trim());
  const t = (firstUser?.content || '').trim().slice(0, 18);
  return t || '新对话';
}

function persistSessions(sessions: Session[]) {
  try {
    localStorage.setItem('workbench_sessions', JSON.stringify(sessions));
  } catch {}
}

// ---- 工具函数 ----
function buildChartOption(rows: any[], xKey: string, yKey: string, chartType: string): any {
  if (!rows.length || !xKey || !yKey) return null;
  const xAxisData: string[] = [];
  const seriesData: number[] = [];
  for (const row of rows) {
    const xVal = String(row[xKey] ?? '');
    const yVal = parseFloat(row[yKey]);
    if (isNaN(yVal)) continue;
    xAxisData.push(xVal);
    seriesData.push(yVal);
  }
  if (!seriesData.length) return null;

  if (chartType === 'pie') {
    return {
      title: { text: `${yKey} 分布`, left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'item' },
      xAxis: { show: false },
      yAxis: { show: false },
      series: [{ name: yKey, type: 'pie', radius: '55%', data: xAxisData.map((n, i) => ({ name: n, value: seriesData[i] })) }],
    };
  }
  if (chartType === 'scatter') {
    return {
      title: { text: `${yKey} 散点图`, left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'item' },
      xAxis: { type: 'category', name: xKey },
      yAxis: { type: 'value', name: yKey },
      series: [{ type: 'scatter', data: seriesData.map((y, i) => [i, y]), symbolSize: 8 }],
    };
  }
  return {
    title: { text: `${yKey} 分布`, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: xAxisData, name: xKey, axisLabel: { interval: 0, rotate: xAxisData.length > 10 ? 30 : 0 } },
    yAxis: { type: 'value', name: yKey },
    series: [{
      name: yKey,
      type: chartType === 'bar' ? 'bar' : 'line',
      data: seriesData,
      itemStyle: { borderRadius: [4, 4, 0, 0], color: '#60a5fa' },
      lineStyle: { color: '#60a5fa', width: 2 },
      smooth: true,
    }],
    grid: { bottom: 60 },
  };
}

function getCSVContext(file: CSVFile | null): any {
  if (!file) return null;
  const numericStats: Record<string, any> = {};
  for (const h of file.headers) {
    const vals = file.rows.map(r => parseFloat(r[h])).filter(v => !isNaN(v));
    if (vals.length > 0) {
      numericStats[h] = {
        count: vals.length,
        sum: Number(vals.reduce((a, b) => a + b, 0).toFixed(2)),
        avg: Number((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2)),
        max: Math.max(...vals),
        min: Math.min(...vals),
      };
    }
  }
  return {
    fileName: file.name,
    headers: file.headers,
    sampleRows: file.rows.slice(0, 5),
    // 传真实数据行给后端做统计（上限 2000 行，避免大文件请求体过大）
    rows: file.rows.slice(0, 2000),
    stats: numericStats,
    rowCount: file.rows.length,
  };
}

// ---- 主组件 ----
export default function WorkbenchPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [kbs, setKBs] = useState<KBInfo[]>([]);
  const [activeKB, setActiveKB] = useState('');
  const [csvFiles, setCSVFiles] = useState<CSVFile[]>([]);
  const [activeCSVId, setActiveCSVId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [dataPanelCollapsed, setDataPanelCollapsed] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [docPreview, setDocPreview] = useState<DocPreview | null>(null);
  const [docPreviewLoading, setDocPreviewLoading] = useState(false);
  const [docUploadTrigger, setDocUploadTrigger] = useState(0);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeCSV = csvFiles.find(f => f.id === activeCSVId) || null;

  // ---- 加载知识库列表 ----
  const loadKBs = useCallback(async () => {
    try {
      const res = await fetch('/api/kb/list');
      const data = await res.json();
      if (data.kbs) {
        setKBs(data.kbs);
      }
    } catch {
      // 后端未启动时静默失败
    }
  }, []);

  // ---- 自动选择第一个 KB ----
  useEffect(() => {
    if (kbs.length > 0 && !activeKB) {
      setActiveKB(kbs[0].name);
    }
  }, [kbs, activeKB]);

  // ---- 初始化：恢复会话列表（含旧版单会话数据迁移）----
  useEffect(() => {
    let loaded: Session[] = [];
    try {
      const raw = localStorage.getItem('workbench_sessions');
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) loaded = parsed.filter(s => s && s.id);
      }
    } catch {}

    // 迁移旧版 workbench_messages（单会话历史）
    if (loaded.length === 0) {
      try {
        const old = localStorage.getItem('workbench_messages');
        if (old) {
          const msgs = JSON.parse(old);
          if (Array.isArray(msgs) && msgs.length > 0) {
            const now = Date.now();
            loaded = [{
              id: `s-${now}-migrated`,
              title: deriveSessionTitle(msgs),
              createdAt: now,
              updatedAt: now,
              messages: msgs,
            }];
          }
        }
      } catch {}
    }

    if (loaded.length === 0) {
      loaded = [createEmptySession()];
    }
    // 按最近更新排序
    loaded.sort((a, b) => b.updatedAt - a.updatedAt);
    setSessions(loaded);
    const active = loaded[0];
    setActiveSessionId(active.id);
    setMessages(active.messages);

    // 恢复 CSV 文件
    const savedCSV = localStorage.getItem('workbench_csv_files');
    if (savedCSV) {
      try {
        const parsed = JSON.parse(savedCSV) as CSVFile[];
        setCSVFiles(parsed);
        if (parsed.length > 0 && !activeCSVId) {
          setActiveCSVId(parsed[0].id);
        }
      } catch {}
    }
    loadKBs();
  }, [loadKBs]);

  // ---- 持久化：当前会话消息写入会话列表 ----
  useEffect(() => {
    if (!activeSessionId) return;
    setSessions(prev => {
      const next = prev.map(s => {
        if (s.id !== activeSessionId) return s;
        const title = s.title === '新对话' && messages.some(m => m.role === 'user')
          ? deriveSessionTitle(messages)
          : s.title;
        return { ...s, title, messages: messages.slice(-100), updatedAt: Date.now() };
      });
      persistSessions(next);
      return next;
    });
  }, [messages, activeSessionId]);

  // ---- 会话切换（保留滚动位置无需处理，直接换消息） ----
  const handleNewSession = () => {
    // 当前会话为空时不重复新建
    if (messages.length === 0) return;
    const s = createEmptySession();
    setSessions(prev => {
      const next = [s, ...prev];
      persistSessions(next);
      return next;
    });
    setActiveSessionId(s.id);
    setMessages([]);
  };

  const handleSelectSession = (id: string) => {
    if (id === activeSessionId || loading) return;
    const s = sessions.find(x => x.id === id);
    if (s) {
      setActiveSessionId(id);
      setMessages(s.messages || []);
    }
  };

  const handleDeleteSession = (id: string) => {
    const next = sessions.filter(s => s.id !== id);
    const final = next.length > 0 ? next : [createEmptySession()];
    setSessions(final);
    persistSessions(final);
    if (id === activeSessionId) {
      setActiveSessionId(final[0].id);
      setMessages(final[0].messages || []);
    }
  };

  // ---- 持久化 CSV 文件列表 ----
  useEffect(() => {
    try {
      if (csvFiles.length > 0) {
        localStorage.setItem('workbench_csv_files', JSON.stringify(csvFiles));
      } else {
        localStorage.removeItem('workbench_csv_files');
      }
    } catch {}
  }, [csvFiles]);

  // ---- 自动滚动 ----
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ---- 添加消息 ----
  const addMessage = (msg: Partial<Message> & { role: 'user' | 'assistant' }) => {
    const fullMsg: Message = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      content: '',
      type: 'text',
      timestamp: Date.now(),
      ...msg,
    } as Message;
    setMessages(prev => [...prev, fullMsg]);
    return fullMsg.id;
  };

  // ---- 更新消息 ----
  const updateMessage = (id: string, updates: Partial<Message>) => {
    setMessages(prev => prev.map(m => (m.id === id ? { ...m, ...updates } : m)));
  };

  // ---- 构建多轮对话历史（最近 8 条有效消息）----
  const buildHistory = (): { role: string; content: string }[] => {
    return messages
      .filter(m =>
        (m.role === 'user' || m.role === 'assistant') &&
        m.content && m.content.trim() &&
        m.type !== 'error' && m.type !== 'csv-upload' && m.type !== 'doc-upload'
      )
      .slice(-8)
      .map(m => ({ role: m.role, content: m.content.slice(0, 400) }));
  };

  // ---- 发送消息（核心 SSE 流程）----
  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userText = input;
    setInput('');
    setLoading(true);
    const historyForRequest = buildHistory();

    addMessage({ role: 'user', content: userText });

    const assistantId = addMessage({ role: 'assistant', content: '', type: 'text' });
    let firstTokenReceived = false;

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userText,
          kb_name: activeKB,
          csv_context: getCSVContext(activeCSV),
          history: historyForRequest,
        }),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const event of events) {
          const line = event.trim();
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            switch (data.type) {
              case 'intent':
                updateMessage(assistantId, { intent: data.intent });
                break;

              case 'status':
                updateMessage(assistantId, { content: data.content });
                firstTokenReceived = false;
                break;

              case 'sources':
                // Agent 消息保留 agent 类型（同时显示规划步骤和引用来源）
                setMessages(prev => prev.map(m =>
                  m.id === assistantId
                    ? {
                        ...m,
                        sources: data.sources,
                        kbName: data.kb || activeKB,
                        type: m.type === 'agent' ? 'agent' : 'rag',
                      }
                    : m
                ));
                break;

              case 'plan':
                updateMessage(assistantId, {
                  type: 'agent',
                  plan: data.steps,
                  results: [],
                });
                break;

              case 'step_result':
                setMessages(prev => prev.map(m => {
                  if (m.id !== assistantId) return m;
                  const results = m.results || [];
                  return {
                    ...m,
                    type: 'agent',
                    results: [...results, data.result],
                  };
                }));
                break;

              case 'chart':
                if (data.config && activeCSV) {
                  const opt = buildChartOption(
                    activeCSV.rows,
                    data.config.xKey,
                    data.config.yKey,
                    data.config.chartType,
                  );
                  if (opt) {
                    setMessages(prev => prev.map(m =>
                      m.id === assistantId
                        ? {
                            ...m,
                            chartConfig: data.config,
                            chartOption: opt,
                            type: m.type === 'agent' ? 'agent' : 'chart',
                          }
                        : m
                    ));
                    setDataPanelCollapsed(false);
                  }
                }
                break;

              case 'token':
                if (!firstTokenReceived) {
                  firstTokenReceived = true;
                  updateMessage(assistantId, { content: data.content });
                } else {
                  setMessages(prev => prev.map(m =>
                    m.id === assistantId
                      ? { ...m, content: m.content + data.content }
                      : m
                  ));
                }
                break;

              case 'error':
                updateMessage(assistantId, { type: 'error', content: data.content });
                break;

              case 'done':
                break;
            }
          } catch {}
        }
      }
    } catch (err: any) {
      updateMessage(assistantId, {
        type: 'error',
        content: `连接失败：${err.message}。请确认后端服务已启动。`,
      });
    } finally {
      setLoading(false);
    }
  };

  // ---- 文件上传 ----
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    Array.from(files).forEach(file => {
      const ext = file.name.toLowerCase().split('.').pop();
      if (ext === 'csv') handleCSVUpload(file);
      else if (['pdf', 'txt', 'md'].includes(ext || '')) handleDocUpload(file);
      else addMessage({ role: 'assistant', type: 'error', content: `不支持的文件格式：${file.name}` });
    });
    e.target.value = '';
  };

  const handleCSVUpload = (file: File) => {
    if (file.size > 10 * 1024 * 1024) {
      addMessage({ role: 'assistant', type: 'error', content: `文件 ${file.name} 超过 10MB 限制` });
      return;
    }
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.data && results.data.length) {
          const firstRow = results.data[0] as Record<string, any>;
          const headers = Object.keys(firstRow);
          const newFile: CSVFile = {
            id: `${Date.now()}-${file.name}`,
            name: file.name,
            headers,
            rows: results.data as any[],
          };
          setCSVFiles(prev => [...prev, newFile]);
          setActiveCSVId(newFile.id);
          setDataPanelCollapsed(false);
          addMessage({
            role: 'assistant',
            type: 'csv-upload',
            fileName: file.name,
            rowCount: results.data.length,
            content: `CSV 文件「${file.name}」已加载，共 ${results.data.length} 行数据。列名：${headers.join('、')}。你可以在对话中告诉我你想怎么分析，或直接说"画一个柱状图"。`,
          });
        } else {
          addMessage({ role: 'assistant', type: 'error', content: `文件 ${file.name} 无有效数据` });
        }
      },
      error: (err) => {
        addMessage({ role: 'assistant', type: 'error', content: `解析 ${file.name} 失败：${err.message}` });
      },
    });
  };

  const handleDocUpload = async (file: File) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    const kbName = activeKB || 'default';
    formData.append('kb_name', kbName);

    const statusId = addMessage({
      role: 'assistant',
      content: `📥 正在上传并处理「${file.name}」...`,
    });

    try {
      const res = await fetch('/api/upload-doc', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.success) {
        updateMessage(statusId, {
          type: 'doc-upload',
          fileName: data.file_name || file.name,
          chunkCount: data.chunks,
          kbName: data.kb_name,
          content: `文档「${data.file_name || file.name}」已成功入库到知识库「${data.kb_name}」，切分为 ${data.chunks} 个片段并完成向量化。现在可以基于该知识库提问了。`,
        });
        loadKBs();
        setDocUploadTrigger(prev => prev + 1);
      } else {
        updateMessage(statusId, { type: 'error', content: data.error || '上传失败' });
      }
    } catch (err: any) {
      updateMessage(statusId, {
        type: 'error',
        content: `上传失败：${err.message}。请确认后端服务已启动。`,
      });
    } finally {
      setUploading(false);
    }
  };

  // ---- KB 管理 ----
  const handleCreateKB = async (name: string) => {
    try {
      await fetch('/api/kb/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      await loadKBs();
      setActiveKB(name);
      setDocUploadTrigger(prev => prev + 1);
    } catch {
      addMessage({ role: 'assistant', type: 'error', content: '创建知识库失败，请确认后端服务已启动' });
    }
  };

  const handleDeleteKB = async (name: string) => {
    try {
      const res = await fetch(`/api/kb/${encodeURIComponent(name)}`, { method: 'DELETE' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.detail) {
        alert(data.detail || `删除知识库「${name}」失败`);
        return;
      }
      await loadKBs();
      if (activeKB === name) {
        setActiveKB('');
      }
      setDocUploadTrigger(prev => prev + 1);
    } catch (err: any) {
      alert(`删除知识库失败：${err.message || '网络错误'}`);
    }
  };

  // ---- 键盘事件 ----
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ---- 清空当前会话 ----
  const handleClearMessages = () => {
    if (confirm('确认清空当前对话？（其他会话不受影响）')) {
      setMessages([]);
    }
  };

  // ---- 文档预览 ----
  const handlePreviewDoc = async (
    kbName: string,
    source: string,
  ) => {
    setDocPreviewLoading(true);
    try {
      const res = await fetch(`/api/kb/${encodeURIComponent(kbName)}/doc-content?source=${encodeURIComponent(source)}`);
      const data = await res.json();
      if (data.content !== undefined) {
        const items: DocChunk[] = Array.isArray(data.chunkList) ? data.chunkList : [];
        setDocPreview({
          kbName,
          source,
          content: data.content || '',
          chunkList: items,
          highlightIndex: null,
        });
      } else {
        addMessage({ role: 'assistant', type: 'error', content: `获取文档「${source}」内容失败` });
      }
    } catch (err: any) {
      addMessage({ role: 'assistant', type: 'error', content: `预览文档失败：${err.message}` });
    } finally {
      setDocPreviewLoading(false);
    }
  };

  // ---- 高亮片段自动滚动居中 ----
  useEffect(() => {
    if (docPreview && docPreview.highlightIndex != null && docPreview.highlightIndex >= 0) {
      const el = document.getElementById(`doc-chunk-${docPreview.highlightIndex}`);
      if (el) {
        setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'center' }), 150);
      }
    }
  }, [docPreview]);

  const handleCloseDocPreview = () => {
    setDocPreview(null);
  };

  // ---- 渲染 ----
  return (
    <div className="workbench-root">
      {/* 侧边栏 */}
      <WorkbenchSidebar
        kbs={kbs}
        activeKB={activeKB}
        onSelectKB={setActiveKB}
        onCreateKB={handleCreateKB}
        onDeleteKB={handleDeleteKB}
        onPreviewDoc={(kbName, source) => handlePreviewDoc(kbName, source)}
        refreshTrigger={docUploadTrigger}
        sessions={sessions.map(s => ({
          id: s.id,
          title: s.title,
          createdAt: s.createdAt,
          updatedAt: s.updatedAt,
        }))}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
        csvFiles={csvFiles}
        activeCSVId={activeCSVId}
        onSelectCSV={(id) => { setActiveCSVId(id); setDataPanelCollapsed(false); }}
        onRemoveCSV={(id) => {
          setCSVFiles(prev => prev.filter(f => f.id !== id));
          if (activeCSVId === id) setActiveCSVId(null);
        }}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      {/* 主聊天区域 */}
      <div className="wb-chat-area">
        {/* 头部 */}
        <div className="wb-chat-header">
          <div className="flex items-center gap-3">
            {sidebarCollapsed && (
              <button onClick={() => setSidebarCollapsed(false)} className="text-gray-400 hover:text-gray-600 text-sm">
                ☰
              </button>
            )}
            <h1>🧠 RAGent 智能工作台</h1>
            {activeKB && <span className="header-badge">📚 {activeKB}</span>}
            {activeCSV && <span className="header-badge">📊 {activeCSV.name}</span>}
            {uploading && <span className="header-badge text-blue-600">⏳ 上传中...</span>}
          </div>
          <div className="flex items-center gap-2">
            {activeCSV && (
              <button
                onClick={() => setDataPanelCollapsed(!dataPanelCollapsed)}
                className="text-xs px-2 py-1 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded transition"
              >
                {dataPanelCollapsed ? '📊 显示数据面板' : '📊 隐藏数据面板'}
              </button>
            )}
            {messages.length > 0 && (
              <button
                onClick={handleClearMessages}
                className="text-xs px-2 py-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition"
              >
                🗑️ 清空对话
              </button>
            )}
          </div>
        </div>

        {/* 文档预览 */}
        {docPreview && (
          <div className="doc-preview-bar">
            <div className="doc-preview-header">
              <div className="flex items-center gap-2">
                <span className="text-sm">📄</span>
                <span className="text-sm font-medium text-gray-700">{docPreview.source}</span>
                <span className="text-xs text-gray-400">（知识库：{docPreview.kbName}）</span>
              </div>
              <button
                onClick={handleCloseDocPreview}
                className="text-gray-400 hover:text-gray-600 text-sm px-2"
                title="关闭预览"
              >
                ✕
              </button>
            </div>
            <div className="doc-preview-body">
              {docPreview.chunkList && docPreview.chunkList.length > 0 ? (
                docPreview.chunkList.map((ch) => (
                  <div
                    key={ch.index}
                    id={`doc-chunk-${ch.index}`}
                    className={`doc-chunk ${docPreview.highlightIndex === ch.index ? 'highlighted' : ''}`}
                  >
                    {ch.text}
                  </div>
                ))
              ) : docPreview.content ? (
                <pre className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed">{docPreview.content}</pre>
              ) : (
                <div className="text-xs text-gray-400">该文档暂无内容</div>
              )}
            </div>
          </div>
        )}
        {docPreviewLoading && !docPreview && (
          <div className="doc-preview-bar">
            <div className="flex items-center gap-2 text-gray-400 text-xs py-2 px-4">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
              正在加载文档内容...
            </div>
          </div>
        )}

        {/* 消息列表 */}
        <div className="wb-messages">
          {messages.length === 0 && !loading ? (
            <div className="welcome-card">
              <div className="welcome-icon">🧠</div>
              <div className="welcome-title">RAGent 智能工作台</div>
              <div className="welcome-desc">
                数据可视化 · 知识库问答 · 任务规划，三合一智能工作台
              </div>
              <div className="welcome-suggestions">
                <div className="welcome-suggestion" onClick={() => { setInput('帮我画一个柱状图看看数据分布'); }}>
                  📊 <span>上传 CSV 后说「画一个柱状图看看数据分布」</span>
                </div>
                <div className="welcome-suggestion" onClick={() => { setActiveKB(kbs[0]?.name || ''); setInput('根据知识库内容，什么是混合检索？'); }}>
                  📚 <span>上传 PDF/TXT 构建知识库后提问</span>
                </div>
                <div className="welcome-suggestion" onClick={() => { setInput('现在几点了？顺便查一下北京明天的天气'); }}>
                  🤖 <span>「现在几点了？顺便查一下北京明天的天气」</span>
                </div>
                <div className="welcome-suggestion" onClick={() => { setInput('番茄可以生吃吗？'); }}>
                  💬 <span>日常问题也能问：「番茄可以生吃吗？」</span>
                </div>
              </div>
            </div>
          ) : (
            messages.map(msg => <ChatMessage key={msg.id} message={msg} />)
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="wb-input-area">
          <div className="wb-input-row">
            <button
              className="wb-upload-btn"
              onClick={() => fileInputRef.current?.click()}
              title="上传 CSV / PDF / TXT 文件"
              disabled={uploading}
            >
              📎
            </button>
            <input
              type="file"
              ref={fileInputRef}
              accept=".csv,.pdf,.txt,.md"
              multiple
              onChange={handleFileUpload}
              style={{ display: 'none' }}
            />
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={uploading ? '正在上传文件...' : '输入消息，或点 📎 上传 CSV/PDF/TXT 文件...'}
              disabled={loading || uploading}
            />
            <button
              className="wb-send-btn"
              onClick={handleSend}
              disabled={loading || !input.trim() || uploading}
            >
              {loading ? '⏳' : '发送'}
            </button>
          </div>
        </div>
      </div>

      {/* 数据面板 */}
      <DataPanel
        file={activeCSV}
        collapsed={dataPanelCollapsed}
        onToggle={() => setDataPanelCollapsed(!dataPanelCollapsed)}
      />
    </div>
  );
}

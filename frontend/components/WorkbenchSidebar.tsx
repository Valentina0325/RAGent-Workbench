'use client';

import { useState, useCallback, useEffect } from 'react';

interface KBInfo {
  name: string;
  chunk_count: number;
}

interface KBDoc {
  source: string;
  count: number;
}

interface CSVFile {
  id: string;
  name: string;
  headers: string[];
  rows: any[];
}

export interface SessionInfo {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount?: number;
}

interface WorkbenchSidebarProps {
  kbs: KBInfo[];
  activeKB: string;
  onSelectKB: (name: string) => void;
  onCreateKB: (name: string) => void;
  onDeleteKB: (name: string) => void;
  onPreviewDoc: (kbName: string, source: string) => void;
  csvFiles: CSVFile[];
  activeCSVId: string | null;
  onSelectCSV: (id: string) => void;
  onRemoveCSV: (id: string) => void;
  collapsed: boolean;
  onToggle: () => void;
  refreshTrigger?: number;
  sessions: SessionInfo[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
}

const KB_ICONS: Record<string, string> = {
  '课程': '📚',
  '项目': '📁',
  '生活': '🏠',
  'docs': '📖',
};

function getKBIcon(name: string): string {
  for (const key in KB_ICONS) {
    if (name.includes(key)) return KB_ICONS[key];
  }
  return '🗂️';
}

function formatSessionTime(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const pad = (n: number) => String(n).padStart(2, '0');
  if (sameDay) return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function WorkbenchSidebar({
  kbs, activeKB, onSelectKB, onCreateKB, onDeleteKB, onPreviewDoc,
  csvFiles, activeCSVId, onSelectCSV, onRemoveCSV,
  collapsed, onToggle, refreshTrigger = 0,
  sessions, activeSessionId, onSelectSession, onNewSession, onDeleteSession,
}: WorkbenchSidebarProps) {
  const [showNewKB, setShowNewKB] = useState(false);
  const [newKBName, setNewKBName] = useState('');
  const [expandedKBs, setExpandedKBs] = useState<Set<string>>(new Set());
  const [kbDocs, setKBDocs] = useState<Record<string, KBDoc[]>>({});
  const [loadingDocs, setLoadingDocs] = useState<Set<string>>(new Set());

  const handleCreate = () => {
    const name = newKBName.trim();
    if (!name) return;
    onCreateKB(name);
    setNewKBName('');
    setShowNewKB(false);
  };

  const fetchDocsForKB = useCallback(async (kbName: string, force = false) => {
    if (!force && kbDocs[kbName]) return;

    setLoadingDocs(prev => {
      const next = new Set(prev);
      next.add(kbName);
      return next;
    });

    try {
      const res = await fetch(`/api/kb/${encodeURIComponent(kbName)}/docs`);
      const data = await res.json();
      if (data.documents) {
        const docs = Object.entries(data.documents as Record<string, number>).map(([source, count]) => ({
          source,
          count,
        }));
        setKBDocs(prev => ({ ...prev, [kbName]: docs }));
      }
    } catch {
      // 静默失败
    } finally {
      setLoadingDocs(prev => {
        const next = new Set(prev);
        next.delete(kbName);
        return next;
      });
    }
  }, [kbDocs]);

  const toggleKBExpand = useCallback(async (kbName: string) => {
    setExpandedKBs(prev => {
      const next = new Set(prev);
      if (next.has(kbName)) {
        next.delete(kbName);
      } else {
        next.add(kbName);
      }
      return next;
    });

    // 展开时自动拉取文档列表
    await fetchDocsForKB(kbName);
  }, [fetchDocsForKB]);

  // 当 refreshTrigger 变化时，刷新所有已展开的 KB 文档列表
  useEffect(() => {
    if (refreshTrigger <= 0) return;
    const names = Array.from(expandedKBs);
    names.forEach(kbName => fetchDocsForKB(kbName, true));
  }, [refreshTrigger]);

  return (
    <aside className={`wb-sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* Logo */}
      <div className="wb-sidebar-header">
        <div className="wb-sidebar-logo">🧠 RAGent</div>
        <button
          onClick={onToggle}
          className="text-gray-400 hover:text-gray-600 text-sm"
          title="收起侧边栏"
        >
          {collapsed ? '☰' : '◀'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* 对话历史（多会话管理） */}
        <div className="wb-sidebar-section">
          <div className="wb-sidebar-section-title">
            <span>💬 对话历史</span>
            <button
              onClick={onNewSession}
              className="text-blue-500 hover:text-blue-700 text-xs"
              title="开始新对话"
            >
              ＋ 新对话
            </button>
          </div>

          {sessions.length === 0 && (
            <div className="text-xs text-gray-400 py-2">暂无对话记录</div>
          )}

          {sessions.map((s) => (
            <div
              key={s.id}
              className={`session-item ${s.id === activeSessionId ? 'active' : ''}`}
              onClick={() => onSelectSession(s.id)}
              title={s.title}
            >
              <span className="text-xs">💬</span>
              <div className="flex-1 min-w-0">
                <div className="truncate text-xs">{s.title || '新对话'}</div>
                <div className="session-time">{formatSessionTime(s.updatedAt)}</div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(`确认删除对话「${s.title || '新对话'}」？`)) {
                    onDeleteSession(s.id);
                  }
                }}
                className="kb-delete"
                title="删除对话"
              >
                🗑️
              </button>
            </div>
          ))}
        </div>

        {/* 知识库管理 */}
        <div className="wb-sidebar-section">
          <div className="wb-sidebar-section-title">
            <span>📚 知识库</span>
            <button
              onClick={() => setShowNewKB(!showNewKB)}
              className="text-blue-500 hover:text-blue-700 text-xs"
            >
              {showNewKB ? '取消' : '+ 新建'}
            </button>
          </div>

          {showNewKB && (
            <div className="flex gap-1 mb-2">
              <input
                type="text"
                value={newKBName}
                onChange={(e) => setNewKBName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                placeholder="知识库名称..."
                className="kb-new-input"
                autoFocus
              />
              <button
                onClick={handleCreate}
                className="px-2 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700"
              >
                确定
              </button>
            </div>
          )}

          {kbs.length === 0 && !showNewKB && (
            <div className="text-xs text-gray-400 py-2">
              暂无知识库，点击「新建」创建
            </div>
          )}

          {kbs.map((kb) => {
            const isExpanded = expandedKBs.has(kb.name);
            const docs = kbDocs[kb.name] || [];
            const isLoading = loadingDocs.has(kb.name);

            return (
              <div key={kb.name}>
                <div
                  className={`kb-item ${activeKB === kb.name ? 'active' : ''}`}
                  onClick={() => onSelectKB(kb.name)}
                >
                  <span>{getKBIcon(kb.name)}</span>
                  <span className="flex-1 truncate">{kb.name}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleKBExpand(kb.name);
                    }}
                    className="text-gray-400 hover:text-gray-600 text-xs px-1 transition-transform"
                    style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                    title={isExpanded ? '折叠文档列表' : '展开文档列表'}
                  >
                    ▶
                  </button>
                  <span className="kb-count">{kb.chunk_count}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm(`确认删除知识库「${kb.name}」？`)) {
                        onDeleteKB(kb.name);
                      }
                    }}
                    className="kb-delete"
                    title="删除知识库"
                  >
                    🗑️
                  </button>
                </div>

                {/* 展开的文档列表 */}
                {isExpanded && (
                  <div className="ml-5 mb-1 border-l-2 border-blue-100 pl-2">
                    {isLoading && (
                      <div className="text-xs text-gray-400 py-1">加载中...</div>
                    )}
                    {!isLoading && docs.length === 0 && (
                      <div className="text-xs text-gray-400 py-1">暂无文档</div>
                    )}
                    {docs.map((doc) => (
                      <div
                        key={doc.source}
                        className="doc-item"
                        onClick={() => onPreviewDoc(kb.name, doc.source)}
                        title="点击预览文档"
                      >
                        <span className="text-xs">📄</span>
                        <span className="flex-1 truncate text-xs">{doc.source}</span>
                        <span className="text-xs text-gray-400">{doc.count}段</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* 数据文件 */}
        <div className="wb-sidebar-section">
          <div className="wb-sidebar-section-title">
            <span>📊 数据文件</span>
          </div>

          {csvFiles.length === 0 && (
            <div className="text-xs text-gray-400 py-2">
              上传 CSV 文件后在此显示
            </div>
          )}

          {csvFiles.map((file) => (
            <div
              key={file.id}
              className={`csv-item ${activeCSVId === file.id ? 'active' : ''}`}
              onClick={() => onSelectCSV(file.id)}
            >
              <span>📄</span>
              <span className="flex-1 truncate">{file.name}</span>
              <span className="text-xs text-gray-400">{file.rows.length}行</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(`确认移除数据文件「${file.name}」？`)) {
                    onRemoveCSV(file.id);
                  }
                }}
                className="kb-delete"
                title="移除文件"
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        {/* 使用提示 */}
        <div className="wb-sidebar-section">
          <div className="wb-sidebar-section-title">
            <span>💡 使用提示</span>
          </div>
          <div className="text-xs text-gray-500 leading-relaxed space-y-1">
            <div>📎 上传 CSV → 自动解析数据</div>
            <div>📎 上传 PDF/TXT → 自动构建知识库</div>
            <div>💬 任何问题都会智能规划（含日常问答）</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

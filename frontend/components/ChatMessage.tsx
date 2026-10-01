'use client';

import ReactECharts from 'echarts-for-react';
import ReactMarkdown from 'react-markdown';

// ---- 类型定义 ----
interface SourceItem {
  text: string;
  source: string;
  score: number;
  chunk_index?: number;
}

interface Step {
  tool: string;
  args: Record<string, any>;
}

interface ResultItem {
  tool: string;
  args: Record<string, any>;
  result: string;
}

interface ChartConfig {
  chartType: string;
  xKey: string;
  yKey: string;
  reason: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  type?: 'text' | 'rag' | 'agent' | 'chart' | 'csv-upload' | 'doc-upload' | 'error';
  sources?: SourceItem[];
  plan?: Step[];
  results?: ResultItem[];
  chartConfig?: ChartConfig;
  chartOption?: any;
  fileName?: string;
  rowCount?: number;
  chunkCount?: number;
  kbName?: string;
  intent?: string;
  timestamp: number;
}

const TOOL_LABELS: Record<string, string> = {
  get_current_time: '🕐 时间查询',
  get_weather: '🌤️ 天气查询',
  query_knowledge_base: '📚 知识库检索',
  search_knowledge_base: '📚 知识库检索',
  analyze_csv: '📊 数据分析',
  llm_answer: '💬 智能问答',
};

const INTENT_LABELS: Record<string, { label: string; icon: string }> = {
  rag: { label: '知识库问答', icon: '📚' },
  agent: { label: '智能规划', icon: '🤖' },
  chart: { label: '数据可视化', icon: '📊' },
  general: { label: '智能对话', icon: '💬' },
};

interface ChatMessageProps {
  message: Message;
}

// 渲染 Markdown 正文（纯展示，无引用角标逻辑）
function MarkdownContent({ text }: { text: string }) {
  if (!text) return null;

  return (
    <ReactMarkdown
      components={{
        root: ({ children }: any) => <>{children}</>,
        p: ({ children }: any) => <span className="md-p">{children}</span>,
        ul: ({ children }: any) => <ul className="md-ul">{children}</ul>,
        ol: ({ children }: any) => <ol className="md-ol">{children}</ol>,
        li: ({ children }: any) => <li className="md-li">{children}</li>,
        h1: ({ children }: any) => <h1 className="md-h1">{children}</h1>,
        h2: ({ children }: any) => <h2 className="md-h2">{children}</h2>,
        h3: ({ children }: any) => <h3 className="md-h3">{children}</h3>,
        h4: ({ children }: any) => <h4 className="md-h4">{children}</h4>,
        strong: ({ children }: any) => <strong className="md-strong">{children}</strong>,
        code: ({ children }: any) => <code className="md-code">{children}</code>,
        pre: ({ children }: any) => <pre className="md-pre">{children}</pre>,
        a: ({ href, children }: any) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="md-a">
            {children}
          </a>
        ),
      } as any}
    >
      {text}
    </ReactMarkdown>
  );
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const { role, content, type } = message;

  if (role === 'user') {
    return (
      <div className="msg-row user">
        <div className="msg-bubble user">
          <div className="whitespace-pre-wrap">{content}</div>
        </div>
        <div className="msg-avatar user">🧑</div>
      </div>
    );
  }

  // 助手消息
  const intentInfo = message.intent ? INTENT_LABELS[message.intent] : null;

  return (
    <div className="msg-row">
      <div className="msg-avatar assistant">🤖</div>
      <div className="msg-bubble assistant">
        {/* 意图标签 */}
        {intentInfo && (
          <div className={`intent-badge ${message.intent}`}>
            {intentInfo.icon} {intentInfo.label}
          </div>
        )}

        {/* CSV 上传确认 */}
        {type === 'csv-upload' && (
          <div>
            <div className="text-sm font-semibold text-green-700 mb-1">
              ✅ CSV 文件已加载
            </div>
            <div className="text-xs text-gray-600">
              📄 {message.fileName} · {message.rowCount} 行数据
            </div>
            <div className="text-xs text-gray-500 mt-1">
              你可以在右侧数据面板查看表格和生成图表，或直接在对话中告诉我你想怎么分析。
            </div>
          </div>
        )}

        {/* 文档上传确认 */}
        {type === 'doc-upload' && (
          <div>
            <div className="text-sm font-semibold text-green-700 mb-1">
              ✅ 文档已入库
            </div>
            <div className="text-xs text-gray-600">
              📄 {message.fileName} → 知识库「{message.kbName}」
            </div>
            <div className="text-xs text-gray-500 mt-1">
              已切分为 {message.chunkCount} 个片段并完成向量化。现在可以基于该知识库提问了。
            </div>
          </div>
        )}

        {/* 引用来源（RAG / Agent 知识库检索共用，仅展示） */}
        {message.sources && message.sources.length > 0 && (
          <div className="rag-sources">
            <div className="rag-sources-title">📖 引用来源</div>
            {message.sources.map((src, i) => (
              <div
                key={i}
                className="rag-source-item"
              >
                <div className="rag-source-snippet">
                  <span className="rag-source-index">[{i + 1}]</span>
                  {src.text.length > 150 ? src.text.substring(0, 150) + '...' : src.text}
                </div>
                <div className="source-meta">
                  来源：{src.source} · 相关度：{(src.score * 100).toFixed(1)}%
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Agent 规划步骤 + 执行结果 */}
        {message.plan && message.plan.length > 0 && (
          <div className="agent-steps">
            <div className="agent-steps-title">📋 任务规划</div>
            {message.plan.map((step, idx) => {
              const result = message.results?.[idx];
              const isDone = !!result;
              return (
                <div key={idx} className="agent-step">
                  <div className={`agent-step-icon ${isDone ? 'done' : 'executing'}`}>
                    {isDone ? '✓' : idx + 1}
                  </div>
                  <div className="agent-step-detail">
                    <span className="tool-name">
                      {TOOL_LABELS[step.tool] || step.tool}
                    </span>
                    {Object.keys(step.args || {}).length > 0 && (
                      <span className="text-gray-400 text-xs ml-1">
                        ({JSON.stringify(step.args)})
                      </span>
                    )}
                    {result && (
                      <div className="agent-step-result">
                        {result.result.length > 120
                          ? result.result.substring(0, 120) + '...'
                          : result.result}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* 图表渲染（Agent analyze_csv 或直接图表请求） */}
        {message.chartOption && (
          <div className="mt-2">
            <ReactECharts
              option={message.chartOption}
              notMerge={true}
              style={{ height: 320 }}
              opts={{ renderer: 'canvas' }}
            />
          </div>
        )}

        {/* 主要文本内容（支持 Markdown + 引用角标） */}
        {content && (
          <div className="md-content text-sm leading-relaxed">
            <MarkdownContent text={content} />
            {message.intent === 'agent' && !message.results && message.plan && (
              <span className="inline-block w-2 h-4 bg-blue-500 ml-0.5 animate-pulse" />
            )}
          </div>
        )}

        {/* 空内容且在加载中 */}
        {!content && type !== 'csv-upload' && type !== 'doc-upload' && !message.chartOption && (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <div className="dot animate-pulse" style={{ width: 6, height: 6, borderRadius: '50%', background: '#3b82f6' }} />
            思考中...
          </div>
        )}

        {/* 错误 */}
        {type === 'error' && (
          <div className="text-sm text-red-600">⚠️ {content}</div>
        )}
      </div>
    </div>
  );
}

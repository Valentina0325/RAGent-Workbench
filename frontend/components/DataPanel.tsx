'use client';

import { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import debounce from 'lodash.debounce';
import { DataTableVirtual } from './DataTableVirtual';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';

interface CSVFile {
  id: string;
  name: string;
  headers: string[];
  rows: any[];
}

interface DataPanelProps {
  file: CSVFile | null;
  collapsed: boolean;
  onToggle: () => void;
}

type ChartType = 'bar' | 'line' | 'pie' | 'scatter';

function buildChartOption(rows: any[], xKey: string, yKey: string, chartType: ChartType): any {
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
  if (seriesData.length === 0) return null;

  if (chartType === 'pie') {
    return {
      title: { text: `${yKey} 分布`, left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'item' },
      xAxis: { show: false },
      yAxis: { show: false },
      series: [{
        name: yKey, type: 'pie', radius: '55%',
        data: xAxisData.map((name, idx) => ({ name, value: seriesData[idx] })),
      }],
    };
  } else if (chartType === 'scatter') {
    return {
      title: { text: `${yKey} 散点图`, left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'item' },
      xAxis: { type: 'category', name: xKey },
      yAxis: { type: 'value', name: yKey },
      series: [{ type: 'scatter', data: seriesData.map((y, idx) => [idx, y]), symbolSize: 8 }],
    };
  } else {
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
}

// ---- 全列统计（供 AI 报告使用）----
function computeAllStats(headers: string[], rows: any[]): Record<string, any> {
  const stats: Record<string, any> = {};
  for (const h of headers) {
    const vals = rows.map(r => parseFloat(r[h])).filter(v => !isNaN(v));
    if (vals.length >= Math.max(1, Math.floor(rows.length * 0.5))) {
      const sum = vals.reduce((a, b) => a + b, 0);
      stats[h] = {
        类型: '数值',
        非空数: vals.length,
        均值: Number((sum / vals.length).toFixed(2)),
        最大: Math.max(...vals),
        最小: Math.min(...vals),
      };
    } else {
      const uniqueVals = new Set(rows.map(r => String(r[h] ?? '').trim()).filter(Boolean));
      stats[h] = { 类型: '文本', 非空数: uniqueVals.size, 唯一值数: uniqueVals.size };
    }
  }
  return stats;
}

// ---- 简易 Markdown 渲染（标题 / 加粗 / 列表 / 段落）----
function renderInline(text: string, keyPrefix: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return <strong key={`${keyPrefix}-${i}`} className="font-semibold text-gray-800">{p.slice(2, -2)}</strong>;
    }
    return <span key={`${keyPrefix}-${i}`}>{p}</span>;
  });
}

function RenderMarkdown({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="text-xs leading-relaxed text-gray-600 space-y-1">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} className="h-1.5" />;
        if (trimmed.startsWith('### ')) {
          return <div key={i} className="text-sm font-medium text-gray-800 pt-1.5">{renderInline(trimmed.slice(4), `h${i}`)}</div>;
        }
        if (trimmed.startsWith('## ')) {
          return (
            <div key={i} className="flex items-center gap-1.5 pt-2.5 pb-0.5">
              <span className="w-1 h-3.5 bg-blue-500 rounded-sm" />
              <span className="text-sm font-medium text-gray-800">{renderInline(trimmed.slice(3), `h${i}`)}</span>
            </div>
          );
        }
        if (trimmed.startsWith('# ')) {
          return <div key={i} className="text-sm font-medium text-gray-800 pt-1.5">{renderInline(trimmed.slice(2), `h${i}`)}</div>;
        }
        if (/^[-*•]\s+/.test(trimmed)) {
          return (
            <div key={i} className="flex gap-1.5 pl-2">
              <span className="text-blue-400 shrink-0">•</span>
              <span>{renderInline(trimmed.replace(/^[-*•]\s+/, ''), `l${i}`)}</span>
            </div>
          );
        }
        if (/^\d+[.、)]\s+/.test(trimmed)) {
          return (
            <div key={i} className="flex gap-1.5 pl-2">
              <span className="text-blue-500 shrink-0 font-medium">{trimmed.match(/^\d+/)?.[0]}.</span>
              <span>{renderInline(trimmed.replace(/^\d+[.、)]\s+/, ''), `n${i}`)}</span>
            </div>
          );
        }
        return <div key={i} className="pl-0.5">{renderInline(trimmed, `p${i}`)}</div>;
      })}
    </div>
  );
}

export default function DataPanel({ file, collapsed, onToggle }: DataPanelProps) {
  const [chartType, setChartType] = useState<ChartType>('bar');
  const [xKey, setXKey] = useState('');
  const [yKey, setYKey] = useState('');
  const [chartOption, setChartOption] = useState<any>(null);
  const chartRef = useRef<ReactECharts>(null);

  // ---- AI 报告状态 ----
  const [aiReport, setAiReport] = useState('');
  const [reportLoading, setReportLoading] = useState(false);
  const reportAbortRef = useRef<AbortController | null>(null);

  const headers = file?.headers || [];
  const rows = file?.rows || [];

  // Auto-select keys when file changes
  useEffect(() => {
    if (headers.length >= 2) {
      setXKey(headers[0]);
      setYKey(headers[1]);
    } else if (headers.length === 1) {
      setXKey(headers[0]);
      setYKey(headers[0]);
    }
    setChartOption(null);
    // 切换文件时中止进行中的请求，并载入该文件此前保存的报告（历史保留，不自动清空）
    reportAbortRef.current?.abort();
    setReportLoading(false);
    let saved = '';
    if (file?.id) {
      try {
        saved = localStorage.getItem(`workbench_ai_report_${file.id}`) || '';
      } catch {}
    }
    setAiReport(saved);
  }, [file?.id]);

  const stats = useMemo(() => {
    if (!rows.length || !yKey) return null;
    const yValues = rows.map(r => parseFloat(r[yKey])).filter(v => !isNaN(v));
    if (!yValues.length) return null;
    const sum = yValues.reduce((a, b) => a + b, 0);
    const sorted = [...yValues].sort((a, b) => a - b);
    return {
      count: yValues.length,
      sum: sum.toFixed(2),
      max: Math.max(...yValues),
      min: Math.min(...yValues),
      avg: (sum / yValues.length).toFixed(2),
      median: sorted[Math.floor(sorted.length / 2)],
    };
  }, [rows, yKey]);

  const generateChartCore = useCallback(() => {
    return buildChartOption(rows, xKey, yKey, chartType);
  }, [rows, xKey, yKey, chartType]);

  const debouncedGenerate = useMemo(
    () => debounce(() => {
      const opt = generateChartCore();
      if (opt) setChartOption(opt);
    }, 300),
    [generateChartCore]
  );

  const handleGenerate = () => {
    const opt = generateChartCore();
    if (opt) setChartOption(opt);
  };

  // Update chart when keys/type change
  useEffect(() => {
    if (xKey && yKey) {
      debouncedGenerate();
    }
  }, [xKey, yKey, chartType]);

  // ---- 生成 AI 数据报告 ----
  const handleGenerateReport = async () => {
    if (!file || reportLoading) return;
    const fileId = file.id;
    reportAbortRef.current?.abort();
    const controller = new AbortController();
    reportAbortRef.current = controller;

    setReportLoading(true);
    setAiReport('');

    try {
      const response = await fetch('/api/csv-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          fileName: file.name,
          headers: file.headers,
          sampleRows: file.rows.slice(0, 5),
          stats: computeAllStats(file.headers, file.rows),
          rowCount: file.rows.length,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let acc = '';

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
            if (data.type === 'token' && data.content) {
              acc += data.content;
              setAiReport(acc);
            } else if (data.type === 'error') {
              acc = `⚠️ ${data.content}`;
              setAiReport(acc);
            }
          } catch {}
        }
      }

      // 生成完成即持久化，下次打开该文件仍能看到这份报告
      if (acc) {
        try {
          localStorage.setItem(`workbench_ai_report_${fileId}`, acc);
        } catch {}
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setAiReport(`⚠️ 报告生成失败：${err.message}`);
      }
    } finally {
      setReportLoading(false);
    }
  };

  // 清除当前报告（同时删除本地保存的历史）
  const clearReport = () => {
    setAiReport('');
    if (file?.id) {
      try {
        localStorage.removeItem(`workbench_ai_report_${file.id}`);
      } catch {}
    }
  };

  // 导出报告为 Markdown 文件
  const exportReport = () => {
    if (!aiReport) return;
    const blob = new Blob([aiReport], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.download = `${(file?.name || 'data').replace(/\.csv$/i, '')}_AI报告.md`;
    link.href = url;
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportChart = () => {
    if (chartRef.current) {
      const canvas = chartRef.current.getEchartsInstance().renderToCanvas();
      const link = document.createElement('a');
      link.download = `${file?.name || 'chart'}.png`;
      link.href = canvas.toDataURL();
      link.click();
    }
  };

  const useVirtualScroll = rows.length > 100;

  if (!file) {
    return (
      <div className={`wb-data-panel ${collapsed ? 'collapsed' : ''}`}>
        <div className="wb-data-panel-header">
          <span className="text-sm font-medium text-gray-700">📊 数据面板</span>
          <button onClick={onToggle} className="text-gray-400 hover:text-gray-600 text-sm">
            ▶
          </button>
        </div>
        <div className="wb-data-panel-body">
          <div className="text-center text-gray-400 py-12">
            <div className="text-4xl mb-3">📊</div>
            <div className="text-sm">上传 CSV 文件后</div>
            <div className="text-sm">在此查看图表和数据</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`wb-data-panel ${collapsed ? 'collapsed' : ''}`}>
      <div className="wb-data-panel-header">
        <div>
          <span className="text-sm font-medium text-gray-700">📊 数据面板</span>
          <span className="text-xs text-gray-400 ml-2">{file.name}</span>
        </div>
        <button onClick={onToggle} className="text-gray-400 hover:text-gray-600 text-sm">
          ▶
        </button>
      </div>

      <div className="wb-data-panel-body">
        {/* AI 数据报告 */}
        <div className="mb-4 border border-blue-100 rounded-lg overflow-hidden bg-blue-50/40">
          <div className="flex items-center justify-between px-3 py-2 bg-blue-50 border-b border-blue-100">
            <span className="text-xs font-medium text-blue-800">
              🤖 AI 数据报告
            </span>
            <div className="flex items-center gap-2">
              {aiReport && !reportLoading && (
                <>
                  <button
                    onClick={exportReport}
                    className="px-2.5 py-1 rounded-lg text-xs font-medium bg-white text-blue-700 border border-blue-200 hover:bg-blue-100 transition-all"
                    title="导出报告为 Markdown 文件"
                  >
                    ⬇ 导出报告
                  </button>
                  <button
                    onClick={clearReport}
                    className="text-xs text-gray-400 hover:text-gray-600"
                    title="清除报告"
                  >
                    ✕
                  </button>
                </>
              )}
              <button
                onClick={handleGenerateReport}
                disabled={reportLoading}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  reportLoading
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                }`}
              >
                {reportLoading ? '⏳ 生成中...' : aiReport ? '🔄 重新生成' : '✨ 生成报告'}
              </button>
            </div>
          </div>
          <div className="p-3 max-h-[340px] overflow-y-auto">
            {reportLoading && !aiReport && (
              <div className="flex items-center gap-2 text-gray-400 text-xs py-2">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                正在分析数据并生成报告...
              </div>
            )}
            {aiReport ? (
              <>
                <RenderMarkdown text={aiReport} />
                {reportLoading && (
                  <span className="inline-block w-1.5 h-3.5 bg-blue-500 ml-0.5 animate-pulse align-middle" />
                )}
              </>
            ) : (
              !reportLoading && (
                <div className="text-xs text-gray-400 py-1">
                  点击「生成报告」，AI 将基于当前 CSV 数据的统计特征自动生成
                  数据概览、关键发现、数据质量与分析建议。
                </div>
              )
            )}
          </div>
        </div>

        {/* 控制面板 */}
        <div className="mb-4 space-y-3">
          {/* 图表类型 */}
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">图表类型</label>
            <div className="flex gap-1.5">
              {(['bar', 'line', 'pie', 'scatter'] as ChartType[]).map(t => (
                <button
                  key={t}
                  onClick={() => setChartType(t)}
                  className={`px-2.5 py-1 rounded-lg text-xs transition-all ${
                    chartType === t
                      ? 'bg-blue-600 text-white shadow'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {t === 'bar' && '📊'}
                  {t === 'line' && '📈'}
                  {t === 'pie' && '🥧'}
                  {t === 'scatter' && '✨'}
                </button>
              ))}
            </div>
          </div>

          {/* X/Y 轴 */}
          {chartType !== 'pie' ? (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-gray-500">X 轴</label>
                <select
                  value={xKey}
                  onChange={e => setXKey(e.target.value)}
                  className="w-full text-xs border border-gray-200 rounded-md px-2 py-1"
                >
                  {headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-500">Y 轴</label>
                <select
                  value={yKey}
                  onChange={e => setYKey(e.target.value)}
                  className="w-full text-xs border border-gray-200 rounded-md px-2 py-1"
                >
                  {headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-gray-500">分类列</label>
                <select value={xKey} onChange={e => setXKey(e.target.value)} className="w-full text-xs border border-gray-200 rounded-md px-2 py-1">
                  {headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-500">数值列</label>
                <select value={yKey} onChange={e => setYKey(e.target.value)} className="w-full text-xs border border-gray-200 rounded-md px-2 py-1">
                  {headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
            </div>
          )}

          <button onClick={handleGenerate} className="w-full py-1.5 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700">
            ✨ 生成图表
          </button>
        </div>

        {/* 图表 */}
        {chartOption && (
          <div className="mb-4 bg-white border border-gray-100 rounded-lg p-2">
            <ReactECharts ref={chartRef} option={chartOption} notMerge={true} style={{ height: 280 }} />
            <button onClick={exportChart} className="text-xs text-gray-400 hover:text-blue-600 mt-1">
              📸 导出为 PNG
            </button>
          </div>
        )}

        {/* 统计信息 */}
        {stats && (
          <div className="mb-4 p-3 bg-gray-50 rounded-lg">
            <div className="text-xs font-medium text-gray-600 mb-2">📈 统计信息（{yKey}）</div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div><span className="text-gray-400">行数</span><br /><span className="font-medium">{stats.count}</span></div>
              <div><span className="text-gray-400">总和</span><br /><span className="font-medium">{stats.sum}</span></div>
              <div><span className="text-gray-400">均值</span><br /><span className="font-medium">{stats.avg}</span></div>
              <div><span className="text-gray-400">中位数</span><br /><span className="font-medium">{stats.median}</span></div>
              <div><span className="text-gray-400">最大</span><br /><span className="font-medium text-red-500">{stats.max}</span></div>
              <div><span className="text-gray-400">最小</span><br /><span className="font-medium text-green-600">{stats.min}</span></div>
            </div>
          </div>
        )}

        {/* 数据表格 */}
        {rows.length > 0 && (
          <div className="border border-gray-100 rounded-lg overflow-hidden">
            <div className="bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600 border-b border-gray-100">
              📋 数据表格（{rows.length} 行）
            </div>
            {useVirtualScroll ? (
              <DataTableVirtual headers={headers} rows={rows} rowHeight={40} height={300} />
            ) : (
              <div className="overflow-auto max-h-[300px]">
                <Table className="min-w-full">
                  <TableHeader className="bg-gray-50 sticky top-0">
                    <TableRow className="border-b">
                      {headers.map(h => (
                        <TableHead key={h} className="px-3 py-2 text-left text-xs font-semibold text-gray-700">
                          {h}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((row, idx) => (
                      <TableRow key={idx} className="hover:bg-blue-50 border-b border-gray-50">
                        {headers.map(h => (
                          <TableCell key={h} className="px-3 py-1.5 text-xs text-gray-600">
                            {String(row[h] ?? '')}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

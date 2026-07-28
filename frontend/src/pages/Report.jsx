import React, { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getReport,
  generateReport,
  getProfile,
  getChatHistory,
  sendQuery,
  getDatasetRows,
} from '../api'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts'
import {
  ArrowLeft,
  Brain,
  CheckCircle2,
  Download,
  Send,
  Loader2,
  AlertTriangle,
  BarChart3,
  TrendingUp,
  Table as TableIcon,
  MessageSquare,
  Bot,
  User,
  Sparkles,
  Layers,
  Activity,
  ShieldAlert,
  Zap,
  Sliders,
} from 'lucide-react'

// Helper for rendering inline charts inside Chat messages
function InlineChatResult({ chartConfig, data }) {
  if (!data) return null

  if (Array.isArray(data) && data.length > 0) {
    const keys = Object.keys(data[0]).slice(0, 5)

    if (chartConfig?.type === 'line' && chartConfig?.x_key && chartConfig?.y_key) {
      return (
        <div className="mt-3 p-3 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-xs font-semibold text-cyan-400">
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Trend Chart ({chartConfig.y_key} vs {chartConfig.x_key})</span>
          </div>
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey={chartConfig.x_key} stroke="#94a3b8" fontSize={10} />
                <YAxis stroke="#94a3b8" fontSize={10} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }} />
                <Line type="monotone" dataKey={chartConfig.y_key} stroke="#06b6d4" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )
    }

    if (chartConfig?.type === 'bar' && chartConfig?.x_key && chartConfig?.y_key) {
      return (
        <div className="mt-3 p-3 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-xs font-semibold text-teal-400">
            <BarChart3 className="w-3.5 h-3.5" />
            <span>Comparison Chart ({chartConfig.y_key} by {chartConfig.x_key})</span>
          </div>
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey={chartConfig.x_key} stroke="#94a3b8" fontSize={10} />
                <YAxis stroke="#94a3b8" fontSize={10} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }} />
                <Bar dataKey={chartConfig.y_key} fill="#14b8a6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )
    }

    // Default Table view for records
    return (
      <div className="mt-3 p-2 bg-slate-950/80 border border-slate-800 rounded-xl overflow-x-auto">
        <div className="flex items-center space-x-2 text-xs font-semibold text-slate-400 mb-2 px-1">
          <TableIcon className="w-3.5 h-3.5" />
          <span>Result Table ({data.length} rows)</span>
        </div>
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-slate-900 text-slate-400 border-b border-slate-800">
            <tr>
              {keys.map((k) => (
                <th key={k} className="p-1.5 font-semibold">{k}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-slate-300">
            {data.slice(0, 8).map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-900/40">
                {keys.map((k) => (
                  <td key={k} className="p-1.5 truncate max-w-[120px]">{String(row[k] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return null
}

export default function Report() {
  const { datasetId } = useParams()
  const [report, setReport] = useState(null)
  const [profile, setProfile] = useState(null)
  const [sampleRows, setSampleRows] = useState([])
  const [anomalousRows, setAnomalousRows] = useState([])
  const [chatHistory, setChatHistory] = useState([])
  const [question, setQuestion] = useState('')
  const [selectedNumCol, setSelectedNumCol] = useState('')
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [querying, setQuerying] = useState(false)
  const [error, setError] = useState('')

  const chatEndRef = useRef(null)

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [chatHistory, querying])

  useEffect(() => {
    const loadAllReportData = async () => {
      setLoading(true)
      setError('')

      try {
        // 1. Fetch Profile
        let currentProfile = null
        try {
          currentProfile = await getProfile(datasetId)
          setProfile(currentProfile)
        } catch (e) {
          console.log('Profile load notice:', e)
        }

        // 2. Fetch Sample Rows for Telemetry Plot
        try {
          const rowsRes = await getDatasetRows(datasetId)
          setSampleRows(rowsRes.rows || [])
        } catch (e) {
          console.log('Sample rows fetch notice:', e)
        }

        // 3. Fetch Chat History
        try {
          const history = await getChatHistory(datasetId)
          setChatHistory(history || [])
        } catch (e) {
          console.log('Chat history load notice:', e)
        }

        // 4. Fetch or Generate Report
        try {
          const repData = await getReport(datasetId)
          setReport(repData)
          fetchAnomaliesIfPresent(repData)
        } catch (repErr) {
          if (repErr.response?.status === 404) {
            setGenerating(true)
            const newReport = await generateReport(datasetId)
            setReport(newReport)
            fetchAnomaliesIfPresent(newReport)
            setGenerating(false)
          } else {
            throw repErr
          }
        }
      } catch (err) {
        console.error(err)
        setError('Failed to load dataset report. Please ensure the backend server is running.')
      } finally {
        setLoading(false)
      }
    }

    loadAllReportData()
  }, [datasetId])

  const fetchAnomaliesIfPresent = async (repData) => {
    const rawProf = repData?.raw_profile_reference
    const indices = rawProf?.anomalies?.anomalous_row_indices
    if (indices && indices.length > 0) {
      try {
        const rowsRes = await getDatasetRows(datasetId, indices.slice(0, 10).join(','))
        setAnomalousRows(rowsRes.rows || [])
      } catch (e) {
        console.log('Anomalous rows fetch notice:', e)
      }
    }
  }

  // Set default selected numeric column for telemetry chart
  useEffect(() => {
    const numericCols = profile?.columns?.filter((c) => c.dtype === 'numeric').map((c) => c.name) || []
    if (numericCols.length > 0 && !selectedNumCol) {
      setSelectedNumCol(numericCols[0])
    }
  }, [profile])

  const handleSendQuery = async (e) => {
    e.preventDefault()
    if (!question.trim() || querying) return

    const userQ = question.trim()
    setQuestion('')
    setQuerying(true)

    const tempMessage = {
      question: userQ,
      answer_text: 'Analyzing dataset...',
      loading: true,
      timestamp: new Date().toISOString(),
    }
    setChatHistory((prev) => [...prev, tempMessage])

    try {
      const res = await sendQuery(datasetId, userQ)
      setChatHistory((prev) =>
        prev.map((msg) =>
          msg.loading && msg.question === userQ
            ? {
                question: userQ,
                answer_text: res.answer_text,
                data: res.data,
                chart_config: res.chart_config,
                timestamp: new Date().toISOString(),
              }
            : msg
        )
      )
    } catch (err) {
      console.error(err)
      setChatHistory((prev) =>
        prev.map((msg) =>
          msg.loading && msg.question === userQ
            ? {
                question: userQ,
                answer_text: 'Error processing question. Please try rephrasing.',
                error: true,
                timestamp: new Date().toISOString(),
              }
            : msg
        )
      )
    } finally {
      setQuerying(false)
    }
  }

  const handleExportPDF = () => {
    window.print()
  }

  // X-Axis Column Name for Telemetry Stream
  const dtColName = profile?.columns?.find((c) => c.dtype === 'datetime')?.name || profile?.columns?.[0]?.name || 'index'
  const numericCols = profile?.columns?.filter((c) => c.dtype === 'numeric').map((c) => c.name) || []

  // Unique count chart data for Data Quality section
  const columnUniqueData =
    profile?.columns?.map((c) => ({
      name: c.name,
      unique_count: c.unique_count ?? c.outlier_count ?? 1,
      missing_pct: c.missing_pct,
    })) || []

  const indSignals = profile?.industrial_signals || {}
  const correlations = profile?.correlations || []

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 print:p-0 print:m-0 print:max-w-none">
      
      {/* Top Header Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-5 print:hidden">
        <Link
          to="/"
          className="inline-flex items-center space-x-2 text-sm font-medium text-slate-400 hover:text-teal-400 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Dashboard</span>
        </Link>

        <div className="flex items-center space-x-3">
          <button
            onClick={handleExportPDF}
            className="inline-flex items-center space-x-2 bg-slate-800 hover:bg-slate-700 active:bg-slate-900 border border-slate-700 text-slate-200 text-sm font-medium px-4 py-2 rounded-xl transition-all shadow-sm hover:border-teal-500/40"
          >
            <Download className="w-4 h-4 text-teal-400" />
            <span>Export Report (PDF)</span>
          </button>
        </div>
      </div>

      {/* Loading or Error Overlay */}
      {loading || generating ? (
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-16 text-center space-y-6">
          <div className="inline-flex p-4 bg-teal-500/10 border border-teal-500/30 rounded-3xl text-teal-400">
            <Loader2 className="w-10 h-10 animate-spin" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-slate-100">
              {generating ? 'Generating Comprehensive AI Report with LangGraph...' : 'Loading Report Workspace...'}
            </h2>
            <p className="text-sm text-slate-400 max-w-md mx-auto">
              Synthesizing schema intent, Isolation Forest anomalies, 3-sigma signal breaches, and actionable recommendations.
            </p>
          </div>
        </div>
      ) : error ? (
        <div className="p-8 bg-rose-500/10 border border-rose-500/30 rounded-3xl text-center space-y-4">
          <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
          <h3 className="text-lg font-bold text-rose-200">{error}</h3>
          <Link
            to="/"
            className="inline-block bg-slate-800 hover:bg-slate-700 text-slate-200 px-5 py-2 rounded-xl text-sm font-medium border border-slate-700"
          >
            Return to Dashboard
          </Link>
        </div>
      ) : (
        /* Report Grid Layout: Left 2/3 Content + Right 1/3 Chat Drawer */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
          
          {/* LEFT COLUMN: COMPREHENSIVE REPORT BODY */}
          <div className="lg:col-span-2 space-y-8 print:w-full">
            
            {/* 1. EXECUTIVE REPORT BANNER */}
            <div className="bg-gradient-to-r from-slate-900 via-slate-900/90 to-slate-800/80 border border-slate-800 rounded-3xl p-8 shadow-xl space-y-6 print:bg-white print:text-black print:border-none print:shadow-none">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex items-center space-x-3">
                  <div className="p-3 bg-teal-500/10 border border-teal-500/30 rounded-2xl text-teal-400 print:hidden">
                    <Brain className="w-8 h-8" />
                  </div>
                  <div>
                    <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-100 print:text-black">
                      Industrial Operational Report
                    </h1>
                    <span className="text-sm font-mono text-teal-400 print:text-black">
                      Dataset ID: {datasetId}
                    </span>
                  </div>
                </div>

                <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-full text-emerald-400 text-xs font-semibold uppercase tracking-wider print:border-gray-300 print:text-black">
                  <Activity className="w-4 h-4" />
                  <span>Profile & Report Validated</span>
                </div>
              </div>

              {/* Dataset Quick Metrics Bar */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4 border-t border-slate-800/80 print:border-gray-300">
                <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl print:bg-gray-100">
                  <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold block print:text-gray-600">
                    Dataset Filename
                  </span>
                  <span className="text-sm font-bold font-mono text-slate-200 truncate block print:text-black" title={profile?.filename}>
                    {profile?.filename || 'dataset.csv'}
                  </span>
                </div>

                <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl print:bg-gray-100">
                  <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold block print:text-gray-600">
                    Row & Column Count
                  </span>
                  <span className="text-sm font-bold font-mono text-teal-400 print:text-black">
                    {profile?.shape?.rows?.toLocaleString() || 0} rows × {profile?.shape?.columns || 0} cols
                  </span>
                </div>

                <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl print:bg-gray-100">
                  <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold block print:text-gray-600">
                    Memory Footprint
                  </span>
                  <span className="text-sm font-bold font-mono text-cyan-400 print:text-black">
                    {profile?.memory_usage_mb || 0} MB
                  </span>
                </div>

                <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl print:bg-gray-100">
                  <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold block print:text-gray-600">
                    Anomalous Rows
                  </span>
                  <span className="text-sm font-bold font-mono text-amber-400 print:text-black">
                    {profile?.anomalies?.anomalous_row_count ?? 0} ({profile?.anomalies?.anomalous_row_pct ?? 0}%)
                  </span>
                </div>
              </div>
            </div>

            {/* 2. OVERVIEW & SCHEMA INTENT */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 shadow-xl space-y-6 print:bg-white print:border-gray-300 print:shadow-none">
              <div className="flex items-center space-x-2 border-b border-slate-800 pb-3 print:border-gray-300">
                <Sparkles className="w-5 h-5 text-teal-400 print:hidden" />
                <h2 className="text-xl font-bold text-slate-100 print:text-black">
                  1. Executive Overview & Schema Intent
                </h2>
              </div>

              {report?.schema_summary && (
                <div className="p-4 bg-teal-500/10 border border-teal-500/20 rounded-2xl text-teal-300 text-sm font-medium leading-relaxed print:bg-gray-100 print:text-black">
                  <span className="font-bold block mb-1 uppercase tracking-wider text-xs text-teal-400 print:text-black">
                    Schema Classification & Intent
                  </span>
                  {report.schema_summary}
                </div>
              )}

              <div className="text-slate-300 text-sm leading-relaxed whitespace-pre-line print:text-black">
                {report?.overview}
              </div>
            </div>

            {/* 3. INTERACTIVE TELEMETRY STREAM & TREND ANALYSIS */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 shadow-xl space-y-6 print:bg-white print:border-gray-300 print:shadow-none">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-3 print:border-gray-300">
                <div className="flex items-center space-x-2">
                  <TrendingUp className="w-5 h-5 text-cyan-400 print:hidden" />
                  <h2 className="text-xl font-bold text-slate-100 print:text-black">
                    2. Telemetry Stream & Trend Analysis
                  </h2>
                </div>

                {/* Dropdown Selector for Plotting Telemetry Column */}
                {numericCols.length > 0 && (
                  <div className="flex items-center space-x-2 print:hidden">
                    <Sliders className="w-4 h-4 text-slate-400" />
                    <span className="text-xs text-slate-400">Signal:</span>
                    <select
                      value={selectedNumCol}
                      onChange={(e) => setSelectedNumCol(e.target.value)}
                      className="bg-slate-950 border border-slate-800 text-teal-300 text-xs font-mono font-semibold rounded-xl px-3 py-1.5 focus:outline-none focus:border-teal-500"
                    >
                      {numericCols.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* Narrative Text */}
              <div className="text-slate-300 text-sm leading-relaxed whitespace-pre-line print:text-black">
                {report?.key_trends}
              </div>

              {/* Correlation Badges */}
              {correlations.length > 0 && (
                <div className="space-y-2 pt-2">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                    Observed Variable Correlations ({correlations.length} pairs analyzed)
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {correlations.slice(0, 6).map((c, idx) => (
                      <span
                        key={idx}
                        className={`inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl text-xs font-mono font-medium border ${
                          Math.abs(c.correlation) > 0.7
                            ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
                            : 'bg-slate-800/80 text-slate-300 border-slate-700/80'
                        }`}
                      >
                        <span>{c.col_a} ↔ {c.col_b}:</span>
                        <span className="font-bold">{c.correlation > 0 ? `+${c.correlation}` : c.correlation}</span>
                        {Math.abs(c.correlation) > 0.7 && <span className="text-[10px] bg-cyan-500/20 px-1.5 py-0.5 rounded text-cyan-200">Strong</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Telemetry Line Chart (Plots Actual Dataset Rows) */}
              {sampleRows.length > 0 && selectedNumCol && (
                <div className="space-y-2 pt-4">
                  <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
                    <span className="text-cyan-400 font-semibold uppercase tracking-wider">
                      Telemetry Stream: {selectedNumCol} over {dtColName}
                    </span>
                    <span>Sample Window: {sampleRows.length} data points</span>
                  </div>

                  <div className="h-72 w-full pt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={sampleRows}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                        <XAxis dataKey={dtColName} stroke="#94a3b8" fontSize={10} tickFormatter={(v) => String(v).slice(-8)} />
                        <YAxis stroke="#94a3b8" fontSize={11} domain={['auto', 'auto']} />
                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '12px', fontSize: '11px' }} />
                        <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }} />
                        <Line
                          type="monotone"
                          dataKey={selectedNumCol}
                          name={`${selectedNumCol} reading`}
                          stroke="#06b6d4"
                          strokeWidth={2.5}
                          dot={{ r: 3, fill: '#06b6d4' }}
                          activeDot={{ r: 6 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>

            {/* 4. DATA QUALITY & COLUMN STATISTICS */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 shadow-xl space-y-6 print:bg-white print:border-gray-300 print:shadow-none">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3 print:border-gray-300">
                <div className="flex items-center space-x-2">
                  <BarChart3 className="w-5 h-5 text-teal-400 print:hidden" />
                  <h2 className="text-xl font-bold text-slate-100 print:text-black">
                    3. Data Quality & Column Distribution
                  </h2>
                </div>
                <span className="text-xs text-slate-400 font-mono">Cardinality & Completeness</span>
              </div>

              {/* Column Cardinality / Unique Count Bar Chart */}
              {columnUniqueData.length > 0 && (
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-teal-400 uppercase tracking-wider block">
                    Column Unique Values Distribution
                  </span>
                  <div className="h-56 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={columnUniqueData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                        <XAxis dataKey="name" stroke="#94a3b8" fontSize={11} />
                        <YAxis stroke="#94a3b8" fontSize={11} />
                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '12px' }} />
                        <Bar dataKey="unique_count" name="Unique Count" fill="#14b8a6" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Detailed Column Statistics Table */}
              <div className="overflow-x-auto border border-slate-800 rounded-2xl print:border-gray-300">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 print:bg-gray-100 print:text-black">
                    <tr>
                      <th className="p-3">Column Name</th>
                      <th className="p-3">Type</th>
                      <th className="p-3">Missing %</th>
                      <th className="p-3">Mean / Unique</th>
                      <th className="p-3">Min / Top Value</th>
                      <th className="p-3">Max</th>
                      <th className="p-3">IQR Outliers</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300 print:divide-gray-200 print:text-black">
                    {profile?.columns?.map((col) => (
                      <tr key={col.name} className="hover:bg-slate-800/40">
                        <td className="p-3 font-semibold text-slate-100 print:text-black">{col.name}</td>
                        <td className="p-3 text-teal-400 font-bold print:text-black">{col.dtype}</td>
                        <td className="p-3">{col.missing_pct}%</td>
                        <td className="p-3 text-cyan-300">
                          {col.mean !== undefined && col.mean !== null ? col.mean : (col.unique_count ?? 'N/A')}
                        </td>
                        <td className="p-3">
                          {col.min !== undefined && col.min !== null ? col.min : (col.top_5_values?.[0]?.value ?? 'N/A')}
                        </td>
                        <td className="p-3">{col.max !== undefined && col.max !== null ? col.max : 'N/A'}</td>
                        <td className="p-3 text-amber-400 font-bold">{col.outlier_count ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 5. ANOMALIES & INDUSTRIAL SIGNALS */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 shadow-xl space-y-6 print:bg-white print:border-gray-300 print:shadow-none">
              <div className="flex items-center space-x-2 border-b border-slate-800 pb-3 print:border-gray-300">
                <ShieldAlert className="w-5 h-5 text-amber-400 print:hidden" />
                <h2 className="text-xl font-bold text-slate-100 print:text-black">
                  4. Operational Anomalies & Industrial Signals
                </h2>
              </div>

              <div className="text-slate-300 text-sm leading-relaxed whitespace-pre-line print:text-black">
                {report?.anomalies}
              </div>

              {/* Industrial Signal Breach Badges */}
              {Object.keys(indSignals).length > 0 && (
                <div className="space-y-3 pt-2">
                  <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider block">
                    Monitored Industrial Signals (3-Sigma Threshold Breaches)
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {Object.entries(indSignals).map(([colName, sig]) => (
                      <div
                        key={colName}
                        className="p-4 bg-slate-950/80 border border-slate-800 rounded-2xl space-y-1"
                      >
                        <div className="flex items-center justify-between text-xs font-mono">
                          <span className="font-bold text-slate-200">{colName}</span>
                          <Zap className={`w-3.5 h-3.5 ${sig.threshold_breach_count > 0 ? 'text-amber-400 animate-pulse' : 'text-slate-600'}`} />
                        </div>
                        <div className="text-lg font-bold font-mono text-amber-400">
                          {sig.threshold_breach_count} breach(es)
                        </div>
                        <span className="text-xs text-slate-500 font-mono block">
                          Breach Rate: {sig.threshold_breach_pct}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Anomalous Dataset Rows Table */}
              {anomalousRows.length > 0 && (
                <div className="space-y-3 pt-2">
                  <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider block">
                    Multivariate Anomalous Records (Isolation Forest Identified)
                  </span>
                  <div className="overflow-x-auto border border-amber-500/30 rounded-2xl bg-amber-500/5">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-slate-950/80 text-amber-300 border-b border-amber-500/30">
                        <tr>
                          {Object.keys(anomalousRows[0]).map((k) => (
                            <th key={k} className="p-2.5 font-semibold">{k}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 text-slate-200">
                        {anomalousRows.map((row, idx) => (
                          <tr key={idx} className="hover:bg-slate-900/60">
                            {Object.keys(anomalousRows[0]).map((k) => (
                              <td key={k} className="p-2.5">{String(row[k] ?? '')}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* 6. STRATEGIC ACTION PLAN & RECOMMENDATIONS */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 shadow-xl space-y-6 print:bg-white print:border-gray-300 print:shadow-none">
              <div className="flex items-center space-x-2 border-b border-slate-800 pb-3 print:border-gray-300">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 print:hidden" />
                <h2 className="text-xl font-bold text-slate-100 print:text-black">
                  5. Actionable Operational Recommendations
                </h2>
              </div>

              <div className="space-y-3">
                {report?.recommendations?.map((rec, idx) => (
                  <div
                    key={idx}
                    className="flex items-start space-x-3.5 p-4 bg-slate-950/60 border border-slate-800/80 rounded-2xl print:bg-gray-50 print:border-gray-200"
                  >
                    <div className="p-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-400 mt-0.5 print:hidden">
                      <CheckCircle2 className="w-4 h-4" />
                    </div>
                    <div className="space-y-1">
                      <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider block print:text-black">
                        Recommendation #{idx + 1}
                      </span>
                      <p className="text-sm text-slate-200 font-medium leading-relaxed print:text-black">
                        {rec}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* RIGHT COLUMN: PERSISTENT NATURAL LANGUAGE CHAT DRAWER */}
          <div className="lg:col-span-1 sticky top-20 print:hidden">
            <div className="bg-slate-900/90 border border-slate-800 rounded-3xl shadow-2xl overflow-hidden flex flex-col h-[750px] max-h-[85vh]">
              
              {/* Chat Panel Header */}
              <div className="p-4 bg-slate-950/90 border-b border-slate-800 flex items-center justify-between">
                <div className="flex items-center space-x-2.5">
                  <div className="p-2 bg-teal-500/10 border border-teal-500/30 rounded-xl text-teal-400">
                    <MessageSquare className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-slate-100">DataSense Q&A Assistant</h3>
                    <p className="text-xs text-slate-400">Natural language code & inline charts</p>
                  </div>
                </div>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" title="Ready"></span>
              </div>

              {/* Chat Message List */}
              <div className="flex-1 p-4 overflow-y-auto space-y-4">
                {chatHistory.length === 0 ? (
                  <div className="text-center py-12 space-y-3">
                    <Bot className="w-10 h-10 text-slate-600 mx-auto" />
                    <p className="text-xs text-slate-400 max-w-[200px] mx-auto">
                      Ask questions like <span className="text-teal-300 font-mono">"what is the average temperature"</span> or <span className="text-teal-300 font-mono">"show rows where status is fault"</span>.
                    </p>
                  </div>
                ) : (
                  chatHistory.map((item, idx) => (
                    <div key={idx} className="space-y-3">
                      
                      {/* User Question */}
                      <div className="flex items-start space-x-2 justify-end">
                        <div className="bg-teal-600/90 text-white p-3 rounded-2xl rounded-tr-none text-xs max-w-[85%] shadow-md">
                          <p className="font-medium">{item.question}</p>
                        </div>
                        <div className="p-1.5 bg-teal-500/20 text-teal-300 rounded-lg">
                          <User className="w-3.5 h-3.5" />
                        </div>
                      </div>

                      {/* AI Answer Response */}
                      <div className="flex items-start space-x-2">
                        <div className="p-1.5 bg-slate-800 text-teal-400 rounded-lg mt-1">
                          <Bot className="w-3.5 h-3.5" />
                        </div>
                        <div className="bg-slate-950 border border-slate-800 text-slate-200 p-3 rounded-2xl rounded-tl-none text-xs max-w-[90%] shadow-md space-y-1">
                          {item.loading ? (
                            <div className="flex items-center space-x-2 text-slate-400">
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              <span>Executing calculation...</span>
                            </div>
                          ) : (
                            <>
                              <p className="leading-relaxed font-medium">{item.answer_text}</p>
                              <InlineChatResult chartConfig={item.chart_config} data={item.data} />
                            </>
                          )}
                        </div>
                      </div>

                    </div>
                  ))
                )}

                <div ref={chatEndRef} />
              </div>

              {/* Chat Input Form */}
              <form onSubmit={handleSendQuery} className="p-3 bg-slate-950 border-t border-slate-800 flex items-center space-x-2">
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask a question about this data..."
                  disabled={querying}
                  className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-teal-500 transition-colors disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!question.trim() || querying}
                  className="p-2.5 bg-teal-500 hover:bg-teal-400 active:bg-teal-600 text-slate-950 font-bold rounded-xl transition-colors disabled:opacity-40"
                >
                  {querying ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
              </form>

            </div>
          </div>

        </div>
      )}

    </div>
  )
}

import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listDatasets } from '../api'
import {
  FileSpreadsheet,
  UploadCloud,
  ArrowRight,
  Database,
  RefreshCw,
  Sparkles,
  Clock,
  CheckCircle2,
  Loader2,
  Server,
} from 'lucide-react'

export default function Dashboard() {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [isWakingUp, setIsWakingUp] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const fetchDatasetsWithRetry = async (retryCount = 0) => {
    setLoading(true)
    setError('')

    // Show waking up notice after 2 seconds
    const timer = setTimeout(() => {
      setIsWakingUp(true)
    }, 2000)

    try {
      const data = await listDatasets()
      setDatasets(data || [])
      setError('') // Clear any error on success
    } catch (err) {
      console.warn(`Connection attempt ${retryCount + 1} failed, retrying...`, err)
      
      // Auto-retry up to 3 times for Render cold start
      if (retryCount < 3) {
        setIsWakingUp(true)
        await new Promise((resolve) => setTimeout(resolve, 4000))
        return fetchDatasetsWithRetry(retryCount + 1)
      }

      setError('Unable to connect to backend server. Please click Retry below.')
    } finally {
      clearTimeout(timer)
      setLoading(false)
      setIsWakingUp(false)
    }
  }

  useEffect(() => {
    fetchDatasetsWithRetry()
  }, [])

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      
      {/* Top Banner & Action */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-gradient-to-r from-slate-900 via-slate-900/90 to-slate-800/80 p-6 rounded-2xl border border-slate-800 shadow-xl backdrop-blur-xl">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-100 tracking-tight flex items-center gap-2">
            Industrial Datasets & Analytics
            <Sparkles className="w-5 h-5 text-teal-400" />
          </h1>
          <p className="text-sm text-slate-400 max-w-xl">
            Upload plant telemetry, sensor streams, or equipment logs for instant profiling, anomaly detection, and AI report generation.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => fetchDatasetsWithRetry(0)}
            disabled={loading}
            className="p-2.5 bg-slate-800 hover:bg-slate-700 active:bg-slate-900 border border-slate-700 text-slate-300 rounded-xl transition-colors disabled:opacity-50"
            title="Refresh datasets"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <Link
            to="/upload"
            className="inline-flex items-center space-x-2 bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-slate-950 font-semibold px-5 py-2.5 rounded-xl shadow-lg shadow-teal-500/20 transition-all hover:scale-[1.02]"
          >
            <UploadCloud className="w-5 h-5" />
            <span>Upload New Dataset</span>
          </Link>
        </div>
      </div>

      {/* Persistent Connection Error State (Only shown if ALL retries fail) */}
      {error && !loading && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={() => fetchDatasetsWithRetry(0)}
            className="text-xs bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 px-4 py-1.5 rounded-lg border border-rose-500/40 font-semibold transition-colors"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Loading & Connection State */}
      {loading ? (
        <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-12 text-center space-y-6">
          <div className="inline-flex p-4 bg-teal-500/10 border border-teal-500/30 rounded-3xl text-teal-400">
            <Loader2 className="w-8 h-8 animate-spin" />
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-bold text-slate-100">
              Connecting to DataSense AI Engine...
            </h3>
            <p className="text-xs text-teal-400/90 max-w-md mx-auto font-mono">
              {isWakingUp
                ? '⚡ Server instance is booting up (Render Free Tier wakeup 15-30s)...'
                : 'Initializing secure API connection...'}
            </p>
          </div>
          <div className="w-48 h-1.5 bg-slate-800 rounded-full mx-auto overflow-hidden">
            <div className="w-full h-full bg-gradient-to-r from-teal-500 to-cyan-400 animate-pulse"></div>
          </div>
        </div>
      ) : datasets.length === 0 ? (
        /* Clean Empty State - NO RED ERROR BANNER */
        <div className="text-center py-16 bg-slate-900/40 border border-slate-800/80 rounded-3xl p-8 space-y-5">
          <div className="inline-flex p-4 bg-slate-800/60 border border-slate-700/60 rounded-2xl text-teal-400">
            <Database className="w-12 h-12" />
          </div>
          <div className="space-y-1">
            <h3 className="text-xl font-bold text-slate-200">No Datasets Uploaded Yet</h3>
            <p className="text-slate-400 text-sm max-w-md mx-auto">
              Get started by uploading your first CSV, XLSX, or JSON telemetry dataset to generate automated AI insights.
            </p>
          </div>
          <div>
            <Link
              to="/upload"
              className="inline-flex items-center space-x-2 bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-slate-950 font-bold px-6 py-3 rounded-xl shadow-lg shadow-teal-500/20 transition-all hover:scale-105"
            >
              <UploadCloud className="w-5 h-5" />
              <span>Upload Your First Dataset</span>
            </Link>
          </div>
        </div>
      ) : (
        /* Dataset Cards Grid */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {datasets.map((dataset) => (
            <div
              key={dataset.dataset_id}
              className="group bg-slate-900/80 hover:bg-slate-900 border border-slate-800 hover:border-teal-500/40 rounded-2xl p-6 shadow-xl hover:shadow-2xl hover:shadow-teal-500/5 transition-all flex flex-col justify-between"
            >
              <div className="space-y-4">
                {/* Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center space-x-3">
                    <div className="p-2.5 bg-teal-500/10 border border-teal-500/20 rounded-xl text-teal-400 group-hover:scale-110 transition-transform">
                      <FileSpreadsheet className="w-6 h-6" />
                    </div>
                    <div className="overflow-hidden">
                      <h3
                        className="text-base font-bold text-slate-100 truncate group-hover:text-teal-300 transition-colors"
                        title={dataset.filename}
                      >
                        {dataset.filename}
                      </h3>
                      <span className="text-xs text-slate-500 font-mono">
                        ID: {dataset.dataset_id.slice(0, 8)}...
                      </span>
                    </div>
                  </div>

                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider ${
                      dataset.status === 'report_generated'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                        : 'bg-teal-500/10 text-teal-400 border border-teal-500/30'
                    }`}
                  >
                    <CheckCircle2 className="w-3 h-3" />
                    {dataset.status === 'report_generated' ? 'Reported' : 'Profiled'}
                  </span>
                </div>

                {/* Metrics Stats */}
                <div className="grid grid-cols-2 gap-3 p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl">
                  <div>
                    <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold block">
                      Rows
                    </span>
                    <span className="text-lg font-bold font-mono text-slate-200">
                      {dataset.row_count ? dataset.row_count.toLocaleString() : '0'}
                    </span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold block">
                      Columns
                    </span>
                    <span className="text-lg font-bold font-mono text-teal-400">
                      {dataset.col_count ? dataset.col_count.toLocaleString() : '0'}
                    </span>
                  </div>
                </div>

                {/* Timestamp */}
                {dataset.created_at && (
                  <div className="flex items-center space-x-1.5 text-xs text-slate-500">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Uploaded: {new Date(dataset.created_at).toLocaleString()}</span>
                  </div>
                )}
              </div>

              {/* Action Button */}
              <div className="pt-5 mt-2 border-t border-slate-800/80">
                <button
                  onClick={() => navigate(`/report/${dataset.dataset_id}`)}
                  className="w-full flex items-center justify-center space-x-2 bg-slate-800 hover:bg-teal-600/20 active:bg-slate-900 text-slate-200 hover:text-teal-300 border border-slate-700 hover:border-teal-500/40 font-medium py-2.5 rounded-xl transition-all group-hover:shadow-md"
                >
                  <span>View Report & Chat</span>
                  <ArrowRight className="w-4 h-4 text-teal-400 group-hover:translate-x-1 transition-transform" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

    </div>
  )
}

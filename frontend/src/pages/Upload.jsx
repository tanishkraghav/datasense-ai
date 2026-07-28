import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { generateReport, uploadDataset } from '../api'
import {
  UploadCloud,
  FileSpreadsheet,
  AlertCircle,
  Loader2,
  Brain,
  CheckCircle2,
  ArrowLeft,
} from 'lucide-react'

export default function Upload() {
  const [file, setFile] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [status, setStatus] = useState('idle') // 'idle' | 'uploading' | 'generating' | 'success' | 'error'
  const [statusMsg, setStatusMsg] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const navigate = useNavigate()

  const ALLOWED_EXTENSIONS = ['.csv', '.xlsx', '.xls', '.json']

  const validateFile = (selectedFile) => {
    if (!selectedFile) return false
    const ext = '.' + selectedFile.name.split('.').pop().toLowerCase()
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setErrorMsg(`Unsupported file type '${ext}'. Please upload a .csv, .xlsx, or .json file.`)
      return false
    }
    if (selectedFile.size > 50 * 1024 * 1024) {
      setErrorMsg('File size exceeds maximum allowed limit of 50 MB.')
      return false
    }
    setErrorMsg('')
    return true
  }

  const handleDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0]
      if (validateFile(droppedFile)) {
        setFile(droppedFile)
        processUploadAndReport(droppedFile)
      }
    }
  }

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0]
      if (validateFile(selectedFile)) {
        setFile(selectedFile)
        processUploadAndReport(selectedFile)
      }
    }
  }

  const processUploadAndReport = async (targetFile) => {
    setStatus('uploading')
    setStatusMsg('Uploading and parsing dataset...')
    setErrorMsg('')

    try {
      // 1. Upload dataset
      const uploadRes = await uploadDataset(targetFile)
      const datasetId = uploadRes.dataset_id

      // 2. Generate report
      setStatus('generating')
      setStatusMsg('Generating AI analysis report with LangGraph...')
      await generateReport(datasetId)

      // 3. Navigate to report page
      setStatus('success')
      setStatusMsg('Report generated successfully! Redirecting...')
      setTimeout(() => {
        navigate(`/report/${datasetId}`)
      }, 500)
    } catch (err) {
      console.error(err)
      setStatus('error')
      const msg = err.response?.data?.detail || err.message || 'An error occurred during upload/report generation.'
      setErrorMsg(msg)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-10 space-y-6">
      
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/')}
          className="flex items-center space-x-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Dashboard</span>
        </button>

        <span className="text-xs text-slate-500 font-mono">Max File Size: 50MB</span>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-3xl p-8 shadow-2xl space-y-8">
        
        {/* Title */}
        <div className="text-center space-y-2">
          <div className="inline-flex p-3 bg-teal-500/10 border border-teal-500/20 rounded-2xl text-teal-400 mb-2">
            <UploadCloud className="w-8 h-8" />
          </div>
          <h2 className="text-3xl font-extrabold text-slate-100 tracking-tight">
            Upload Industrial Telemetry Dataset
          </h2>
          <p className="text-sm text-slate-400 max-w-lg mx-auto">
            Upload your CSV, Excel, or JSON files. DataSense AI will automatically profile the dataset, detect 3-sigma anomalies, and produce a structured operational report.
          </p>
        </div>

        {/* Error Alert */}
        {errorMsg && (
          <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-sm flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-semibold block">Upload Failed</span>
              <p className="text-xs text-rose-300/90">{errorMsg}</p>
            </div>
          </div>
        )}

        {/* Drag & Drop Box */}
        {status === 'idle' || status === 'error' ? (
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`relative border-2 border-dashed rounded-2xl p-10 text-center transition-all cursor-pointer ${
              dragActive
                ? 'border-teal-400 bg-teal-500/10 scale-[1.01]'
                : 'border-slate-700/80 hover:border-teal-500/50 bg-slate-950/60 hover:bg-slate-950/80'
            }`}
          >
            <input
              type="file"
              accept=".csv,.xlsx,.xls,.json"
              onChange={handleFileSelect}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />

            <div className="space-y-4 pointer-events-none">
              <div className="inline-flex p-4 bg-slate-800/80 rounded-2xl text-slate-300 border border-slate-700">
                <FileSpreadsheet className="w-10 h-10 text-teal-400" />
              </div>

              <div>
                <p className="text-base font-semibold text-slate-200">
                  Drag and drop your file here, or{' '}
                  <span className="text-teal-400 underline underline-offset-4">browse</span>
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Supports CSV, XLSX, XLS, and JSON (up to 500,000 rows)
                </p>
              </div>

              {file && (
                <div className="inline-flex items-center space-x-2 px-3 py-1.5 bg-slate-800 rounded-lg text-xs text-slate-300 border border-slate-700">
                  <FileSpreadsheet className="w-4 h-4 text-teal-400" />
                  <span className="font-mono">{file.name}</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Loading & Progress States */
          <div className="border border-slate-800 bg-slate-950/80 rounded-2xl p-12 text-center space-y-6">
            <div className="inline-flex relative">
              <div className="p-5 bg-teal-500/10 border border-teal-500/30 rounded-3xl text-teal-400">
                {status === 'uploading' && <Loader2 className="w-10 h-10 animate-spin text-teal-400" />}
                {status === 'generating' && <Brain className="w-10 h-10 animate-bounce text-cyan-400" />}
                {status === 'success' && <CheckCircle2 className="w-10 h-10 text-emerald-400" />}
              </div>
            </div>

            <div className="space-y-2">
              <h3 className="text-xl font-bold text-slate-100">{statusMsg}</h3>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                {status === 'uploading' && 'Parsing rows, validating schema, and creating cached data structures...'}
                {status === 'generating' && 'LangGraph nodes are analyzing schema, correlations, anomalies, and recommendations...'}
                {status === 'success' && 'Redirecting to interactive report workspace...'}
              </p>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-slate-800 rounded-full h-2 max-w-md mx-auto overflow-hidden">
              <div
                className={`h-full transition-all duration-700 ${
                  status === 'uploading'
                    ? 'w-1/3 bg-teal-500'
                    : status === 'generating'
                    ? 'w-4/5 bg-cyan-400 animate-pulse'
                    : 'w-full bg-emerald-400'
                }`}
              ></div>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}

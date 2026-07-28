import { Link, useLocation } from 'react-router-dom'

import { Brain, LayoutDashboard, UploadCloud } from 'lucide-react'

export default function Navbar() {
  const location = useLocation()

  const isActive = (path) => location.pathname === path

  return (
    <header className="sticky top-0 z-50 bg-slate-900/90 border-b border-slate-800/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand Logo */}
        <Link to="/" className="flex items-center space-x-3 group">
          <div className="p-2 bg-gradient-to-tr from-teal-500/20 via-cyan-500/20 to-indigo-500/20 border border-teal-500/30 rounded-xl text-teal-400 group-hover:scale-105 transition-transform">
            <Brain className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-teal-400 via-cyan-300 to-indigo-400 bg-clip-text text-transparent">
              DataSense AI
            </span>
            <span className="hidden sm:inline-block ml-2 text-xs font-medium text-slate-400 border border-slate-700/60 px-2 py-0.5 rounded-md">
              Industrial Demo
            </span>
          </div>
        </Link>

        {/* Nav Links */}
        <nav className="flex items-center space-x-2">
          <Link
            to="/"
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
              isActive('/')
                ? 'bg-slate-800 text-teal-400 border border-teal-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <LayoutDashboard className="w-4 h-4" />
            <span>Dashboard</span>
          </Link>

          <Link
            to="/upload"
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
              isActive('/upload')
                ? 'bg-teal-600 text-white shadow-lg shadow-teal-600/20'
                : 'bg-teal-600/90 hover:bg-teal-500 text-white'
            }`}
          >
            <UploadCloud className="w-4 h-4" />
            <span>Upload Dataset</span>
          </Link>
        </nav>

      </div>
    </header>
  )
}

# DataSense AI

DataSense AI is a full-stack personal learning and demo platform combining AI-driven analytics, data profiling, vector database indexing, and interactive data visualization.

> [!NOTE]
> This application is built as a demo tool without authentication (no login, JWT, or user tables).

---

## 📁 Project Structure

```
datasense-ai/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application & endpoints
│   │   ├── routers/        # API route controllers
│   │   ├── services/       # Core business & AI logic
│   │   ├── models/         # Pydantic schemas & data models
│   │   └── core/           # Config, database, & environment settings
│   ├── requirements.txt    # Python dependencies
│   └── .env.example        # Environment variable template
├── frontend/
│   (React + Vite app with Tailwind CSS, React Router, Recharts, Lucide icons)
└── README.md
```

---

## 🚀 Getting Started

### 1. Backend Setup (FastAPI)

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

# Run FastAPI server on http://localhost:8000
uvicorn app.main:app --reload --port 8000
```

Verify backend health check at: [http://localhost:8000/health](http://localhost:8000/health)

---

## 2. Frontend Setup (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server will launch at [http://localhost:5173](http://localhost:5173).

---

## 🛠️ Stack & Technologies

- **Backend**: FastAPI, Python 3.11+, Pandas, NumPy, Scikit-Learn, YData Profiling, LangGraph, LangChain-Groq, ChromaDB, Supabase-py.
- **Frontend**: React, Vite, Tailwind CSS, React Router DOM, Recharts, Axios, Lucide React icons.

import uvicorn

if __name__ == "__main__":
    print("Starting FastAPI Uvicorn server on http://0.0.0.0:8000 (accessible via localhost:8000 and 127.0.0.1:8000)...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)

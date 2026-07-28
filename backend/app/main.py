from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import datasets

app = FastAPI(title="DataSense AI API")

# Enable CORS for frontend clients (local & deployed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register datasets router
app.include_router(datasets.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}

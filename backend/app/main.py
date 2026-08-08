import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .database import Base, engine
from .routers import members

load_dotenv()

app = FastAPI(title="MACT Cooperative Ledger API", version="0.1.0")

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Creates tables if they don't exist yet. Fine for early development;
# switch to Alembic migrations once the schema stabilizes.
Base.metadata.create_all(bind=engine)

app.include_router(members.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}

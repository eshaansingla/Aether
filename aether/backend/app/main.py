from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routes import router
from app.config import ALLOWED_ORIGIN, OUTPUT_DIR
from app.core.database import initialize
from app.tools.productivity import start_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    start_scheduler()
    yield

app = FastAPI(title="AETHER Local AI Assistant", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[ALLOWED_ORIGIN,"http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["GET","POST"], allow_headers=["*"])
@app.get("/health")
async def health():
    return {"status":"online","application":"AETHER","version":"2.0.0","mode":"local"}
app.include_router(router)
# Generated documents/screenshots live only under OUTPUT_DIR; this serves them read-only so
# the desktop UI can offer a real "Download" link, the way a cloud chatbot would.
app.mount("/files", StaticFiles(directory=str(OUTPUT_DIR)), name="files")

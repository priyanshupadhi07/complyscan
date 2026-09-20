"""
ComplyScan - FastAPI Application
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 1. Ensure Python can find root and backend modules across local dev and Vercel
backend_dir = Path(__file__).resolve().parent
root_dir = backend_dir.parent

for path in (str(backend_dir), str(root_dir)):
    if path not in sys.path:
        sys.path.append(path)

# 2. Load .env whether running from repository root or inside backend/
env_path_backend = backend_dir / ".env"
env_path_root = root_dir / ".env"

if env_path_backend.exists():
    load_dotenv(dotenv_path=env_path_backend)
elif env_path_root.exists():
    load_dotenv(dotenv_path=env_path_root)
else:
    load_dotenv()

# 3. Dynamic imports supporting both direct package runs and Vercel root runs
try:
    from backend.database import create_tables
    from backend.routes.scans import router as scans_router
    from backend.routes.dashboard import router as dashboard_router
    from backend.routes.reports import router as reports_router
except ImportError:
    try:
        from database import create_tables
        from routes.scans import router as scans_router
        from routes.dashboard import router as dashboard_router
        from routes.reports import router as reports_router
    except ImportError:
        # Fallback in case your friend named it 'scan' instead of 'scans'
        from database import create_tables
        from routes.scan import router as scans_router
        from routes.dashboard import router as dashboard_router
        from routes.reports import router as reports_router

# 4. Initialize FastAPI Application
app = FastAPI(
    title="ComplyScan API",
    description="Packaged Commodity Label Compliance Checker",
    version="1.0"
)

# 5. Enable CORS for local ports (3000, 5500, 8000) and Vercel domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 6. Initialize database tables safely
try:
    create_tables()
except Exception as e:
    print(f"[Startup Warning] Database table creation skipped/failed: {e}")

# 7. Mount routers with dual-prefix support (both /api/... for Vercel rewrites and direct calls)
app.include_router(scans_router, prefix="/api")
app.include_router(scans_router)

app.include_router(dashboard_router, prefix="/api")
app.include_router(dashboard_router)

app.include_router(reports_router, prefix="/api")
app.include_router(reports_router)

# 8. Health check endpoints
@app.get("/")
@app.get("/api")
def health_check():
    return {
        "status": "ok",
        "service": "ComplyScan API",
        "message": "ComplyScan backend is running"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
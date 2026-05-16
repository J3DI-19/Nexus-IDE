from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api import scan, file, prompt, terminal, settings
from utils.security import set_project_root
from pydantic import BaseModel

app = FastAPI(title="Nexus IDE Backend")

class SetRootRequest(BaseModel):
    path: str

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from context_engine.core.pipeline import pipeline

@app.post("/set-root")
def update_root(request: SetRootRequest):
    set_project_root(request.path)
    # Initialize Context Engine
    try:
        pipeline.initialize_project(request.path)
        print(f"[ContextEngine] Initialized for {request.path}")
    except Exception as e:
        print(f"[ContextEngine] Failed to initialize: {e}")
        raise HTTPException(status_code=500, detail=f"Context engine initialization failed: {e}")
        
    return {"status": "success", "root": request.path}

# Include routers
app.include_router(scan.router)
app.include_router(file.router)
app.include_router(prompt.router)
app.include_router(terminal.router)
app.include_router(settings.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

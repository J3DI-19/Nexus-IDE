from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import scan, file

app = FastAPI(title="Nexus IDE Backend")

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(scan.router)
app.include_router(file.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)

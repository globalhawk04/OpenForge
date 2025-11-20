#
# FILE: app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routers import auth, projects, downloads

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (For dev/proto simplicity)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Autonomous Drone Architect", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
# app.include_router(projects.router) # Uncomment once file populated
# app.include_router(downloads.router) # Uncomment once file populated

@app.get("/")
async def root():
    return {"message": "Drone Architect System Online"}
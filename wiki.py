import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from logging import INFO

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.api.chat import router
from src.api.sync import router as sync_router
from src.api.research import router as research_router

from src.services.graphiti.index import init as graphiti_init
from src.services.sync.scheduler import start_sync_scheduler, stop_sync_scheduler

# Configure logging
logging.basicConfig(
    level=INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    logger.info("Starting up FWTX NextGen Wiki API")
    logger.info("--- Application Settings ---")
    logger.info(f"Allowed Origins: {settings.ALLOWED_ORIGINS if settings.ALLOWED_ORIGINS else '[Not Set - Allowing all by default in middleware]'}")
    logger.info(f"Docs Enabled: {settings.DOCS_ENABLED}")
    logger.info(f"API Key: {'Set' if settings.API_KEY else 'Not Set - Authentication Disabled'}")
    logger.info(f"OpenAI API Base: {settings.OPENAI_API_BASE}")
    logger.info(f"OpenAI API Key: {'Set' if settings.OPENAI_API_KEY else 'Not Set'}")
    logger.info(f"OpenAI Model: {settings.OPENAI_MODEL}")
    logger.info("--------------------------")

    if not settings.API_KEY:
        logger.warning("API_KEY not set in environment. Authentication is disabled.")
    
    # Initialize Graphiti knowledge graph
    try:
        logger.info("Initializing Graphiti knowledge graph...")
        # Check if we should load initial data
        load_initial_data = os.getenv("LOAD_INITIAL_DATA", "false").lower() == "true"
        sync_mode = os.getenv("SYNC_MODE", "initial")  # 'initial' or 'live'
        
        # Run initialization in a background task to not block startup
        asyncio.create_task(initialize_graphiti(load_initial_data, sync_mode))
        logger.info(f"Graphiti initialization started in background (mode: {sync_mode})")
    except Exception as e:
        logger.error(f"Failed to start Graphiti initialization: {e}")
    
    # Start sync scheduler if enabled
    if os.getenv("ENABLE_SYNC_SCHEDULER", "false").lower() == "true":
        try:
            logger.info("Starting data sync scheduler...")
            start_sync_scheduler()
            logger.info("Data sync scheduler started")
        except Exception as e:
            logger.error(f"Failed to start sync scheduler: {e}")
    
    yield
    
    # Shutdown event
    logger.info("Shutting down FWTX Wiki API")
    
    # Stop sync scheduler
    try:
        stop_sync_scheduler()
    except Exception as e:
        logger.error(f"Error stopping sync scheduler: {e}")


async def initialize_graphiti(load_initial_data: bool, sync_mode: str = "initial"):
    """Background task to initialize Graphiti."""
    try:
        await graphiti_init(load_initial_data_flag=load_initial_data, sync_mode=sync_mode)
        logger.info("Graphiti initialization completed successfully")
        
        # If initial data was loaded, log some statistics
        if load_initial_data:
            logger.info(f"Initial data loaded using {sync_mode} mode")
    except Exception as e:
        logger.error(f"Graphiti initialization failed: {e}")
        # Continue running even if initialization fails
        # The app can still serve static files and handle basic requests

# Create FastAPI app
app = FastAPI(
    title="FWTX Wiki API",
    description="API for FWTX Wiki",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()] if settings.ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)
app.include_router(sync_router)
app.include_router(research_router)

# Mount static files
app.mount("/", StaticFiles(directory="client", html=True), name="static")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("wiki:app", host="0.0.0.0", port=8001, reload=True)


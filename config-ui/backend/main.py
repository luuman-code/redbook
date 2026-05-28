"""FastAPI application entry point"""
import os
import sys

# Load .env file
from dotenv import load_dotenv
load_dotenv()

# Add redbook root to path for studio imports
redbook_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if redbook_root not in sys.path:
    sys.path.insert(0, redbook_root)

# Add backend directory to path for config_service imports
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
import importlib.util
import logging

# Initialize Sentry if DSN is provided
try:
    from studio.api.sentry import init_sentry
    init_sentry()
except Exception as e:
    print(f"Sentry initialization failed (may not be installed): {e}")

logger = logging.getLogger("studio")

# Dynamically import api.config to avoid package-relative import issues
spec = importlib.util.spec_from_file_location("config_module", os.path.join(os.path.dirname(__file__), "api", "config.py"))
config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)

from config_service import ConfigService

app = FastAPI(title="小红书 Agent 配置中心")

# Global exception handler middleware
@app.middleware("http")
async def global_exception_handler(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": str(e) if os.getenv("DEBUG") else None,
                "request_id": request.state.request_id if hasattr(request.state, 'request_id') else None
            }
        )

# CORS config - from environment variable
cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
if not cors_origins:
    cors_origins = ["http://localhost:5178", "http://localhost:8080"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter integration
try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from studio.api.rate_limit import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    print("Rate limiter 已注册")
except ImportError as e:
    print(f"Rate limiter 导入失败 (可能未安装): {e}")

# Include config routers
app.include_router(config_module.router, prefix="/api/config")

# Include studio routers
try:
    from studio.api.routes import router as studio_router
    app.include_router(studio_router)
    print("Studio 路由已注册")
except Exception as e:
    print(f"注册 Studio 路由失败: {e}")

# Include canvas routers
try:
    from studio.api.canvas_routes import router as canvas_router
    app.include_router(canvas_router)
    print("Canvas 路由已注册")
except Exception as e:
    print(f"注册 Canvas 路由失败: {e}")


# Include auth routers
from studio.api.auth import router as auth_router
app.include_router(auth_router)

# Include log routers
try:
    from api.log_routes import router as log_router
    app.include_router(log_router)
    print("Log 路由已注册")
except Exception as e:
    print(f"注册 Log 路由失败: {e}")

from datetime import datetime

@app.get("/api/health")
async def health_check():
    """Detailed health check with service status"""
    services = {}

    # Database check
    db_status = "unhealthy"
    try:
        from studio.db.connection import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)[:50]}"

    # Redis check
    redis_status = "disabled"
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis
            r = redis.from_url(redis_url)
            r.ping()
            redis_status = "healthy"
        except Exception as e:
            redis_status = f"unhealthy: {str(e)[:50]}"

    # ChromaDB check
    chroma_status = "disabled"
    chroma_host = os.getenv("CHROMA_HOST")
    if chroma_host:
        try:
            import chromadb
            client = chromadb.Client()
            client.heartbeat()
            chroma_status = "healthy"
        except Exception as e:
            chroma_status = f"unhealthy: {str(e)[:50]}"

    overall = "healthy" if db_status == "healthy" else "degraded"

    return {
        "status": overall,
        "services": {
            "database": db_status,
            "redis": redis_status,
            "chromadb": chroma_status
        }
    }


@app.get("/api/live")
async def liveness():
    """Kubernetes liveness probe"""
    return {"status": "alive"}


@app.get("/api/ready")
async def readiness():
    """Kubernetes readiness probe"""
    # Check if critical services are ready
    try:
        from studio.db.connection import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except:
        return {"status": "not ready"}, 503


# Initialize config service on startup
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化配置服务"""
    ConfigService()

    # Mount static files for studio content (images, videos, audio)
    import os
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "studio")
    if os.path.exists(data_dir):
        app.mount("/static/studio", StaticFiles(directory=data_dir), name="studio_static")
        print(f"静态文件服务已挂载: /static/studio -> {data_dir}")
    else:
        print(f"警告: 静态文件目录不存在: {data_dir}")

    # Mount materials upload directory for direct access
    materials_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "studio", "materials")
    if os.path.exists(materials_dir):
        app.mount("/api/studio/materials", StaticFiles(directory=materials_dir), name="materials_static")
        print(f"素材目录静态文件服务已挂载: /api/studio/materials -> {materials_dir}")
    else:
        # Create the directory if it doesn't exist
        os.makedirs(materials_dir, exist_ok=True)
        app.mount("/api/studio/materials", StaticFiles(directory=materials_dir), name="materials_static")
        print(f"素材目录已创建并挂载: /api/studio/materials -> {materials_dir}")


# Studio API 集成
@app.on_event("startup")
async def init_studio():
    """初始化 Studio 模块"""
    try:
        # 导入 studio 模块
        from studio.api.routes import set_session_store, set_orchestrator
        from studio.core.orchestrator import Orchestrator
        from agent import AgentConfigService, GatewayFactory

        # 初始化配置服务
        config_service = AgentConfigService()

        # 初始化网关
        llm_gateway = GatewayFactory.get_gateway("llm", config_service)
        vision_gateway = GatewayFactory.get_gateway("vision", config_service)
        image_gateway = GatewayFactory.get_gateway("image_generation", config_service)
        tts_gateway = GatewayFactory.get_gateway("tts", config_service)
        video_gateway = GatewayFactory.get_gateway("video", config_service)

        # 初始化记忆管理器
        memory_manager = None
        try:
            from memory import MemoryManager
            memory_manager = MemoryManager(
                user_id="default",
                chroma_persist_dir="data/memory/chroma"
            )
            print("记忆模块初始化完成")
        except Exception as e:
            print(f"记忆模块初始化失败: {e}")

        # 初始化会话存储（使用单例）
        from studio.storage.session_store import get_session_store
        session_store = get_session_store()

        # 初始化 Orchestrator
        orchestrator = Orchestrator(
            llm_gateway=llm_gateway,
            vision_gateway=vision_gateway,
            image_gateway=image_gateway,
            tts_gateway=tts_gateway,
            video_gateway=video_gateway,
            memory_manager=memory_manager,
            config_service=config_service,
        )

        # 注入到 routes
        set_session_store(session_store)
        set_orchestrator(orchestrator)

        print("Studio 模块初始化完成")
    except Exception as e:
        print(f"Studio 模块初始化失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

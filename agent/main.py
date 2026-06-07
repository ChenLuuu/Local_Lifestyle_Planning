"""FastAPI application entry point."""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.routers.auth import router as auth_router
from agent.routers.collab import router as collab_router
from agent.routers.collect import router as collect_router
from agent.routers.deals import router as deals_router
from agent.routers.execute import router as execute_router
from agent.routers.plan import router as plan_router
from agent.routers.profile import router as profile_router
from agent.routers.share import router as share_router
from agent.routers.swap import router as swap_router

app: FastAPI = FastAPI(title="Meituan Local Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(collect_router)
app.include_router(plan_router)
app.include_router(swap_router)
app.include_router(execute_router)
app.include_router(collab_router)
app.include_router(deals_router)
app.include_router(share_router)
app.include_router(profile_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

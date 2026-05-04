import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import models  # noqa: F401 — register ORM mappers before create_all
import controllers
from database import (
    BaseModel,
    VectorBase,
    engine,
    engine_oip,
    session_vector,
    vector_engine,
)


async def _maybe_seed_oip_catalogue() -> None:
    raw = os.getenv("AUTO_SEED_OIP_EMBEDDINGS", "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return
    from services.file_service import seed_oip_embeddings_from_repo_file

    db = session_vector()
    try:
        n = await seed_oip_embeddings_from_repo_file(db)
        print(f"OIP catalogue embeddings seeded: {n} new row(s).")
    finally:
        db.close()


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        engine.connect()
        print("BCD/Salesforce execution DB connected")

        try:
            with vector_engine.begin() as vc:
                vc.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as ext_exc:
            print(f"embeddings DB: CREATE EXTENSION vector skipped ({ext_exc})")
        VectorBase.metadata.create_all(bind=vector_engine)
        vector_engine.connect()
        print("Vector catalogue DB connected")

        BaseModel.metadata.create_all(bind=engine)

        if engine_oip is not None:
            engine_oip.connect()
            print("OIP execution DB connected")

        await _maybe_seed_oip_catalogue()
        app.include_router(controllers.file_router, prefix="/file")
        app.include_router(controllers.agent_router, prefix="/agent")
        app.include_router(controllers.insights_router, prefix="/insights")
    except Exception as e:
        print(e)

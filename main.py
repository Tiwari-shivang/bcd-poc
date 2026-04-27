from fastapi import FastAPI
from database import engine, BaseModel
import models
import controllers
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.on_event('startup')
async def startup():
    try:
        engine.connect()
        print('Db connected')
        BaseModel.metadata.create_all(bind=engine)
        app.include_router(controllers.file_router, prefix="/file")
        app.include_router(controllers.agent_router, prefix="/agent")
    except Exception as e:
        print(e)
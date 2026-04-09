from fastapi import FastAPI
from database import engine, BaseModel
import models
import controllers

app = FastAPI()
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
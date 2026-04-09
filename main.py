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
    except:
        print("Error connecting db")
from fastapi import FastAPI
from database import engine, BaseModel
import models

app = FastAPI()
@app.on_event('startup')
async def startup():
    try:
        engine.connect()
        print('Db connected')
        BaseModel.metadata.create_all(bind=engine)
    except:
        print("error connecting db!")
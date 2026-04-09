from fastapi import FastAPI
from database import engine

app = FastAPI()
@app.on_event('startup')
async def startup():
    try:
        engine.connect()
        print('Db connected')
    except:
        print("error connecting db!")
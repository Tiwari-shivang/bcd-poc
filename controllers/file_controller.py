from fastapi import APIRouter, Form, UploadFile, File, Depends
from database import get_db
from sqlalchemy.orm import Session
import services

router = APIRouter()

@router.post("/upload")
async def upload_file(key: str=Form(...), description:str=Form(...) ,file: UploadFile = File(...), db:Session=Depends(get_db)):
    file_service = services.FileService()
    response = await file_service.upload_file(file, key, description, db)
    return response
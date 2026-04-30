from fastapi import APIRouter, Form, UploadFile, File, Depends
from sqlalchemy.orm import Session

import services
from database import get_db_vector

router = APIRouter()


@router.post("/upload")
async def upload_file(
    description: str = Form(...),
    file: UploadFile = File(...),
    vector_db: Session = Depends(get_db_vector),
    data_source: str = Form(default="salesforce"),
):
    file_service = services.FileService()
    response = await file_service.upload_file(
        file,
        description,
        vector_db,
        data_source=data_source,
    )
    return response

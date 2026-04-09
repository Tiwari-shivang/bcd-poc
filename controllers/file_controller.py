from fastapi import APIRouter, Form, UploadFile, File, Depends
from database import get_db
from sqlalchemy.orm import Session
from models import EmbeddingModel
import DTOs
import config

router = APIRouter()

@router.post("/upload")
async def upload_file(key: str=Form(...), description:str=Form(...) ,file: UploadFile = File(...), db:Session=Depends(get_db)):
    file_content = await file.read()
    content = file_content.decode("utf-8").split("\n")
    chunks = []
    for c in range(0,len(content), 200):
        chunk = "\n".join(content[c:c+200])
        chunks.append(chunk)
    points=[]
    for chunk in chunks:
        print(chunk)
        embeddings = config.OpenAIClient.embeddings.create(
            model="text-embedding-3-small",
            input=chunk
        )
        data=EmbeddingModel()
        data.data=embeddings.data[0].embedding
        data.description=description
        data.key=key
        data.content=chunk
        db.add(data)
        db.commit()
        response = db.refresh(data)
        points.append(response)
    response=DTOs.UploadResponse(
        message="Uploaded successfully",
        description=description,
        key=key
    )
    return response
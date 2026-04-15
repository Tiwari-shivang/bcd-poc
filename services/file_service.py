from fastapi import UploadFile
from config import OpenAIClient
import models
from sqlalchemy.orm import Session
import DTOs

class FileService:
    async def upload_file(self, file: UploadFile, key: str, description: str, db: Session):
        file_content = await file.read()
        content = file_content.decode("utf-8")
        chunks=[]
        for c in range(0, len(content), 500):
            chunk = "\n".join(content[c:c+500])
            chunks.append(chunk)
        for chunk in chunks:
            vector_data = OpenAIClient.embeddings.create(
                model="text-embedding-3-small",
                input=chunk
            )
            data = models.EmbeddingModel()
            data.data = vector_data.data[0].embedding
            data.content = chunk
            data.key = key
            data.description = description
            db.add(data)
            db.commit()
            db.refresh(data)
        response = DTOs.UploadResponse(
            message="Uploaded successfully",
            description=description,
            key=key
        )
        return response
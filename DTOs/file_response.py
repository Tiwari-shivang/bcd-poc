from pydantic import BaseModel

class UploadResponse(BaseModel):
    message: str
    description: str
    class Config:
        from_attributes: True
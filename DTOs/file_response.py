from pydantic import BaseModel

class UploadResponse(BaseModel):
    message: str
    description: str
    key: str
    class Config:
        from_attributes: True
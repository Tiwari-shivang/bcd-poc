from pydantic import BaseModel
class AgentChatRequest(BaseModel):
    message: str

class AgentChatResponse(BaseModel):
    response: str
    class Config:
        from_attributes:True
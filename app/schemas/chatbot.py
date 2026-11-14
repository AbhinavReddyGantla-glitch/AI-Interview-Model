from pydantic import BaseModel

class ChatbotRequest(BaseModel):
    query: str

class ChatbotResponse(BaseModel):
    query: str
    response: str
    source: str  # "faq" or "gemini"

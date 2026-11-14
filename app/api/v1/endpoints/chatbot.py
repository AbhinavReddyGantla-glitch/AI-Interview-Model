import logging
from fastapi import APIRouter
from app.schemas.chatbot import ChatbotRequest, ChatbotResponse
from app.services.chatbot import handle_chatbot_query, EXPANDED_FAQ_DATA

logger = logging.getLogger("app.api.chatbot")

router = APIRouter()

@router.post("/query", response_model=ChatbotResponse)
def query_assistant(request: ChatbotRequest):
    """
    Exposes the Chatbot support assistant endpoint.
    Routes queries first to the FAQ / guideline engine.
    If not matched, delegates query to Gemini AI.
    """
    logger.info(f"Received chatbot query: '{request.query}'")
    response_text = handle_chatbot_query(request.query)
    
    # Determine the source
    source = "gemini"
    q_lower = request.query.lower().strip()
    for item in EXPANDED_FAQ_DATA:
        if any(kw in q_lower for kw in item["keywords"]):
            source = "faq"
            break
            
    return ChatbotResponse(
        query=request.query,
        response=response_text,
        source=source
    )


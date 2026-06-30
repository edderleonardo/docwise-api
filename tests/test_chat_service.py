# tests/test_chat_service.py
import asyncio
import uuid

from app.db.database import AsyncSessionLocal
from app.services.chat_service import generate_chat_response


async def main():
    # Use a real session ID from your database for testing
    session_id = uuid.UUID("b2cbdd34-ed8b-4000-a5d7-2815c08ee738")
    question = "What is this document about?"

    async with AsyncSessionLocal() as db:
        async for token in generate_chat_response(session_id, question, db):
            print(token, end="", flush=True)
        print()


asyncio.run(main())

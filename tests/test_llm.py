# test_llm.py
import asyncio
from app.core.llm import stream_response


async def main():
    chunks = [
        "The document states that the service costs $100 per month, including all features and support.",
    ]
    question = "What is the monthly cost of the service?"

    async for token in stream_response(question, chunks):
        print(token, end="", flush=True)
    print()


asyncio.run(main())

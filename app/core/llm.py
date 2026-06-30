from google import genai
from app.config import settings

# Configura el cliente una sola vez
client = genai.Client(api_key=settings.gemini_api_key)

SYSTEM_PROMPT = """You are a helpful assistant that answers questions about documents.
Answer based ONLY on the context provided below.
If the answer is not in the context, say "I don't have enough information in the document to answer that."
Be concise and accurate. Answer in the same language as the question."""


def build_prompt(question: str, chunks: list[str]) -> str:
    """
    Build the prompt for the LLM using the question and relevant chunks.
    <context of chunks>
    """
    context = "\n\n---\n\n".join(chunks)

    return f"""{SYSTEM_PROMPT}

Context from the document:
{context}

Question: {question}

Answer:"""


async def stream_response(question, chunks: list[str]):
    """
    Call to Gemini with streaming and make yield of the response in chunks,
    with out waiting for the full response to be generated.
    """
    prompt = build_prompt(question, chunks)

    response = client.models.generate_content_stream(
        model=settings.gemini_model,
        contents=prompt,
    )

    for chunk in response:
        if chunk.text:
            yield chunk.text

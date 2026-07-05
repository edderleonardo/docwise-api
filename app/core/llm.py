from google import genai
from app.config import settings

# Configura el cliente una sola vez
client = genai.Client(api_key=settings.gemini_api_key)

SYSTEM_PROMPT = """You are a helpful assistant that answers questions about documents.
Answer based ONLY on the context provided below.
If the answer is not in the context, say "I don't have enough information in the document to answer that."
Be concise and accurate. Answer in the same language as the question."""

EXPANSION_PROMPT = """Rewrite this question to improve semantic search over a document.
Expand acronyms to their full terms (keeping the acronym too), and add synonyms
for the key concepts. If the question is not in English, append an English
translation. Reply with ONLY the rewritten question, nothing else.

Question: {question}"""


async def expand_query(question: str) -> str:
    """
    Rewrites the user's question so vector search matches the document's
    vocabulary (e.g. "LLM" -> "Large Language Model (LLM)").
    Falls back to the original question on any error — expansion must
    never break the chat.
    """
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=EXPANSION_PROMPT.format(question=question),
        )
        expanded = (response.text or "").strip()
        return expanded or question
    except Exception:
        return question


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
    The async client (client.aio) is required: the sync iterator blocks the
    event loop, so uvicorn buffers every token and flushes them all at once.
    """
    prompt = build_prompt(question, chunks)

    response = await client.aio.models.generate_content_stream(
        model=settings.gemini_model,
        contents=prompt,
    )

    async for chunk in response:
        if chunk.text:
            yield chunk.text

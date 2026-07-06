# test_ingestion.py
import asyncio
from pathlib import Path
from app.core.ingestion import chunk_and_embed

pdf_path = Path.home() / "Downloads" / "propuesta_isi.pdf"
pdf_bytes = pdf_path.read_bytes()

results = chunk_and_embed(pdf_bytes, "propuesta_isi.pdf")

print(f"Total chunks: {len(results)}")
print(f"Embedding dims: {len(results[0]['embedding'])}")
print(f"\nPrimer chunk (primeros 200 chars):")
print(results[0]["content"][:200])
print(f"\nSegundo chunk (primeros 200 chars):")
print(results[1]["content"][:200])

import tempfile
from pathlib import Path

from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter

from app.config import settings
from app.core.embeddings import embed_texts


def chunk_and_embed(pdf_bytes: bytes, filename: str) -> list[dict]:
    """ """
    # 1 save the PDF bytes to a temporary file
    with tempfile.NamedTemporaryFile(
        suffix=".pdf", delete=False, dir="/tmp"
    ) as tmp_file:
        tmp_file.write(pdf_bytes)
        tmp_path = Path(tmp_file.name)

    try:
        # 2 LlamaIndex read the file
        documents = SimpleDirectoryReader(
            input_files=[str(tmp_path)],
        ).load_data()

        # 3 LlamaIndex split the documents into chunks
        splitter = SentenceSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        nodes = splitter.get_nodes_from_documents(documents)
        # 4 Extract the text from the nodes
        texts = [node.text for node in nodes if node.text.strip()]

        if not texts:
            raise ValueError(f"No text extracted from the PDF. from {documents}")

        # 5 sentences-transformers embeddings
        embeddings = embed_texts(texts)
        # 6 return
        return [
            {
                "content": text,
                "embedding": embedding,
                "chunk_index": i,
            }
            for i, (text, embedding) in enumerate(zip(texts, embeddings))
        ]

    finally:
        tmp_path.unlink(missing_ok=True)  # Clean up the temporary file

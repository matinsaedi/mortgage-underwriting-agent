"""Search the Seeling Guide: hybrid search (meaning + keywords), then rerank."""

from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"
COLLECTION = "selling_guide_b3"


@lru_cache(maxsize=1)
def get_vector_store() -> QdrantVectorStore:
    """Open the Qdrant collection built in notebook 02. Loaded once, then reused."""
    return QdrantVectorStore(
        client=QdrantClient(path=str(QDRANT_PATH)),
        collection_name=COLLECTION,
        embedding=HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            encode_kwargs={"normalize_embeddings": True},
        ),
        sparse_embedding=FastEmbedSparse(model_name="Qdrant/bm25"),
        retrieval_mode=RetrievalMode.HYBRID,
        sparse_vector_name="langchain-sparse",
    )


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    """Load the reranker once, then reuse it."""
    return CrossEncoder("BAAI/bge-reranker-base")



def retrieve(question: str, k_candidates: int = 20, top_n: int = 5) -> list[Document]:
    """Two-stage retrieval: hybrid search for candidates, then rerank to the best few"""
    candidates = get_vector_store().similarity_search(question, k=k_candidates)
    scores = get_reranker().predict([(question, d.page_content) for d in candidates])
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    return [d for _, d in ranked[:top_n]]
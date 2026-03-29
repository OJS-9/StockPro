"""
Embedding service using Google Gemini text-embedding-004 (768d).
"""

import os
from typing import List, Optional
from dotenv import load_dotenv

from google import genai

load_dotenv()

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 3072


class EmbeddingService:
    """Service for creating text embeddings using Gemini."""

    def __init__(self, api_key: Optional[str] = None, model: str = EMBEDDING_MODEL):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required. Set it in your .env file.")
        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    def create_embedding(self, text: str) -> List[float]:
        """Create an embedding for a single text."""
        try:
            result = self.client.models.embed_content(
                model=self.model,
                contents=text,
            )
            if not result.embeddings:
                raise RuntimeError("Embedding API returned no embeddings")
            return result.embeddings[0].values
        except Exception as e:
            raise RuntimeError(f"Failed to create embedding: {e}")

    def create_embeddings_batch(
        self, texts: List[str], batch_size: int = 100
    ) -> List[List[float]]:
        """Create embeddings for multiple texts."""
        embeddings = []
        for text in texts:
            try:
                embeddings.append(self.create_embedding(text))
            except Exception as e:
                print(f"Error embedding text: {e}")
                embeddings.append([0.0] * EMBEDDING_DIMENSION)
        return embeddings

    def get_embedding_dimension(self) -> int:
        return EMBEDDING_DIMENSION

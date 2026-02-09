"""
Pydantic Schemas

Data models for the RAG pipeline.
"""

from typing import List

from pydantic import BaseModel, Field


class RAGResponse(BaseModel):
    """Response from the RAG engine.

    Attributes:
        answer: The generated answer text
        sources: List of source references (empty for Alation-only)
        question: The original question
    """
    answer: str
    sources: List[str] = Field(default_factory=list)
    question: str

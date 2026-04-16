from pydantic import BaseModel, Field


class Utterance(BaseModel):
    id: str
    chunk_id: int
    speaker: str = Field(default="unknown")
    text: str = Field(default="")
    start_time: float = Field(default=0.0)
    end_time: float = Field(default=0.0)
    confidence: float = Field(default=0.0)

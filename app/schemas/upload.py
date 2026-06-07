from pydantic import BaseModel


class UploadIngestResponse(BaseModel):
    job_id: int

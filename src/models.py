from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from typing import List, Union, Tuple, Optional, Type
from fastapi import Query, Form

# @dataclass
class Topic(BaseModel):
    topic_name: str = "video_upload"
    num_partitions: int = 1
    replication_factor: int = 1
    retention: str = Query("7200000", description="The unit is in ms")
    cleanup_policy: str = "delete"
    message_size: str = Query("1048588", description="The unit is in bytes")
    
# @dataclass
class ProduceInput(BaseModel):
    sess_id: str = Query(...)
    name: str = Query(...)
    topic_name: str = Query("video_upload")
    overview: str = ""
    category: str = ""
    mute: bool = True
    
# @dataclass
class InputQueryWorker(BaseModel):
    sess_id: str = ""
    query: str = ""
    
# @dataclass
class Status(BaseModel):
    sess_id: str = ""
    
# @dataclass
class VideoId(BaseModel):
    v_ids: list = [""]
    table_name: str = "videos"
    
# @dataclass
class InputDataWorker(BaseModel):
    sess_id: str = ""
    v_id: str = ""
    name: str = ""
    path_file: str = ""
    overview: str = ""
    category: str = ""
    mute: bool = True

# @dataclass
class OutputDataWorker(BaseModel):
    status: str = ""
    results: object = None
    error: str = ""
    submitted_at: str = ""
    completed_at: str = ""
    
# @dataclass
class VideoHighlight(BaseModel):
    id: str
    start_time: float = 0.0
    end_time: float = 0.0
    highlight_time: float = 0.0
    path_video: str = ""
    description: str = ""
    duration: float = 0.0
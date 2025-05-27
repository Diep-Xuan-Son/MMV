from dataclasses import dataclass, field
from typing import List, Union, Tuple, Optional, Type
from fastapi import Query, Form

@dataclass
class Topic:
    topic_name: str = "video_upload"
    num_partitions: int = 1
    replication_factor: int = 1
    retention: str = Query("3600000", description="The unit is in ms")
    cleanup_policy: str = "delete"
    message_size: str = Query("1048588", description="The unit is in bytes")
    
@dataclass
class ProduceInput:
    sess_id: str = ""
    topic_name: str = "video_upload"
    overview: str = ""
    category: str = ""
    
@dataclass
class InputDataWorker:
    sess_id: str = ""
    path_file: str = ""
    overview: str = ""
    category: str = ""

@dataclass
class OutputDataWorker:
    status: str = ""
    results: object = None
    error: str = ""
    submitted_at: str = ""
    completed_at: str = ""
    
@dataclass
class VideoHighlight:
    id: str
    start_time: float = 0.0
    end_time: float = 0.0
    highlight_time: float = 0.0
    path_video: str = ""
    description: str = ""
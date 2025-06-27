import time
import redis
import asyncio
# from confluent_kafka import Producer
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from confluent_kafka.admin import AdminClient
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Union, Tuple, Optional, Type
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi import FastAPI, Request, Depends, Body, HTTPException, status, Query, File, UploadFile, Form

from libs.utils import *
from multiprocess_worker import Config, MultiprocessWoker, AIOKafkaProducer

os.environ["TOKENIZERS_PARALLELISM"] = "false"

FILE = Path(__file__).resolve()
ROOT = FILE.parents[0]
# PATH_LOG = f"{str(ROOT)}{os.sep}logs"
# PATH_STATIC = f"{str(ROOT)}{os.sep}static"
# PATH_TEMP = os.path.join(PATH_STATIC, "temp")
PATH_LOG = Config.PATH_LOG
PATH_STATIC = Config.PATH_STATIC
PATH_TEMP = Config.PATH_TEMP
check_folder_exist(path_log=PATH_LOG, path_static=PATH_STATIC, path_temp=PATH_TEMP)
# LOGGER_APP = set_log_file(file_name="app")

MULTIW = MultiprocessWoker()

@asynccontextmanager
async def lifespan(app: FastAPI): 
    # Start the consumers
    consumer_tasks = []
    for i in range(Config.NUM_DATA_CONSUMERS):
        consumer_id = f"data_{i}"
        consumer_task = asyncio.create_task(
            MULTIW.process_data_consumer(consumer_id=consumer_id)
        )
        consumer_tasks.append(consumer_task)
        
    for i in range(Config.NUM_QUERY_CONSUMERS):
        consumer_id = f"query_{i}"
        consumer_task = asyncio.create_task(
            MULTIW.process_query_consumer(consumer_id=consumer_id)
        )
        consumer_tasks.append(consumer_task)

        
    # Create a producer for sending messages
    producer = AIOKafkaProducer(
        bootstrap_servers=Config.KAFKA_ADDRESS,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    await producer.start()
    app.state.producer = producer
    
    # Create admin client kafka
    kafka_client = AdminClient({'bootstrap.servers': Config.KAFKA_ADDRESS})
    app.state.kafka_client = kafka_client
    
    yield

    # Shutdown: Cancel all consumer tasks and stop the producer
    for task in consumer_tasks:
        task.cancel()
    
    await producer.stop()
    
    # Wait for all tasks to be cancelled
    await asyncio.gather(*consumer_tasks, return_exceptions=True)
    print("All consumer tasks have been cancelled")

# Create FastAPI application
app = FastAPI(
    title="Chat Bot API",
    description="High-concurrency API for calling chat bot",
    version="1.0.0",
    lifespan=lifespan
)
app.mount("/static", StaticFiles(directory=PATH_STATIC), name="static")
# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
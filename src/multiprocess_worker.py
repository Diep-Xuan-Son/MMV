import os
import jwt
import time
import json
import torch
import asyncio
import threading
import traceback
# from confluent_kafka import Consumer
from langchain_openai import ChatOpenAI
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from langchain_google_genai import ChatGoogleGenerativeAI

# from libs.utils import set_log_file
from data_worker import DBWorker
from main_pipeline import VideoMaketing
from highlight_worker import HighlightWorker
from models import InputDataWorker, OutputDataWorker, VideoHighlight

# LOGGER_WORKER = set_log_file(file_name="worker")

# Configuration settings
class Config:
    # GPU settings
    CUDA_AVAILABLE = torch.cuda.is_available()
    NUM_GPUS = torch.cuda.device_count() if CUDA_AVAILABLE else 0
    NUM_CONSUMERS = 1
    
    BATCH_SIZE = 8
    DBMEM_NAME = "Memory"
    REDISSERVER_IP = os.getenv('REDISSERVER_IP', "192.168.6.163")
    REDISSERVER_PORT = os.getenv('REDISSERVER_PORT', 6400)
    # LOGGER_WORKER.info(f"----REDISSERVER_IP: {REDISSERVER_IP}")
    # LOGGER_WORKER.info(f"----REDISSERVER_PORT: {REDISSERVER_PORT}")
    KAFKA_ADDRESS = os.getenv('KAFKA_ADDRESS', 'localhost:9094')
    TOPIC_DATA = os.getenv('TOPIC_DATA', "video_upload")
    GROUP_ID_DATA = os.getenv('GROUP_ID_DATA', "data_consumer")
    COLLECTION_NAME = os.getenv('COLLECTION_NAME', "mmv")
    BUCKET_NAME = os.getenv('BUCKET_NAME', "data_mmv")
    
    model_hl_path: str='./weights/model_highlight.ckpt'
    model_slowfast_path: str='./weights/SLOWFAST_8x8_R50.pkl',
    model_clip_path: str='./weights/ViT-B-32.pt',

    SECRET_KEY = os.getenv('SECRET_KEY', "MMV")
    token_openai = os.getenv('API_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5Ijoic2stcHJvai1QSDNHNnlMVEticmdvaU9ieTA4YlVMNHc0eVYxR3NJa25IeEltTl9VMFI1WmVsOWpKcDI0MzZuNUEwOTdVdTVDeXVFMDJha1RqNVQzQmxia0ZKX3dJTUw2RHVrZzh4eWtsUXdsMTN0b2JfcGVkV1c0T1hsNzhQWGVIcDhOLW1DNjY1ZE1CdUlLMFVlWEt1bzRRUnk2Ylk1dDNYSUEifQ.2qjUENU0rafI6syRlTfnKIsm6O4zuhHRqahUcculn8E')
    API_KEY_OPENAI = jwt.decode(token_openai, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
    token_gem = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5IjoiQUl6YVN5QS12aGZOalRFYmNzOUNDTHNDbmIyMmdDQjFtU0tMeWZ3In0.iUeorjiPqQ0XSCGovWw0gEY9EAg-SxVedUWdvZt4X94'
    API_KEY_GEM = jwt.decode(token_gem, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
DATAW = DBWorker()
VM = VideoMaketing(api_key_openai=Config.API_KEY_OPENAI,api_key_gem=Config.API_KEY_GEM)

class MultiprocessWoker():
    def __init__(self, ):
        # Task queue and results
        self.results_store: dict[str, OutputDataWorker] = {}

    # Task processor
    async def process_data_consumer(self, consumer_id: int):
        # --------Consumer-----------
        consumer = AIOKafkaConsumer(
            Config.TOPIC_DATA,
            bootstrap_servers=Config.KAFKA_ADDRESS,
            group_id=Config.GROUP_ID_DATA,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            session_timeout_ms=100000,  # 100 seconds
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        while True:
            try:
                await consumer.start()
                print(f"Consumer {consumer_id} started")
                
                # Process messages
                async for message in consumer:
                    print(f"Consumer {consumer_id} received: {message.value} from partition {message.partition}")
                    
                    # Process the message here
                    data = message.value
                    #----upload original file to minio----
                    res = DATAW.upload_file2bucket(bucket_name=Config.BUCKET_NAME, folder_name=f"{Config.COLLECTION_NAME}_backup", list_file_path=[data["path_file"]])
                    if not res["success"]:
                        print(f"Error push file to bucket '{Config.BUCKET_NAME}': {res['error']}")
                    #////////////////////////////
                    
                    datatf = VM.preprocess_data(data=data)
                    v_id = os.path.basename(data["path_file"])
                    res = DATAW.upload_data(collection_name=Config.COLLECTION_NAME, bucket_name=Config.BUCKET_NAME, v_id=v_id, overview=datatf["overview"], list_path=datatf["list_path"], list_des=datatf["list_des"], list_htime=datatf["list_htime"], category=datatf["category"])
                    
                    if res["success"]:
                        print("Upload data success!")
                    
            except asyncio.CancelledError:
                print(f"Consumer {consumer_id} is shutting down")
            except Exception as e:
                print(f"Error in consumer {consumer_id}: {e}")
                await asyncio.sleep(1)  # Prevent tight loop in case of errors
            # finally:
            #     await consumer.stop()
            #     print(f"Consumer {consumer_id} stopped")

if __name__=="__main__":
    MTW = MultiprocessWoker()
    asyncio.run(MTW.process_data_consumer(consumer_id=0))
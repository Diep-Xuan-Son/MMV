import os
import jwt
import time
import json
import uuid
import torch
import asyncio
import psycopg2
import threading
import traceback
from urllib.parse import urlparse 
# from confluent_kafka import Consumer
from langchain_openai import ChatOpenAI
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from langchain_google_genai import ChatGoogleGenerativeAI

# from libs.utils import set_log_file
# from data_worker import DBWorker
from main_pipeline import VideoMaketing
# from highlight_worker import HighlightWorker
from models import InputDataWorker, OutputDataWorker, VideoHighlight
from libs.utils import delete_folder_exist

import sys
from pathlib import Path 
FILE = Path(__file__).resolve()
DIR = FILE.parents[0]
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# LOGGER_WORKER = set_log_file(file_name="worker")

# Configuration settings
class Config:
    from dotenv import load_dotenv
    # Load environment variables from .env file
    load_dotenv()

    # GPU settings
    CUDA_AVAILABLE      = torch.cuda.is_available()
    NUM_GPUS            = torch.cuda.device_count() if CUDA_AVAILABLE else 0
    NUM_DATA_CONSUMERS  = 1
    NUM_QUERY_CONSUMERS = 1
    BATCH_SIZE          = 8
    DBMEM_NAME          = "memory"
    NUM_WORKER          = int(os.getenv('NUM_WORKER', "2"))
    
    # REDISSERVER_IP       = os.getenv('REDISSERVER_IP', "localhost")
    # REDISSERVER_PORT     = os.getenv('REDISSERVER_PORT', 6669)
    REDISSERVER_URL      = os.getenv('REDISSERVER_URL', "http://localhost:6669")
    REDISSERVER_PASSWORD = os.getenv('REDISSERVER_PASSWORD', 'RedisAuth')
    
    POSTGRES_URL      = os.getenv('POSTGRES_URL', "http://localhost:6670")
    POSTGRES_DBNAME   = os.getenv('POSTGRES_DBNAME', "mmv")
    POSTGRES_USER     = os.getenv('POSTGRES_USER', "demo")
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', "demo123456")
    TABLE_NAME        = os.getenv('TABLE_NAME', "videos")
    
    KAFKA_ADDRESS      = os.getenv('KAFKA_ADDRESS', 'localhost:9094')
    TOPIC_DATA         = os.getenv('TOPIC_DATA', "video_upload")
    TOPIC_QUERY        = os.getenv('USER_QUERY', "user_query")
    GROUP_ID_DATA      = os.getenv('GROUP_ID_DATA', "data_consumer")
    GROUP_ID_QUERY     = os.getenv('GROUP_ID_QUERY', "query_consumer")
    
    QDRANT_URL      = os.getenv('QDRANT_URL', "http://localhost:7000")
    COLLECTION_NAME = os.getenv('COLLECTION_NAME', "mmv")
    
    MINIO_URL        = os.getenv('MINIO_URL', "localhost:9000")
    BUCKET_NAME      = os.getenv('BUCKET_NAME', "data_mmv")
    MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', "demo")
    MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', "demo123456")
    
    sparse_model_path   = f"./weights/all_miniLM_L6_v2_with_attentions"
    dense_model_path    = f"./weights/Vietnamese_Embedding"
    model_hl_path       = './weights/model_highlight.ckpt'
    model_slowfast_path = './weights/SLOWFAST_8x8_R50.pkl'
    model_clip_path     = './weights/ViT-B-32.pt'
    
    PATH_LOG           = f"{str(DIR)}{os.sep}logs"
    PATH_STATIC        = f"{str(DIR)}{os.sep}static"
    PATH_TEMP          = os.path.join(PATH_STATIC, "temp")
    FOLDER_FINAL_VIDEO = os.getenv('FOLDER_FINAL_VIDEO', "final_video")

    SECRET_KEY     = os.getenv('SECRET_KEY', "MMV")
    token_openai   = os.getenv('API_KEY_OPENAI', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5Ijoic2stcHJvai1QSDNHNnlMVEticmdvaU9ieTA4YlVMNHc0eVYxR3NJa25IeEltTl9VMFI1WmVsOWpKcDI0MzZuNUEwOTdVdTVDeXVFMDJha1RqNVQzQmxia0ZKX3dJTUw2RHVrZzh4eWtsUXdsMTN0b2JfcGVkV1c0T1hsNzhQWGVIcDhOLW1DNjY1ZE1CdUlLMFVlWEt1bzRRUnk2Ylk1dDNYSUEifQ.2qjUENU0rafI6syRlTfnKIsm6O4zuhHRqahUcculn8E')
    API_KEY_OPENAI = jwt.decode(token_openai, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
    token_gem   = os.getenv('API_KEY_GEM', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5IjoiQUl6YVN5Q1BKSHNJYUxXaGdMakllQkZVS3E4VHFrclRFdWhGd2xzIn0.7iN_1kRmOahYrT7i5FUplOYeda1s7QhYzk-D-AlgWgE')
    API_KEY_GEM = jwt.decode(token_gem, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
# DATAW = DBWorker()

class MultiprocessWoker():
    def __init__(self, ):
        # Task queue and results
        self.results_store: dict[str, OutputDataWorker] = {}
        self.VM = VideoMaketing(
            api_key_openai=Config.API_KEY_OPENAI,
            api_key_gem=Config.API_KEY_GEM,
            
            qdrant_url=Config.QDRANT_URL, 
            collection_name=Config.COLLECTION_NAME, 
            minio_url=Config.MINIO_URL, 
            minio_access_key=Config.MINIO_ACCESS_KEY,
            minio_secret_key=Config.MINIO_SECRET_KEY,
            bucket_name=Config.BUCKET_NAME,
            redis_url=Config.REDISSERVER_URL, 
            redis_password=Config.REDISSERVER_PASSWORD,
            dbmemory_name=Config.DBMEM_NAME,
            psyconpg_url=Config.POSTGRES_URL,
            dbname=Config.POSTGRES_DBNAME,
            psyconpg_user=Config.POSTGRES_USER,
            psyconpg_password=Config.POSTGRES_PASSWORD,
            table_name=Config.TABLE_NAME,
            sparse_model_path=Config.sparse_model_path, 
            dense_model_path=Config.dense_model_path
        )
        self.cur = self.init_postgres(Config.POSTGRES_DBNAME, Config.POSTGRES_URL, Config.POSTGRES_USER, Config.POSTGRES_PASSWORD)
    
    def init_postgres(self, dbname: str, url: int, user: str, password: str):
        #----setup postgreSQL----
        url_pg = urlparse(url)
        conn = psycopg2.connect(dbname=dbname,
                                host=url_pg.hostname, 
                                port=url_pg.port, 
                                user=user, 
                                password=password)
        cur = conn.cursor()
        conn.set_session(autocommit = True)
        return cur
    
    def is_deleted(self, cur: object, columns: list, sess_id: str, type: str, local_path_delete: list, minio_path_delete: list, v_id_delete: list):
        res = self.VM.dataw.get_status(cur, columns, sess_id)
        if res["success"]:
            if res["result"]["status"] == "interrupted":
                self.VM.dataw.update_status(cur, sess_id, type, {"local_path_delete": local_path_delete, "minio_path_delete": minio_path_delete, "v_id_delete": v_id_delete}, 0, "deleted")
                return True
        return False

    # Task processor
    async def process_data_consumer(self, consumer_id: int):
        # --------Consumer-----------
        consumer = AIOKafkaConsumer(
            Config.TOPIC_DATA,
            bootstrap_servers=Config.KAFKA_ADDRESS,
            group_id=Config.GROUP_ID_DATA,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            session_timeout_ms=600000,  # 600 seconds
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        await consumer.start()
        print(f"Consumer {consumer_id} started")
        
        cur = self.init_postgres(Config.POSTGRES_DBNAME, Config.POSTGRES_URL, Config.POSTGRES_USER, Config.POSTGRES_PASSWORD)
        
        while True:
            try:
                # Process messages
                async for message in consumer:
                    # await asyncio.sleep(1)
                    print(f"Consumer {consumer_id} received: {message.value} from partition {message.partition}")
                    
                    data = message.value
                    
                    # check status
                    columns = ["status"]
                    res = self.VM.dataw.get_status(cur, columns, data["sess_id"])
                    if res["success"]:
                        if res["result"]["status"] in ["deleted", "interrupted"] :
                            print(f"Message {data} has been deleted!")
                            continue
                    else:
                        print(f"The session ID {data['sess_id']} not found!")
                        continue
                    self.VM.dataw.update_status(cur, data["sess_id"], "data", res, 1, "pending")
                    
                    # Process the message here
                    name_v = data["name"]
                    if not name_v:
                        name_v = os.path.basename(data["path_file"])
                    # v_id = f"{uuid.uuid4()}_{round(time.time())}".replace('-','_')
                    v_id = data["v_id"]
                    
                    #----upload original file to minio----
                    res_file2bucket = self.VM.dataw.upload_file2bucket(bucket_name=Config.BUCKET_NAME, folder_name=f"{data['scenario_name']}{os.sep}{Config.COLLECTION_NAME}_backup", list_file_path=[data["path_file"]])
                    if not res_file2bucket["success"]:
                        raise ValueError(f"Error push file to bucket '{Config.BUCKET_NAME}': {res_file2bucket['error']}")
                        # print(f"Error push file to bucket '{Config.BUCKET_NAME}': {res_file2bucket['error']}")
                    else:
                        path_file_new = res_file2bucket["list_path_new"][0]
                    #////////////////////////////
                    if self.is_deleted(cur, columns, data["sess_id"], "data", [data["path_file"]], [], []):
                        continue
                    self.VM.dataw.update_status(cur, data["sess_id"], "data", res, 10, "pending")
                    
                    #----preprocess data----
                    data["scene_dict"] = json.loads(self.VM.dataw.get_scenario(cur, data['scenario_name'])["result"]["scenes"])
                    datatf = await self.VM.preprocess_data_nohl(data=data)
                    #//////////////////////
                    scenario_id = f"{data['sender_id']}_{data['scenario_name']}"
                    if datatf["success"]:
                        data_info = {
                            "sender_id": data["sender_id"],
                            "sess_id": data["sess_id"],
                            "collection_name": Config.COLLECTION_NAME,
                            "bucket_name": Config.BUCKET_NAME,
                            "table_name": Config.TABLE_NAME,
                            "v_id": v_id,
                            "v_name": name_v,
                            "root_path": path_file_new,
                            "mute": data["mute"],
                            "scenario_id": scenario_id,
                            "file_type": data["file_type"]
                        }
                        data_info.update(datatf)
                        
                        #----upload data to database----
                        res_upload_data = self.VM.dataw.upload_data(**data_info)
                        if self.is_deleted(cur, columns, data["sess_id"], "data", [data["path_file"]] + datatf["list_path_delete"], res_upload_data["list_path_new"], [v_id]):    # because delete file in buck auto merge folder and file name so that just get all the path have basename in the bucket
                            continue
                        #///////////////////////////////    
                        if res_upload_data["success"]:
                            print("Upload data success!")
                            self.VM.dataw.update_status(cur, data["sess_id"], "data", res_upload_data, 100, "done")
                    else:
                        self.VM.dataw.update_status(cur, data["sess_id"], "data", {"local_path_delete": [], "minio_path_delete": [], "v_id_delete": []}, 0, "deleted")
                
                    delete_folder_exist(*datatf["list_path_delete"], data["path_file"])
                    
            except asyncio.CancelledError:
                print(f"Consumer {consumer_id} is shutting down")
                await consumer.stop()
                break
            except Exception as e:
                tb_str = traceback.format_exc()
                print(f"Error in consumer {consumer_id}: {tb_str}")
                cur.execute(
                    "INSERT INTO tasks (session_id, type, result, percent, status) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (session_id) DO UPDATE SET result = EXCLUDED.result, status = EXCLUDED.status;",
                    (data["sess_id"], "data", json.dumps({"success": False, "error": str(e)}), "100", "error")
                )
                await asyncio.sleep(1)  # Prevent tight loop in case of errors
            # finally:
            #     await asyncio.sleep(1)
            #     await consumer.stop()
            #     print(f"Consumer {consumer_id} stopped")
        self.VM.dataw.cur.close()
        await consumer.stop()
        
    # Task processor
    async def process_query_consumer(self, consumer_id: int):
        # --------Consumer-----------
        consumer = AIOKafkaConsumer(
            Config.TOPIC_QUERY,
            bootstrap_servers=Config.KAFKA_ADDRESS,
            group_id=Config.GROUP_ID_QUERY,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            session_timeout_ms=300000,  # 300 seconds
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        await consumer.start()
        print(f"Consumer {consumer_id} started")
        
        cur = self.init_postgres(Config.POSTGRES_DBNAME, Config.POSTGRES_URL, Config.POSTGRES_USER, Config.POSTGRES_PASSWORD)
        
        while True:
            try:
                # Process messages
                async for message in consumer:
                    # await asyncio.sleep(1)
                    print(f"Consumer {consumer_id} received: {message.value} from partition {message.partition}")
                    
                    data = message.value
                    
                    # check status
                    columns = ["status"]
                    res = self.VM.dataw.get_status(cur, columns, data["sess_id"])
                    if res["success"]:
                        if res["result"]["status"] in ["deleted", "interrupted"] :
                            print(f"Message {data} has been deleted!")
                            continue
                    else:
                        print(f"The session ID {data['sess_id']} not found!")
                        continue
                    
                    data["u_id"] = data["sess_id"]
                    data["SCENE_DICT"] = json.loads(self.VM.dataw.get_scenario(cur, data['sender_id'], data['scenario_name'])["result"]["scenes"])
                    res_make_mv = await self.VM.make_mv(**data)
                    if res_make_mv["success"]:
                        path_final_video = res_make_mv["final_video"]
                        final_output_dir = os.path.dirname(path_final_video)
                        res = self.VM.dataw.upload_file2bucket(bucket_name=Config.BUCKET_NAME, folder_name=f"{data['scenario_name']}{os.sep}{Config.FOLDER_FINAL_VIDEO}", list_file_path=[path_final_video])
                        if res["success"]:
                            res["list_path_new"] = res["list_path_new"][0]
                            self.VM.dataw.update_status(cur, data["sess_id"], "query", res, 100, "done")
                    else:
                        self.VM.dataw.update_status(cur, data["sess_id"], "query", {"local_path_delete": [], "minio_path_delete": [], "v_id_delete": []}, 0, "deleted")

                    delete_folder_exist(*res_make_mv["list_path_delete"])
                    
            except asyncio.CancelledError:
                print(f"Consumer {consumer_id} is shutting down")
                await consumer.stop()
                break
            except Exception as e:
                tb_str = traceback.format_exc()
                print(f"Error in consumer {consumer_id}: {tb_str}")
                # self.VM.dataw.update_status(data["sess_id"], "query", {"success": False, "error": str(e)}, 100, "error")
                cur.execute(
                    "INSERT INTO tasks (session_id, type, result, percent, status) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (session_id) DO UPDATE SET result = EXCLUDED.result, status = EXCLUDED.status;",
                    (data["sess_id"], "query", json.dumps({"success": False, "error": str(e)}), "100", "error")
                )
                await asyncio.sleep(1)  # Prevent tight loop in case of errors
        await consumer.stop()

if __name__=="__main__":
    
    MTW = MultiprocessWoker()
    asyncio.run(MTW.process_data_consumer(consumer_id=0))
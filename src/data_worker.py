import sys
from pathlib import Path 
FILE = Path(__file__).resolve()
DIR = FILE.parents[0]
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
    
import os 
import time
import uuid
import json 
import redis
import psycopg2
import traceback
import numpy as np
from tqdm import tqdm
from minio import Minio
from datetime import datetime
from urllib.parse import urlparse 
from confluent_kafka.admin import NewTopic
# from redisvl.utils.vectorize import HFTextVectorizer
# from redisvl.extensions.llmcache import SemanticCache
from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models as qmodels

from libs.utils import MyException

class DBWorker(object):
    def __init__(self, 
                 qdrant_url="http://localhost:7000",
                 collection_name="mmv",
                 
                 minio_url="localhost:9000", 
                 minio_access_key="demo",
                 minio_secret_key="demo123456",
                 bucket_name="data_mmv",
                 
                 redis_url="redis://:root@localhost:6669", 
                 redis_password="RedisAuth",
                 dbmemory_name="memory",
                 
                 psyconpg_url="http://localhost:6670",
                 dbname="mmv",
                 psyconpg_user='demo',
                 psyconpg_password='demo123456',
                 table_name='videos',
                 
                 sparse_model_path=f"./weights/all_miniLM_L6_v2_with_attentions", 
                 dense_model_path=f"./weights/Vietnamese_Embedding", 
                 check_connection=False, 
                 cache=False):
        #----setup Qdrant----
        self.qdrant_client = QdrantClient(qdrant_url, https=True, timeout=60, api_key="test_qdrant")
        self.model_bm42 = SparseTextEmbedding(model_name=sparse_model_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        self.model_text = TextEmbedding(model_name=dense_model_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        model_dir = self.model_text.model_name
        with open(os.path.join(model_dir, "config.json")) as f:
            data_config = json.load(f)
        self.embed_dims = data_config['hidden_size']

        #----setup Minio----
        self.minio_client = Minio(
                                endpoint=minio_url,
                                access_key=minio_access_key,
                                secret_key=minio_secret_key,
                                secure=False,
                            )
        
        #----setup postgreSQL----
        url_pg = urlparse(psyconpg_url)
        conn = psycopg2.connect(dbname=dbname,
                                host=url_pg.hostname, 
                                port=url_pg.port, 
                                user=psyconpg_user, 
                                password=psyconpg_password)
        self.cur = conn.cursor()
        conn.set_session(autocommit = True)
        
        #----setup cache redis----
        self.dbmemory_name = dbmemory_name
        url_redis = urlparse(redis_url)
        self.redisClient = redis.StrictRedis(host=url_redis.hostname,
                                            port=url_redis.port,
                                            password=redis_password,
                                            db=0)
        # if cache:
        #     redis_ttl = 900
        #     vectorizer = HFTextVectorizer(model=dense_model_path)
        #     self.llmcache = SemanticCache(name="llmcache", ttl=redis_ttl, redis_url=redis_url, distance_threshold=0.2, vectorizer=vectorizer, overwrite=True)
        
        self.init_db(collection_name=collection_name, bucket_name=bucket_name, db_name=dbname, table_name=table_name)
           
    def create_collection(self, collection_name: str):
        if self.qdrant_client.collection_exists(collection_name=collection_name):
            return {"success": False, "error": f"Collection {collection_name} already exists"}
        self.qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "text": qmodels.VectorParams(
                    size=self.embed_dims,
                    distance=qmodels.Distance.COSINE,
                ),
                # "on_disk": True
            },
            sparse_vectors_config={
                "bm42": qmodels.SparseVectorParams(
                    modifier=qmodels.Modifier.IDF,
                    # index=qmodels.SparseIndexParams(on_disk=False),
                )
            },
            # shard_number=1, # 2-4 is a reasonable number, the number of shards per shard key
            # sharding_method=qmodels.ShardingMethod.CUSTOM,
            # replication_factor=2,

            hnsw_config=qmodels.HnswConfigDiff(
                payload_m=16,
                m=0,
            ),

            # optimizers_config=qmodels.OptimizersConfigDiff(indexing_threshold=0, default_segment_number=16),	
            # quantization_config=qmodels.ScalarQuantization(	# High Precision with High-Speed Search
            # 	scalar=qmodels.ScalarQuantizationConfig(
            # 		type=qmodels.ScalarType.INT8,
            # 		always_ram=True,
            # 	),
            # ),
            # on_disk_payload= True
        )
        
        self.qdrant_client.create_payload_index(
            collection_name=collection_name,
            field_name="category",
            field_schema="text"
        )

        return {"success": True}
    
    def delete_collection(self, collection_name: str):
        if not self.qdrant_client.collection_exists(collection_name=collection_name):
            return {"success": False, "error": f"Collection {collection_name} has not been registered yet"}
        self.qdrant_client.delete_collection(collection_name=collection_name)
        return {"success": True}
    
    def create_shard_key(self, collection_name: str, group_id: str):
        try:
            self.qdrant_client.create_shard_key(collection_name, group_id)
        except Exception as e:
            return {"success": False, "error": f"{e}\nShard key {group_id} existed!"}
        return {"success": True}

    def delete_shard_key(self, collection_name: str, group_id: str):
        try:
            self.qdrant_client.delete_shard_key(collection_name, group_id)
        except Exception as e:
            return {"success": False, "error": f"{e}\nShard key {group_id} does not exist!"}
        return {"success": True}
    
    def add_vector(self, 
                   collection_name: str, 
                   v_id: str, 
                   v_name: str,
                   root_path: str,
                   overview: str, 
                   list_path: list, 
                   list_des: list, 
                   list_htime: list, 
                   list_duration: list,  
                   category: str="",  
                   mute: bool=True,
                   scenario_id: str="",
                   group_id: str="group1"):
        if not self.qdrant_client.collection_exists(collection_name=collection_name):
            return {"success": False, "error": f"Collection {collection_name} has not been registered yet"}
        pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, v_id))
        self.qdrant_client.upload_points(
            collection_name=collection_name,
            points=[
                qmodels.PointStruct(
                    id=pid, # uuid.uuid4().hex
                    vector={
                        "text": list(self.model_text.query_embed(overview))[0].tolist(),
                        "bm42": list(self.model_bm42.query_embed(overview))[0].as_object(),
                    },
                    payload={
                        "v_id": v_id,
                        "name": v_name,
                        "root_path": root_path,
                        "overview": overview,
                        "list_path": list_path,
                        "list_des": list_des,
                        "list_htime": list_htime,
                        "list_duration": list_duration,
                        "category": category,
                        "mute": mute,
                        "scenario_id": scenario_id,
                        "datetime": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                        "timestamp": time.time(),
                        "group_id": group_id
                    },
                ),
            ], 
            batch_size=64,
            parallel=1,
            max_retries=3,
            # shard_key_selector=group_id,
        )
        return {"success": True}
    
    def delete_vector(self, collection_name: str, list_v_id: list):   
        if not self.qdrant_client.collection_exists(collection_name=collection_name):
            return {"success": False, "error": f"Collection {collection_name} has not been registered yet"}
        self.qdrant_client.delete(
            collection_name=collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="v_id",
                            match=qmodels.MatchAny(any=list_v_id),
                        ),
                    ],
                )
            ),
        )
        return {"success": True}
    
    def retrieve(self, collection_name: str, text_querys: list[str], categories: list[str], schema_filter: dict=None, n_result: int=5, similarity_threshold: float=0.5):
        sparse_embedding = list(self.model_bm42.query_embed(text_querys))
        dense_embedding = list(self.model_text.query_embed(text_querys))
        if schema_filter is None:
            query_filter = None
        else:
            query_filter = qmodels.Filter(
                                        must=[
                                            qmodels.FieldCondition(
                                                key=k,
                                                match=qmodels.MatchAny(
                                                    any=v,
                                                ),
                                            )
                                        for k, v in schema_filter.items()]
                                    )
        
        results = []
        scores = []
        names = []
        list_paths = []
        list_dess = []
        list_htimes = []
        list_durations = []
        for i in range(len(text_querys)):
            query_filter = qmodels.Filter(
                                        must=[
                                            qmodels.FieldCondition(
                                                key="category",
                                                match=qmodels.MatchAny(
                                                    any=[categories[i]],
                                                ),
                                            )
                                        ]
                                    )
            
            result = {}
            score = []
            name = []
            list_path = {}
            list_des = {}
            list_htime = {}
            list_duration = {}
            query_results = self.qdrant_client.query_points(
                collection_name=collection_name,
                prefetch=[
                    qmodels.Prefetch(query=sparse_embedding[i].as_object(), 
                                    filter=query_filter,
                                    using="bm42", 
                                    limit=20),
                    qmodels.Prefetch(query=dense_embedding[i].tolist(), 
                                    filter=query_filter,
                                    using="text", 
                                    limit=20),
                ],
                query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF), # <--- Combine the scores
                # query_filter=query_filter
                limit=n_result
            ).points
            # [(result.append(hit.payload), score.append(hit.score), list_des.append(hit.payload["list_des"])) for hit in query_results if hit.score>similarity_threshold]
            for j, hit in enumerate(query_results):
                if hit.score>similarity_threshold:
                    id_v = f"video_{j + n_result*i}"
                    list_des[id_v] = hit.payload["list_des"][i]
                    list_path[id_v] = hit.payload["list_path"][i]
                    list_htime[id_v] = hit.payload["list_htime"][i]
                    list_duration[id_v] = hit.payload["list_duration"][i]
            list_dess.append(list_des)
            list_paths.append(list_path)
            list_htimes.append(list_htime)
            list_durations.append(list_duration)
            # print(query_results)
            # if len(score):
            #     rand = np.random.random(len(score))
            #     score_sort_idx = np.lexsort((rand,score))[::-1]
            #     names.append(result[score_sort_idx[0]].payload["name"])
            #     scores.append(score[score_sort_idx[0]])
            # else:
            #     names.append("")
            #     scores.append(0)
        print(list_dess)
        print(list_paths)
        return {"success": True, "list_des": list_dess, "list_paths": list_paths, "list_htimes": list_htimes, "list_durations": list_durations}
            
    def create_bucket(self, bucket_name: str):
        bucket_name = bucket_name.replace("_", "-")
        found = self.minio_client.bucket_exists(bucket_name=bucket_name)
        if found:
            return {"success": False, "error": f"Bucket {bucket_name} already exists, skip creating!"}
        self.minio_client.make_bucket(bucket_name=bucket_name)
        return {"success": True}

    def upload_file2bucket(self, bucket_name: str, folder_name: str, list_file_path: list):
        bucket_name = bucket_name.replace("_", "-")
        found = self.minio_client.bucket_exists(bucket_name=bucket_name)
        if not found:
            return {"success": False, "error": f"Bucket {bucket_name} does not exist!"}
        objects_exist = self.get_file_name_bucket(bucket_name, folder_name)["data"]
        objects_exist = [x.object_name for x in objects_exist]
        list_path_new = []
        for i, fp in enumerate(list_file_path):
            fn = os.path.basename(fp)
            object_name = os.path.join(folder_name, fn)
            list_path_new.append(object_name)
            if object_name in objects_exist:
                # LOGGER_RETRIEVAL.info(f"File {fn} exists!")
                continue
            self.minio_client.fput_object(
                bucket_name=bucket_name, object_name=object_name, file_path=fp,
            )
        return {"success": True, "list_path_new": list_path_new}
    
    def download_file(self, bucket_name: str, object_name: str, folder_local: str):
        bucket_name = bucket_name.replace("_", "-")
        fn = os.path.basename(object_name)
        file_path = os.path.join(folder_local, fn)
        response = self.minio_client.fget_object(bucket_name=bucket_name, object_name=object_name, file_path=file_path)
        return {"success": True, "file_path": file_path}

    def delete_file_bucket(self, bucket_name: str, folder_name: str, list_file_name: list):
        bucket_name = bucket_name.replace("_", "-")
        found = self.minio_client.bucket_exists(bucket_name=bucket_name)
        if not found:
            return {"success": False, "error": f"Bucket {bucket_name} does not exist!"}
        for i, fn in enumerate(list_file_name):
            self.minio_client.remove_object(bucket_name=bucket_name, object_name=os.path.join(folder_name, os.path.basename(fn)))
        return {"success": True}

    def delete_folder_bucket(self, bucket_name: str, folder_name: str):
        bucket_name = bucket_name.replace("_", "-")
        objects_to_delete = self.get_file_name_bucket(bucket_name, folder_name)["data"]
        for obj in objects_to_delete:
            self.minio_client.remove_object(bucket_name=bucket_name, object_name=obj.object_name)
        return {"success": True}

    def get_file_name_bucket(self, bucket_name: str, folder_name: str):
        bucket_name = bucket_name.replace("_", "-")
        found = self.minio_client.bucket_exists(bucket_name=bucket_name)
        if not found:
            return {"success": False, "error": f"Bucket {bucket_name} does not exist!"}
        return {"success": True, "data": self.minio_client.list_objects(bucket_name, prefix=folder_name, recursive=True)}
    
    def create_topic(self, client: object, topic_name: str, num_partitions: int=1, replication_factor: int=1, retention: str="3600000", cleanup_policy: str="delete", message_size: str="1048588"):
        # Check if topic already exists
        existing_topics = client.list_topics(timeout=10).topics
        if topic_name not in existing_topics:
            # Define the topic you want to create
            config={
                'retention.ms': str(retention),  # 1 hour
                'cleanup.policy': cleanup_policy,
                'max.message.bytes': message_size
            }
            new_topic = NewTopic(topic=topic_name, num_partitions=num_partitions, replication_factor=replication_factor, config=config)
            # Create the topic
            fs = client.create_topics([new_topic])
            # Wait for topic creation to finish and check for errors
            for topic, f in fs.items():
                try:
                    f.result()  # Block until topic creation completes
                    message = f"Topic '{topic}' created successfully."
                    print(message)
                    return {"success": True, "message": message}
                except Exception as e:
                    tb_str = traceback.format_exc()
                    print(f"Failed to create topic '{topic}': {tb_str}")
                    return {"success": False, "error": e}
        else:
            error_ms = f"Topic '{topic_name}' already exists."
            print(error_ms)
            return {"success": False, "error": error_ms}
        
    def delete_topic(self, client: object, topic_name: str):
        # Check if topic already exists
        existing_topics = client.list_topics(timeout=10).topics
        if topic_name in existing_topics:
            # Delete the topic
            fs = client.delete_topics([topic_name], operation_timeout=30)
            for topic, f in fs.items():
                try:
                    f.result()  # Wait for deletion to complete
                    message = f"Topic '{topic}' deleted."
                    print(message)
                    return {"success": True, "message": message}
                except Exception as e:
                    tb_str = traceback.format_exc()
                    print(f"Failed to delete topic '{topic}': {tb_str}")
                    return {"success": False, "error": e}
        else:
            error_ms = f"Topic '{topic_name}' doesn't exists."
            print(error_ms)
            return {"success": False, "error": error_ms}
    
    def produce_message(self, producer: object, topic: str, messages: list[dict]):
        # Delivery report callback to confirm message delivery
        def delivery_report(err, msg):
            if err is not None:
                print(f"❌ Delivery failed: {err}")
            else:
                print(f"✅ Message delivered to {msg.topic()} [{msg.partition()}]")
        
        for message in messages:
            message_json = json.dumps(message)
            # Send the message (encoded to UTF-8)
            producer.produce(topic=topic, key=message["sess_id"], value=message_json.encode('utf-8'), callback=delivery_report)
            producer.poll(0)  # Triggers delivery callbacks
        
        producer.flush()
        return {"success": True, "message": f"Message delivered to {topic}"}
    
    @MyException()  
    def init_db(self, collection_name: str, bucket_name: str, db_name: str, table_name: str):
        #----create db qdrant----
        # res = self.delete_collection(collection_name=collection_name)
        # if not res["success"]:
        #     print(res["error"])
        res = self.create_collection(collection_name=collection_name)
        if not res["success"]:
            print(res["error"])

        # res = self.create_shard_key(collection_name=collection_name, group_id="group1")
        # if not res["success"]:
        #     print(res["error"])
        # ////////////////////////
        
        #----create db minio----
        res = self.create_bucket(bucket_name=bucket_name)
        if not res["success"]:
            print(res["error"])
        #///////////////////////
        
        #----create db postgres----
        # self.cur.execute(f'''DROP DATABASE {db_name}''')
        # self.cur.execute(f'''CREATE DATABASE {db_name}''')
        
        # self.cur.execute(f'''DROP TABLE IF EXISTS scenario CASCADE''')
        self.cur.execute(f'''
        CREATE TABLE IF NOT EXISTS scenario(
            id SERIAL PRIMARY KEY,
            s_id TEXT NOT NULL,
            sender_id VARCHAR(512) NOT NULL,
            name TEXT NOT NULL,
            scenes TEXT NOT NULL,
            UNIQUE (s_id)
        )''')
        
        # self.cur.execute(f'''DROP TABLE IF EXISTS {table_name}''')
        print(table_name)
        self.cur.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name}(
            id SERIAL PRIMARY KEY,
            sender_id TEXT NOT NULL,
            v_id VARCHAR(512) NOT NULL,
            v_name TEXT NOT NULL,
            root_path TEXT NOT NULL,
            overview TEXT NOT NULL,
            description_scenes TEXT NOT NULL,
            paths TEXT NOT NULL,
            highlight_times TEXT NOT NULL,
            durations TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            category VARCHAR(255) NOT NULL,
            mute BOOLEAN NOT NULL DEFAULT TRUE,
            file_type TEXT NOT NULL,
            UNIQUE (v_id),
            scenario_id TEXT REFERENCES scenario(s_id) ON DELETE CASCADE
        )''')
        
        # self.cur.execute(f'''DROP TABLE IF EXISTS tasks''')
        self.cur.execute(f'''
        CREATE TABLE IF NOT EXISTS tasks(
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(512) NOT NULL,
            type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            result TEXT NOT NULL,
            percent TEXT NOT NULL,
            status TEXT NOT NULL,
            UNIQUE (session_id)
        )''')
        #//////////////////////////
        return {"success": True}
    
    @MyException()
    def delete_db(self, collection_name: str, bucket_name: str, db_name: str, table_name: str):
        # ----delete db qdrant----
        res = self.delete_collection(collection_name=collection_name)
        if not res["success"]:
            print(res["error"])
        #/////////////////////////
        
        self.cur.execute(f'''DROP TABLE IF EXISTS {table_name}''')
        self.cur.execute(f'''DROP TABLE IF EXISTS tasks''')
        return {"success": True}
    
    def update_status(self, cur: object, sess_id: str, type: str, result: dict, percent: float, status: str):
        cur.execute(
            "INSERT INTO tasks (session_id, type, result, percent, status) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (session_id) DO UPDATE SET result = EXCLUDED.result, percent = EXCLUDED.percent, status = EXCLUDED.status;",
            (sess_id, type, json.dumps(result), str(percent), status)
        )
        
    def get_status(self, cur: object, columns: list, sess_id: str,):
        cur.execute(
            "SELECT " + ", ".join(columns) + " FROM tasks WHERE session_id = %s;",
            (sess_id,)
        )
        # Fetch all matching rows
        rows = cur.fetchall()
        if not len(rows):
            return {"success": False, "error": "The session ID not found!"}
        
        response = dict(zip(columns, rows[0]))
        return {"success": True, "result": response}
    
    def update_scenario(self, cur: object, sender_id: str, name: str, scenes: dict):
        s_id = f"{sender_id}_{name}"
        cur.execute(
            "INSERT INTO scenario (s_id, sender_id, name, scenes) VALUES (%s, %s, %s, %s) ON CONFLICT (s_id) DO UPDATE SET scenes = EXCLUDED.scenes;",
            (s_id, sender_id, name, json.dumps(scenes))
        )
    
    @MyException()    
    def delete_scenario(self, cur: object, sender_id: str, name: str):
        s_id = f"{sender_id}_{name}"
        cur.execute(
            "DELETE FROM scenario WHERE s_id = %s;",
            (s_id,)
        )
        return {"success": True}
        
    def get_scenario(self, cur: object, sender_id: str, scenario_name: str):
        s_id = f"{sender_id}_{scenario_name}"
        cur.execute(
            "SELECT scenes" + f" FROM scenario WHERE s_id = %s;",
            (s_id,)
        )
        rows = cur.fetchall()
        if not len(rows):
            return {"success": False, "error": "The scenario name not found!"}
        
        response = {"scenes": rows[0][0]}
        return {"success": True, "result": response}
    
    def get_list_scenario(self, cur: object, sender_id: str):
        cur.execute(
            "SELECT name" + f" FROM scenario WHERE sender_id = %s;",
            (sender_id,)
        )
        rows = cur.fetchall()
        if not len(rows):
            return {"success": False, "error": "The sender_id name not found!"}
        
        print(rows)
        response = [row[0] for row in rows]
        return {"success": True, "result": response}
    
    def get_row(self, cur: object, table_name: str, columns: list, v_ids: list):
        cur.execute(
            "SELECT " + ", ".join(columns) + f" FROM {table_name} WHERE v_id = ANY(%s);",
            (v_ids,)
        )
        # Fetch all matching rows
        rows = cur.fetchall()
        if not len(rows):
            return {"success": False, "error": "The video ID not found!"}
        
        rowtfs = list(map(list, zip(*rows)))
        response = dict(zip(columns, rowtfs))
        return {"success": True, "result": response}
    
    @MyException()        
    def upload_data(self,
                    sender_id: str,
                    sess_id: str,
                    collection_name: str, 
                    bucket_name: str, 
                    table_name: str, 
                    v_id: str, 
                    v_name: str, 
                    root_path: str, 
                    overview: str, 
                    list_path: list, 
                    list_des: list, 
                    list_htime: list, 
                    list_duration: list, 
                    category: list, 
                    mute: bool,
                    scenario_id: str,
                    file_type: str,
                    **kwargs):
        bucket_name = bucket_name.replace("_", "-")

        # print(list_path)
        list_path_new = []
        for i, file_name in enumerate(tqdm(list_path)):
            #----upload file to minio----
            if file_name:
                print("----upload to minio----")
                folder_name = f"{scenario_id}{os.sep}{collection_name}"
                res = self.upload_file2bucket(bucket_name=bucket_name, folder_name=folder_name, list_file_path=[file_name])
                if not res["success"]:
                    print(res["error"])
                    list_path_new.append("")
                    return res
                else:
                    list_path_new.append(os.path.join(folder_name, os.path.basename(file_name)))
            #////////////////////////////
            else:
                list_path_new.append("")
        self.update_status(self.cur, sess_id, "data", {}, 85, "pending")
        # print(list_path_new)
        
        #----upload dt to postgres----
        # self.cur.execute(f'''INSERT INTO {table_name} (v_id, description, description_scenes, paths, highlight_times, category) VALUES ('{os.path.basename(file_name)}','{description}', '{list_des}', '{list_path_new}', '{list_htime}', '{category}') ON CONFLICT (v_id) DO NOTHING''')
        print("----upload to postgres----")
        self.cur.execute(
            "INSERT INTO " + table_name + " (sender_id, v_id, v_name, root_path, overview, description_scenes, paths, highlight_times, durations, category, mute, file_type, scenario_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO NOTHING;",
            (sender_id, v_id, v_name, root_path, overview, str(list_des), str(list_path_new), str(list_htime), str(list_duration), str(category), mute, file_type, scenario_id)
        )
        #/////////////////////////////
        self.update_status(self.cur, sess_id, "data", {}, 90, "pending")
        
        #----upload vector data to qdrant----
        print("----upload to qdrant----")
        self.add_vector(collection_name=collection_name, v_id=v_id, v_name=v_name, root_path=root_path, overview=overview, list_path=list_path_new, list_des=list_des, list_htime=list_htime, list_duration=list_duration, category=category, mute=mute, scenario_id=scenario_id, group_id="group1")
        if not res["success"]:
            print(res["error"])
            return res
        #///////////////////////////////////
        self.update_status(self.cur, sess_id, "data", {}, 95, "pending")
        
        return {"success": True, "list_path_new": list_path_new}
        
if __name__=="__main__":
    dtw = DBWorker()
    
    collection_name = "mmv"
    bucket_name = "data_mmv"
    db_name = "mmv"
    table_name = "videos"
    scenario_name = "demo1"
    dtw.init_db(collection_name=collection_name, bucket_name=bucket_name, db_name=db_name, table_name=table_name)
    
    # dtw.upload_file2bucket(bucket_name=bucket_name, folder_name=f"{scenario_name}{os.sep}{collection_name}", list_file_path=["./data_test/abc.mp4"])
    
    # demo1 = {
    #     "opening_scene": "Quay toàn cảnh bên ngoài spa, làm nổi bật logo, bảng hiệu và không khí chào đón. Thể hiện rõ nhận diện thương hiệu với hình ảnh sáng sủa, sạch sẽ và thu hút.",
    #     "reception_scene": "Ghi lại khoảnh khắc lễ tân đón tiếp khách với nụ cười thân thiện. Không gian chuyên nghiệp nhưng gần gũi, tạo cảm giác thoải mái ngay từ lúc khách bước vào.",
    #     "consultation_scene": "Quay nhân viên đang tư vấn cho khách, trao đổi về nhu cầu làm đẹp và các dịch vụ. Nhấn mạnh sự lắng nghe chăm chú và phong cách tư vấn chuyên nghiệp, tận tình.",
    #     "service_scene": "Quay các dịch vụ như massage, chăm sóc da mặt, tắm trắng, xông hơi... Tập trung vào: Góc quay cận cảnh bàn tay nhẹ nhàng thao tác, Các thiết bị máy móc hiện đại đang vận hành, Làn da khách mịn màng, sáng khỏe. Tạo cảm giác về sự cao cấp, chuyên nghiệp và tinh tế trong dịch vụ",
    #     "interior_scene": "Quay toàn bộ các khu vực bên trong spa: phòng trị liệu, phòng thư giãn, khu trang điểm... Thể hiện một không gian yên tĩnh, sang trọng và sạch sẽ, mang lại cảm giác thư thái cho khách.",
    #     "staff_scene": "Ghi hình đội ngũ nhân viên chuyên nghiệp, thân thiện. Có thể quay cảnh nhân viên đang làm việc cùng nhau hoặc chụp ảnh nhóm thể hiện tinh thần đoàn kết và chuyên môn cao.",
    #     "customer_scene": "Quay cảnh khách hàng bày tỏ cảm xúc và sự hài lòng sau khi sử dụng dịch vụ. Tập trung vào biểu cảm tự nhiên, vui vẻ và những lời nhận xét chân thành",
    #     "product_scene": "Quay cận cảnh các sản phẩm chăm sóc da và làm đẹp được spa sử dụng. Làm nổi bật bao bì sản phẩm, thành phần và chất lượng, tạo sự tin tưởng và chuyên nghiệp",
    #     "closing_scene": "Hiển thị đầy đủ thông tin liên hệ, trang fanpage và các chương trình ưu đãi hiện có. Thiết kế hình ảnh rõ ràng, hấp dẫn, kêu gọi khách hàng theo dõi và đến trải nghiệm."
    # }
    
    # demo2 = {
    #     "opening_shot": "Cảnh quay tổng quan trụ sở công ty với logo nổi bật, nhân viên ra vào thể hiện môi trường chuyên nghiệp, sáng tạo.",
    #     "rnd_lab": "Cảnh phòng nghiên cứu và phát triển với các kỹ sư đang thử nghiệm và hiệu chỉnh camera AI trên nhiều thiết bị.",
    #     "product_demo": "Cảnh quay cận sản phẩm camera AI đang hoạt động, nhận diện khuôn mặt, phát hiện vật thể trong thời gian thực.",
    #     "ai_algorithm": "Cảnh minh họa quy trình xử lý dữ liệu AI, các dòng code, sơ đồ thuật toán, và dữ liệu huấn luyện trên màn hình máy tính.",
    #     "integration_scene": "Cảnh camera AI được lắp đặt trong các tình huống thực tế như nhà máy, cửa hàng, tòa nhà thông minh.",
    #     "client_testimonial": "Khách hàng chia sẻ trải nghiệm về việc sử dụng camera AI, nhấn mạnh tính năng nổi bật và hiệu quả mang lại.",
    #     "team_meeting": "Cuộc họp nhóm phát triển sản phẩm, trao đổi ý tưởng và chiến lược ra mắt thị trường.",
    #     "closing_scene": "Thông điệp thương hiệu kết thúc, kèm khẩu hiệu và thông tin liên hệ của công ty."
    # }
    # dtw.update_scenario(dtw.cur, "demo2", demo2)
    exit()
    
    # from libs.utils import MyException, check_folder_exist
    # dir_temp_video = f"{DIR}{os.sep}static{os.sep}temp"
    # check_folder_exist(dir_temp_video=dir_temp_video)
    
    v_id = "id_video.mp4"
    overview = "Video này trình bày hai phần nội dung chính liên quan đến lĩnh vực thiết kế. Phần đầu tiên cho thấy một nhóm các nhà thiết kế đang làm việc chăm chỉ trên một dự án, có thể là thiết kế nội thất hoặc kiến trúc, thể hiện sự tỉ mỉ và chuyên nghiệp trong quá trình sáng tạo và hợp tác. Phần thứ hai giới thiệu một không gian nội thất hiện đại và sang trọng, có thể là một spa hoặc phòng tắm cao cấp, với sự kết hợp hoàn hảo giữa các vật liệu tự nhiên và kiến trúc hiện đại, tạo ra một bầu không khí thư giãn và tinh tế. Tổng thể, video mang đến cái nhìn sâu sắc về quy trình thiết kế và không gian sống đẳng cấp."
    list_path = ["./src/static/temp/aaa/5.mp4"]
    list_des = ["test upload video 5"]
    list_htime = [0]
    category = ["other", "service", "staff"]
    # res = dtw.upload_data(collection_name=collection_name, bucket_name=bucket_name, v_id=v_id, overview=overview, list_path=list_path, list_des=list_des, list_htime=list_htime, category=category)
    
    # dtw.add_vector(collection_name=collection_name, v_id=v_id, v_name=v_id, root_path=list_path[0], overview=overview, list_path=list_path, list_des=list_des, list_htime=list_htime, category=category, group_id="group1")
    
    # dtw.retrieve(collection_name=collection_name, text_querys=["sự tỉ mỉ và chuyên nghiệp"], categories=["other"])
    
    
    data = {
        "3.mp4": {
            "overview": "Video cận cảnh quá trình cấy tóc thẩm mỹ tại MQ Spa, tập trung vào sự tỉ mỉ và chuyên nghiệp của kỹ thuật viên. Màu sắc tương phản giữa găng tay tím và da đầu tạo điểm nhấn thị giác.",
            "list_path": ["./src/static/videos_splitted/spa/3_splitted_0.mp4"]*9,
            "list_des": ["Video cận cảnh quá trình cấy tóc thẩm mỹ tại MQ Spa, tập trung vào sự tỉ mỉ và chuyên nghiệp của kỹ thuật viên. Màu sắc tương phản giữa găng tay tím và da đầu tạo điểm nhấn thị giác."]*9,
            "list_htime": [10]*9,
            "category": ["opening_scene", "reception_scene", "consultation_scene", 'service_scene', "interior_scene", "staff_scene", "customer_scene", "product_scene", "closing_scene"]
        },
        "2.mp4": {
            "overview": 'Video này giới thiệu dịch vụ massage tại MQ Spa, tập trung vào trải nghiệm thư giãn và chuyên nghiệp. Hình ảnh cận cảnh các động tác massage nhẹ nhàng, dầu massage bóng bẩy và không gian yên tĩnh tạo cảm giác thư thái, thu hút người xem muốn trải nghiệm dịch vụ.',
            "list_path": ["./src/static/short_videos/spa/2.mp4"]*9,
            "list_des": ['Video này giới thiệu dịch vụ massage tại MQ Spa, tập trung vào trải nghiệm thư giãn và chuyên nghiệp. Hình ảnh cận cảnh các động tác massage nhẹ nhàng, dầu massage bóng bẩy và không gian yên tĩnh tạo cảm giác thư thái, thu hút người xem muốn trải nghiệm dịch vụ.']*9,
            "list_htime": [10]*9,
            "category": ["opening_scene", "reception_scene", "consultation_scene", 'service_scene', "interior_scene", "staff_scene", "customer_scene", "product_scene", "closing_scene"]
        },
        "6.mp4": {
            "overview": 'Video giới thiệu về trải nghiệm thư giãn độc đáo tại MQ Spa, nơi khách hàng có thể tận hưởng liệu pháp floatation therapy trong một không gian yên tĩnh, ánh sáng dịu nhẹ, giúp giảm căng thẳng và tái tạo năng lượng. Video giới thiệu MQ Spa với hình ảnh một người phụ nữ đang thư giãn trong bồn tắm nổi, ánh sáng tím và xanh tạo cảm giác yên bình và thư thái. Sự tập trung vào trải nghiệm cá nhân và không gian spa sang trọng có thể thu hút sự chú ý của khán giả. Cảnh quay cận cảnh một người phụ nữ đang thư giãn trong không gian spa với ánh sáng dịu nhẹ màu hồng và xanh lam. Sự tập trung vào biểu cảm thanh thản và không gian yên bình tạo nên sự hấp dẫn, gợi cảm giác thư giãn và tái tạo năng lượng.',
            "list_path": ["./src/static/videos_splitted/spa/6_splitted_0.mp4", "./src/static/videos_splitted/spa/6_splitted_1.mp4", "./src/static/videos_splitted/spa/6_splitted_0.mp4"]*3,
            "list_des": ['Video giới thiệu về trải nghiệm thư giãn độc đáo tại MQ Spa, nơi khách hàng có thể tận hưởng liệu pháp floatation therapy trong một không gian yên tĩnh, ánh sáng dịu nhẹ, giúp giảm căng thẳng và tái tạo năng lượng.', 'Video giới thiệu MQ Spa với hình ảnh một người phụ nữ đang thư giãn trong bồn tắm nổi, ánh sáng tím và xanh tạo cảm giác yên bình và thư thái. Sự tập trung vào trải nghiệm cá nhân và không gian spa sang trọng có thể thu hút sự chú ý của khán giả.', 'Cảnh quay cận cảnh một người phụ nữ đang thư giãn trong không gian spa với ánh sáng dịu nhẹ màu hồng và xanh lam. Sự tập trung vào biểu cảm thanh thản và không gian yên bình tạo nên sự hấp dẫn, gợi cảm giác thư giãn và tái tạo năng lượng.']*3,
            "list_htime": [10]*9,
            "category": ["opening_scene", "reception_scene", "consultation_scene", 'service_scene', "interior_scene", "staff_scene", "customer_scene", "product_scene", "closing_scene"]
        },
        "1.mp4": {
            "overview": 'Video giới thiệu dịch vụ massage Shiatsu tại MQ Spa. Cảnh quay tập trung vào sự thư giãn và thoải mái mà khách hàng trải nghiệm trong quá trình massage, với ánh sáng dịu nhẹ và không gian yên tĩnh. Các động tác massage chuyên nghiệp được thể hiện, nhấn mạnh lợi ích về sức khỏe và làn da.',
            "list_path": ["./src/static/short_videos/spa/1.mp4"]*9,
            "list_des": ['Video giới thiệu dịch vụ massage Shiatsu tại MQ Spa. Cảnh quay tập trung vào sự thư giãn và thoải mái mà khách hàng trải nghiệm trong quá trình massage, với ánh sáng dịu nhẹ và không gian yên tĩnh. Các động tác massage chuyên nghiệp được thể hiện, nhấn mạnh lợi ích về sức khỏe và làn da.']*9,
            "list_htime": [10]*9,
            "category": ["opening_scene", "reception_scene", "consultation_scene", 'service_scene', "interior_scene", "staff_scene", "customer_scene", "product_scene", "closing_scene"]
        },
        "4.mp4": {
            "overview": 'Video giới thiệu về liệu trình spa tại MQ Spa, tập trung vào trải nghiệm thư giãn và chăm sóc da mặt. Góc quay từ trên xuống tạo cảm giác sang trọng và chuyên nghiệp, làm nổi bật sự thoải mái của khách hàng.',
            "list_path": ["./src/static/videos_splitted/spa/4_splitted_0.mp4"]*9,
            "list_des": ['Video giới thiệu về liệu trình spa tại MQ Spa, tập trung vào trải nghiệm thư giãn và chăm sóc da mặt. Góc quay từ trên xuống tạo cảm giác sang trọng và chuyên nghiệp, làm nổi bật sự thoải mái của khách hàng.']*9,
            "list_htime": [10]*9,
            "category": ["opening_scene", "reception_scene", "consultation_scene", 'service_scene', "interior_scene", "staff_scene", "customer_scene", "product_scene", "closing_scene"]
        },
        "5.mp4": {
            "overview": "Cảnh này giới thiệu 'Phòng Mưa' tại MQ Spa, một không gian độc đáo và thư giãn. Hiệu ứng mưa nhân tạo tạo ra một bầu không khí thanh bình và hấp dẫn, hứa hẹn một trải nghiệm spa khác biệt và đáng nhớ. Video này cho thấy cận cảnh quá trình trị liệu bùn khoáng tại MQ Spa, tập trung vào sự tỉ mỉ và chuyên nghiệp của kỹ thuật viên. Màu sắc tự nhiên của bùn khoáng kết hợp với ánh sáng dịu nhẹ tạo nên cảm giác thư giãn và sang trọng.",
            "list_path": ["./src/static/videos_splitted/spa/5_splitted_0.mp4", "./src/static/videos_splitted/spa/5_splitted_1.mp4", "./src/static/videos_splitted/spa/5_splitted_1.mp4"]*3,
            "list_des": ["Cảnh này giới thiệu 'Phòng Mưa' tại MQ Spa, một không gian độc đáo và thư giãn. Hiệu ứng mưa nhân tạo tạo ra một bầu không khí thanh bình và hấp dẫn, hứa hẹn một trải nghiệm spa khác biệt và đáng nhớ.", 'Video này cho thấy cận cảnh quá trình trị liệu bùn khoáng tại MQ Spa, tập trung vào sự tỉ mỉ và chuyên nghiệp của kỹ thuật viên. Màu sắc tự nhiên của bùn khoáng kết hợp với ánh sáng dịu nhẹ tạo nên cảm giác thư giãn và sang trọng.', 'Video này cho thấy cận cảnh quá trình trị liệu bùn khoáng tại MQ Spa, tập trung vào sự tỉ mỉ và chuyên nghiệp của kỹ thuật viên. Màu sắc tự nhiên của bùn khoáng kết hợp với ánh sáng dịu nhẹ tạo nên cảm giác thư giãn và sang trọng.']*3,
            "list_htime": [10]*9,
            "category": ["opening_scene", "reception_scene", "consultation_scene", 'service_scene', "interior_scene", "staff_scene", "customer_scene", "product_scene", "closing_scene"]
        },
        "7.mp4": {
            "overview": 'Video giới thiệu về MQ Spa, tập trung vào không gian sang trọng và dịch vụ chăm sóc sức khỏe toàn diện. Sự tương tác giữa hai người phụ nữ tạo cảm giác gần gũi, tin cậy, khuyến khích người xem tìm hiểu thêm về spa. Video này giới thiệu trải nghiệm tại MQ Spa, nơi khách hàng được tận hưởng các liệu pháp làm đẹp và thư giãn hiện đại. Điểm nhấn là công nghệ tiên tiến và sự thoải mái, sang trọng trong không gian spa. Video này giới thiệu các dịch vụ đa dạng của MQ Spa, từ phục hồi chấn thương, điều trị các bệnh về da đến giảm cân. Điểm hấp dẫn là sự tập trung vào các vấn đề sức khỏe cụ thể và giải pháp mà spa cung cấp. Video giới thiệu về MQ Spa, tập trung vào trải nghiệm thư giãn và sang trọng mà spa mang lại. Bối cảnh tươi sáng, hiện đại và người đại diện thương hiệu thân thiện tạo cảm giác gần gũi, thu hút.',
            "list_path": ["./src/static/videos_splitted/spa/7_splitted_0.mp4", "./src/static/videos_splitted/spa/7_splitted_1.mp4", "./src/static/videos_splitted/spa/7_splitted_2.mp4", "./src/static/videos_splitted/spa/7_splitted_3.mp4"]*2 + ["./src/static/videos_splitted/spa/7_splitted_3.mp4"],
            "list_des": ['Video giới thiệu về MQ Spa, tập trung vào không gian sang trọng và dịch vụ chăm sóc sức khỏe toàn diện. Sự tương tác giữa hai người phụ nữ tạo cảm giác gần gũi, tin cậy, khuyến khích người xem tìm hiểu thêm về spa.', 'Video này giới thiệu trải nghiệm tại MQ Spa, nơi khách hàng được tận hưởng các liệu pháp làm đẹp và thư giãn hiện đại. Điểm nhấn là công nghệ tiên tiến và sự thoải mái, sang trọng trong không gian spa.', 'Video này giới thiệu các dịch vụ đa dạng của MQ Spa, từ phục hồi chấn thương, điều trị các bệnh về da đến giảm cân. Điểm hấp dẫn là sự tập trung vào các vấn đề sức khỏe cụ thể và giải pháp mà spa cung cấp.', 'Video giới thiệu về MQ Spa, tập trung vào trải nghiệm thư giãn và sang trọng mà spa mang lại. Bối cảnh tươi sáng, hiện đại và người đại diện thương hiệu thân thiện tạo cảm giác gần gũi, thu hút.']*2 + ['Video giới thiệu về MQ Spa, tập trung vào trải nghiệm thư giãn và sang trọng mà spa mang lại. Bối cảnh tươi sáng, hiện đại và người đại diện thương hiệu thân thiện tạo cảm giác gần gũi, thu hút.'],
            "list_htime": [10]*9,
            "category": ["opening_scene", "reception_scene", "consultation_scene", 'service_scene', "interior_scene", "staff_scene", "customer_scene", "product_scene", "closing_scene"]
        },
    }
    
    # for k, v in data.items():
    #     dtw.add_vector(collection_name=collection_name, v_id=k, v_name=v_id, root_path=list_path[0], overview=v["overview"], list_path=v["list_path"], list_des=v["list_des"], list_htime=v["list_htime"], category=v["category"], group_id="group1")
        
    dtw.retrieve(collection_name=collection_name, text_querys=["Màu sắc tương phản giữa găng tay tím và da đầu tạo điểm nhấn thị giác", "dầu massage bóng bẩy và không gian yên tĩnh tạo cảm giác thư thái", "liệu pháp floatation therapy trong một không gian yên tĩnh, ánh sáng dịu nhẹ", "dịch vụ massage Shiatsu tại MQ Spa", "tập trung vào trải nghiệm thư giãn và chăm sóc da mặt", "'Phòng Mưa' tại MQ Spa, một không gian độc đáo và thư giãn", "Sự tương tác giữa hai người phụ nữ tạo cảm giác gần gũi, tin cậy, khuyến khích người xem tìm hiểu thêm về spa", "các dịch vụ đa dạng của MQ Spa, từ phục hồi chấn thương, điều trị các bệnh về da đến giảm cân", "không gian spa với ánh sáng dịu nhẹ màu hồng và xanh lam"], categories=["opening_scene", "reception_scene", "consultation_scene", 'service_scene', "interior_scene", "staff_scene", "customer_scene", "product_scene", "closing_scene"])
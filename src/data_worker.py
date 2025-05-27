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
import psycopg2
import traceback
from tqdm import tqdm
from minio import Minio
from datetime import datetime
from urllib.parse import urlparse 
from confluent_kafka.admin import NewTopic
from redisvl.utils.vectorize import HFTextVectorizer
from redisvl.extensions.llmcache import SemanticCache
from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models as qmodels

from libs.utils import MyException

class DBWorker(object):
    def __init__(self, 
                 qdrant_url="http://localhost:7000", 
                 minio_url="localhost:9000", 
                 redis_url="redis://:root@localhost:6669", 
                 psyconpg_url="http://localhost:6670",
                 sparse_model_path=f"{ROOT}/weights/all_miniLM_L6_v2_with_attentions", 
                 dense_model_path=f"{ROOT}/weights/Vietnamese_Embedding", 
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
                                access_key="demo",
                                secret_key="demo123456",
                                secure=False,
                            )
        
        #----setup postgreSQL----
        url_pg = urlparse(psyconpg_url)
        conn = psycopg2.connect(dbname="mmv",
                                host=url_pg.hostname, 
                                port=url_pg.port, 
                                user='demo', 
                                password='demo123456')
        self.cur = conn.cursor()
        conn.set_session(autocommit = True)
        
        #----setup cache redis----
        if cache:
            redis_ttl = 900
            vectorizer = HFTextVectorizer(model=dense_model_path)
            self.llmcache = SemanticCache(name="llmcache", ttl=redis_ttl, redis_url=redis_url, distance_threshold=0.2, vectorizer=vectorizer, overwrite=True)
           
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
    
    def add_vector(self, collection_name: str, v_id: str, overview: str, category: str="", group_id: str="group1"):
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
                        # "index": idx,
                        "name": v_id,
                        "description": overview,
                        "category": category,
                        "datetime": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                        "timestamp": time.time(),
                        "group_id": group_id
                    },
                ),
            ], 
            batch_size=64,
            parallel=4,
            max_retries=3,
            # shard_key_selector=group_id,
        )
        return {"success": True}
    
    def retrieve(self, collection_name: str, text_querys: list[str], schema_filter: dict=None, n_result: int=5, similarity_threshold: float=0.5):
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
        
        result = []
        score = []
        index = []
        name = []
        for i in range(len(text_querys)):
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
            # [(result.append(hit.payload), score.append(hit.score), name.append(hit.payload["name"])) for hit in query_results if hit.score>similarity_threshold]
            if query_results[0].score > similarity_threshold:
                name.append(query_results[0].payload["name"])
                score.append(query_results[0].score)
            else:
                name.append("")
                score.append(0)
        print(name)
        print(score)
        return {"success": True, "v_id": name}
            
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
        objects_exist = [os.path.basename(x.object_name) for x in objects_exist]
        for i, fp in enumerate(list_file_path):
            fn = os.path.basename(fp)
            if fn in objects_exist:
                # LOGGER_RETRIEVAL.info(f"File {fn} exists!")
                continue
            self.minio_client.fput_object(
                bucket_name=bucket_name, object_name=os.path.join(folder_name, fn), file_path=fp,
            )
        return {"success": True}

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
          
    # def create_pg_db(self, db_name: str):
    #     self.cur.execute(f'''CREATE DATABASE {db_name}''')
    #     return {"success": True}
    
    # def delete_pg_db(self, db_name: str):
    #     self.cur.execute(f'''DROP DATABASE IF EXISTS {db_name}''')
    #     return {"success": True}
            
    # def create_table(self, tb_name: str, tb_scheme: str):
    #     self.cur.execute(f'''CREATE TABLE IF NOT EXISTS {tb_name}({tb_scheme})''')
    #     return {"success": True}
    
    # def delete_table(self, tb_name: str):
    #     self.cur.execute(f'''DROP TABLE IF EXISTS {tb_name}''')
    #     return {"success": True}
    
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
    def init_db(self, collection_name: str, bucket_name: str, db_name: str):
        #----create db qdrant----
        res = self.delete_collection(collection_name=collection_name)
        if not res["success"]:
            print(res["error"])
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
        self.cur.execute(f'''DROP TABLE IF EXISTS videos''')
        self.cur.execute(f'''CREATE TABLE videos(
                                id SERIAL PRIMARY KEY,
                                v_id VARCHAR(255) NOT NULL,
                                overview TEXT NOT NULL,
                                description_scenes TEXT NOT NULL,
                                paths VARCHAR(255) NOT NULL,
                                highlight_times TEXT NOT NULL,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                category VARCHAR(255) NOT NULL,
                                UNIQUE (v_id)
                        )''')
        #//////////////////////////
        return {"success": True}
    
    @MyException()        
    def upload_data(self, collection_name: str, bucket_name: str, v_id: str, overview: str, list_path: list, list_des: list, list_htime: list, category: str):
        bucket_name = bucket_name.replace("_", "-")

        # print(list_path)
        list_path_new = []
        for i, file_name in enumerate(tqdm(list_path)):
            #----upload file to minio----
            if file_name:
                res = self.upload_file2bucket(bucket_name=bucket_name, folder_name=collection_name, list_file_path=[file_name])
                if not res["success"]:
                    print(res["error"])
                    return res
                else:
                    list_path_new.append(os.path.join(collection_name, os.path.basename(file_name)))
            #////////////////////////////
            
        #----upload vector data to qdrant----
        dtw.add_vector(collection_name=collection_name, v_id=v_id, overview=overview, category=category, group_id="group1")
        if not res["success"]:
            print(res["error"])
            return res
        #///////////////////////////////////

        # print(list_path_new)
        #----upload dt to postgres----
        # self.cur.execute(f'''INSERT INTO videos (v_id, description, description_scenes, paths, highlight_times, category) VALUES ('{os.path.basename(file_name)}','{description}', '{list_des}', '{list_path_new}', '{list_htime}', '{category}') ON CONFLICT (v_id) DO NOTHING''')
        self.cur.execute(
            "INSERT INTO videos (v_id, overview, description_scenes, paths, highlight_times, category) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO NOTHING;",
            (v_id, overview, str(list_des), str(list_path_new), str(list_htime), category)
        )
        #/////////////////////////////
        return {"success": True}
        
if __name__=="__main__":
    dtw = DBWorker()
    
    collection_name = "mmv"
    bucket_name = "data_mmv"
    db_name = "mmv"
    # dtw.init_db(collection_name=collection_name, bucket_name=bucket_name, db_name=db_name)
    
    # from libs.utils import MyException, check_folder_exist
    # dir_temp_video = f"{DIR}{os.sep}static{os.sep}temp"
    # check_folder_exist(dir_temp_video=dir_temp_video)
    
    v_id = "id_video.mp4"
    overview = "Video này trình bày hai phần nội dung chính liên quan đến lĩnh vực thiết kế. Phần đầu tiên cho thấy một nhóm các nhà thiết kế đang làm việc chăm chỉ trên một dự án, có thể là thiết kế nội thất hoặc kiến trúc, thể hiện sự tỉ mỉ và chuyên nghiệp trong quá trình sáng tạo và hợp tác. Phần thứ hai giới thiệu một không gian nội thất hiện đại và sang trọng, có thể là một spa hoặc phòng tắm cao cấp, với sự kết hợp hoàn hảo giữa các vật liệu tự nhiên và kiến trúc hiện đại, tạo ra một bầu không khí thư giãn và tinh tế. Tổng thể, video mang đến cái nhìn sâu sắc về quy trình thiết kế và không gian sống đẳng cấp."
    list_path = ["./src/static/temp/aaa/5.mp4"]
    list_des = ["test upload video 5"]
    list_htime = [0]
    category = "other"
    # res = dtw.upload_data(collection_name=collection_name, bucket_name=bucket_name, v_id=v_id, overview=overview, list_path=list_path, list_des=list_des, list_htime=list_htime, category=category)
    
    # dtw.add_vector(collection_name=collection_name, v_id=v_id, overview=overview, category=category, group_id="group1")
    
    dtw.retrieve(collection_name=collection_name, text_querys=["sự tỉ mỉ và chuyên nghiệp"])
import redis
import numpy as np
from redis.commands.search.field import VectorField, TextField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType

# Connect to Redis Stack
r = redis.Redis(host='localhost', port=6669, db=0, password="RedisAuth")

# Drop old index if exists
#try:
r_search = r.ft("idx_test")
#except:
 #   pass

# Create RediSearch index with a vector field
dim = 3  # vector dimension
index_def = IndexDefinition(prefix=["doc:"], index_type=IndexType.HASH)

r_search.create_index(
    [
        TextField("label"),  # optional metadata field
        VectorField("vec", "FLAT", {  # also supports HNSW for ANN
            "TYPE": "FLOAT32",
            "DIM": dim,
            "DISTANCE_METRIC": "COSINE",  # or L2 / IP
        })
    ],
    definition=index_def
)

# Insert sample vectors
vec1 = np.array([0.1, 0.2, 0.3], dtype=np.float32).tobytes()
vec2 = np.array([0.2, 0.1, 0.4], dtype=np.float32).tobytes()

r.hset("doc:1", mapping={"label": "first", "vec": vec1})
r.hset("doc:2", mapping={"label": "second", "vec": vec2})

# Query with a vector (find nearest neighbors)
query_vector = np.array([0.1, 0.2, 0.25], dtype=np.float32).tobytes()
query = f"*=>[KNN 2 @vec $vec AS score]"  # find top 2 closest vectors
params = {"vec": query_vector}

results = r.ft("vec_idx").search(query, query_params=params)

# Print results
for doc in results.docs:
    print(f"id: {doc.id}, label: {doc.label}, score: {doc.score}")


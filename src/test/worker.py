import os
import asyncio 
import redis
from rq import Worker, Queue, Connection
import multiprocessing
# import queue

# os.system("service redis-server start")

listen = ['default']

redis_url = os.getenv('REDISTOGO_URL', 'redis://:RedisAuth@localhost:6669')
# redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6669')

# conn = redis.from_url(redis_url)
conn = redis.Redis(
    host='localhost',     # or your Redis server IP/domain
    port=6669,            # default Redis port
    db=0,                 # default DB index
    # decode_responses=True,  # to get strings instead of bytes
    password="RedisAuth",
)

# q_output = queue.Queue(maxsize=1)
# q_com = queue.Queue(maxsize=1)

def start_worker(name_worker):
    q = Queue(name_worker, connection=conn)
    Worker([q], name=name_worker, connection=conn).work()

async def create_task_worker(name_worker: str):
    with Connection(conn):
        #worker = Worker(list(map(Queue, listen)))
        #worker.work()

        # NUM_WORKERS = multiprocessing.cpu_count()
        NUM_WORKERS = 1
        print("NUM_WORKERS: ", NUM_WORKERS)
        procs = []
        for i in range(NUM_WORKERS):
            proc = multiprocessing.Process(target=start_worker, args=(name_worker,))
            procs.append(proc)
            proc.start()
        print(procs)
        
# async def create_task_worker(self, consumer_id):
#     def start_worker():
#         q = Queue(f"process_{consumer_id}", connection=self.redis_conn)
#         Worker([q], connection=self.redis_conn).work()
    
#     try:
#         with Connection(self.redis_conn):
#             # NUM_WORKERS = multiprocessing.cpu_count()
#             # NUM_WORKERS = 1
#             # print("NUM_WORKERS: ", NUM_WORKERS)
#             # procs = []
#             # for i in range(NUM_WORKERS):
#             proc = multiprocessing.Process(target=start_worker)
#             # procs.append(proc)
#             proc.start()
#             # print(procs)
#             print(proc)
#     except asyncio.CancelledError:
#         print(f"Task worker is shutting down")
#         self.redis_conn.close()
#     except Exception as e:
#         tb_str = traceback.format_exc()
#         print(f"Error in task worker: {tb_str}")
#         await asyncio.sleep(1)  # Prevent tight loop in case of errors

def run_async_in_thread(name_worker):
    asyncio.run(create_task_worker(name_worker))

if __name__ == '__main__':
    import threading
    # with Connection(conn):
    #     #worker = Worker(list(map(Queue, listen)))
    #     #worker.work()

    #     # NUM_WORKERS = multiprocessing.cpu_count()
    #     NUM_WORKERS = 1
    #     print("NUM_WORKERS: ", NUM_WORKERS)
    #     procs = []
    #     for i in range(NUM_WORKERS):
    #         proc = multiprocessing.Process(target=start_worker)
    #         procs.append(proc)
    #         proc.start()
    #     print(procs)
    
    # Create and start thread
    for i in range(2):
        thread = threading.Thread(target=run_async_in_thread, args=(f"process_data_{i}", ))
        thread.start()
        thread.join()
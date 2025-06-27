from celery import Celery
import time
from celery.result import AsyncResult
from celery.events.state import State
from celery.events import EventReceiver
# from celery.bin.worker import worker as celery_worker
from celery.contrib.abortable import AbortableTask
import asyncio
from kombu import Queue
from multiprocessing import Process

app = Celery('test3', broker='redis://:RedisAuth@localhost:6669/0', backend='redis://:RedisAuth@localhost:6669/1')
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    result_backend='redis://:RedisAuth@localhost:6669/1',
    task_track_started=True,
)
# app.conf.task_queues = (
#     Queue('process_data_0'),
#     Queue('process_data_1'),
#     # Queue('process_data_2'),
# )
# app.conf.task_routes = {
#     'tasks.run_test': {'queue': 'process_data_0'},
#     'tasks.add': {'queue': 'process_data_1'},
# }

@app.task(
    bind=True,
    queue="process_data_0",
    base=AbortableTask,
    acks_late=True, max_retries=10, time_limit=31536000
)
def run_test(self, name):
    stop_flag = True
    print(f"----running: {name}")
    while stop_flag:
        for i in range(10):
            print("running")
            time.sleep(2)
            if i == 10:
                stop_flag = False
        break
    return name



@app.task(
    bind=True,
    queue="process_data_1",
    base=AbortableTask,
    acks_late=True, max_retries=10, time_limit=31536000
)
def add(self, x, y):
    return x + y
            
# job_id = "abc1"
# result = run_test.apply_async(args=[job_id])
# print(result)

# task_id = "f067fc1d-e127-4cc0-a881-f7069a7856c6"
# result = AsyncResult(task_id, app=app)
# print(result)
# print(result.state)

# inspect = app.control.inspect()
# active_tasks = inspect.active()
# print(active_tasks)

# # Get scheduled tasks
# scheduled = inspect.scheduled()
# print(scheduled)

# reserved = inspect.reserved()
# print(reserved)

# stats = inspect.stats()
# print(stats)

# registered = inspect.registered()
# print(registered)

# result = app.control.purge()
# print(result)

def start_worker(name):

    options = [
        'worker',
        '--loglevel=INFO',
        '--concurrency=1',
        '--pool=prefork',
        f'--queues={name}',  # Optional: specify queues
    ]

    app.worker_main(argv=options)

if __name__=="__main__":
    # start_worker(f"process_data_0,process_data_1")
    process = []
    for i in range(2):
        # thread = threading.Thread(target=start_worker, args=(f"process_data_{i}", ))
        # thread.start()
        # thread.join()
        w = Process(target=start_worker, args=(f"process_data_{i}",))
        w.start()
        process.append(w)
        
    for p in process:
        p.join()
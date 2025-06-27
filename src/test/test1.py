import os
import time
import redis
from rq import Worker, Queue
from test2 import run_test
from rq.command import send_stop_job_command
from rq.job import Job
from rq.exceptions import NoSuchJobError

# def run_test():
#     stop_flag = True
#     while stop_flag:
#         # for i in range(100):
#         print("running")
#         time.sleep(2)
#             # if i == 10:
#             #     stop_flag = False
            
if __name__=="__main__":
    redis_url = os.getenv('REDISTOGO_URL', 'redis://:RedisAuth@localhost:6669')
    conn = redis.from_url(redis_url)
    q = Queue("process_data_0", connection=conn)

    job_id = "abc1"
    
    job = q.fetch_job(job_id)
    print(job)
    # if job is None:
    #     job = q.enqueue(f=run_test, args=(job_id,), timeout=600, failure_ttl=600, job_id=job_id)
    #     print(job.id)
    # else:
    #     print(f"Job '{job_id}' is already in queue or running.")
        
    if job is None:
        print(f"----Job {job_id} is not exists")
    else:
        print(job.get_status())
        if job.get_status() == 'started':
            print(f"----Interrupt job {job_id}")
            send_stop_job_command(conn, job_id)
            job.delete()
        elif job.get_status() == 'queued':
            print(f"----Delete job {job_id}")
            job.delete()
        elif job.get_status() == 'stopped':
            print(f"----Delete stopped job {job_id}")
            job.delete()
        elif job.get_status() == 'failed':
            print(f"----Delete failed job {job_id}")
            job.delete()
            
            
            
            
    # try:
    #     job = Job.fetch(job_id, connection=conn)
    #     print(job)
    #     if not job.is_finished:
    #         print(f"Job '{job_id}' is already in queue or running.")
    # except NoSuchJobError:
    #     job = q.enqueue_call(func=run_test, args=(job_id,), timeout=600, failure_ttl=600, job_id=job_id)
    #     print(job.id)
        
    # try:
    #     job = Job.fetch(job_id, connection=conn)
    #     print(job.get_status())
    #     if job.get_status() == 'started':
    #         print(f"----Interrupt job {job_id}")
    #         send_stop_job_command(conn, job_id)
    #         job.delete()
    #     elif job.get_status() == 'queued':
    #         print(f"----Delete job {job_id}")
    #         job.delete()
    #     elif job.get_status() == 'stopped':
    #         print(f"----Delete stopped job {job_id}")
    #         job.delete()
    # except NoSuchJobError:
    #     print(f"----Job {job_id} is not exists")
from test3 import run_test, app, add
from celery.result import AsyncResult
import redis
import os

job_id = "abc4"

# redis_url = os.getenv('REDISTOGO_URL', 'redis://:RedisAuth@localhost:6669')
# conn = redis.from_url(redis_url)
# print(conn.get(f"revoke:{job_id}"))
# exit()


result = run_test.apply_async(args=[job_id], task_id = job_id)
# result = add.apply_async(args=[4, 6], task_id = job_id)  # Run add asynchronously
# print(result)

result = run_test.AsyncResult(job_id)
print(result)
print(result.state)
# result.revoke(terminate=True)
if result.state == "SUCCESS":
    print("delete")
    # Revoke the task (soft revoke)
    # result.revoke(terminate=True, signal='SIGTERM')
    result.forget()

inspect = app.control.inspect()
# active_tasks = inspect.active()
# print(active_tasks)

# # Get scheduled tasks
# scheduled = inspect.scheduled()
# print(scheduled)

# result = app.control.purge()
# print(result)

reserved = inspect.reserved()       # Tasks reserved by workers (in memory)
print(reserved)
list_task_waiting = [i['id'] for i in reserved["celery@mq"]]
if result.state == "PENDING" and job_id not in list_task_waiting:
    run_test.apply_async(args=[job_id], task_id = job_id)

# print(result.get(timeout=10))



'''
PENDING (waiting to be executed)

STARTED (running)

SUCCESS (finished successfully)

FAILURE (error occurred)

RETRY (retrying after failure)
'''
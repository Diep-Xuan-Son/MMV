import json
import uuid
import uvicorn
import aiofiles
from itertools import chain
from dataclasses import dataclass, field
from string import ascii_letters, digits, punctuation

from app import *
from langchain_core.prompts import ChatPromptTemplate
from prompts import PROMPT_CHOOSE_TOOL, PROMPT_ANSWER, PROMPT_GET_MEMORY
from langchain_core.messages import HumanMessage, SystemMessage
from models import Topic, ProduceInput, InputDataWorker, InputQueryWorker, Status, VideoId, field

@app.post("/api/uploadData")
@HTTPException() 
async def uploadData(inputs: ProduceInput = Depends(ProduceInput), video_file: UploadFile = File(...)):
    MULTIW.cur.execute("SELECT DISTINCT array_agg(session_id) FROM tasks;")
    list_session_id = MULTIW.cur.fetchone()[0]
    if list_session_id is not None:
        if inputs.sess_id in list_session_id:
            return JSONResponse(status_code=409, content=str(f"The session_id is duplicated!"))
    
    v_id = f"{uuid.uuid4()}_{round(time.time())}".replace('-','_')
    
    path_uid = os.path.join(PATH_TEMP, inputs.sess_id)
    check_folder_exist(path_uid=path_uid)
    # path_file = f"{path_uid}{os.sep}{video_file.filename}"
    path_file = f"{path_uid}{os.sep}{v_id}.{video_file.filename.split('.')[1]}"
    # if os.path.exists(path_file):
    #     return JSONResponse(status_code=500, content=f"File {video_file.filename} is processing")
    
    async with aiofiles.open(path_file, 'wb') as out_file:
        # while chunk := await video_file.read(1024 * 1024):  # 1 MB at a time
        while True:
            chunk = await video_file.read(1024 * 1024)
            if not chunk:
                break
            await out_file.write(chunk)
    
    duration = await MULTIW.VM.vew.get_duration(path_file)
    name_v = inputs.name if inputs.name else ""
    producer = app.state.producer
    if duration > 600:
        n_video_10m = int(duration//600)
        for i in range(n_video_10m):
            name_v_precut = f"{name_v}_{i}" if name_v else ""
            output_precut_path = f"{os.path.splitext(path_file)[0]}_precut_{i}{os.path.splitext(path_file)[1]}"
            await MULTIW.VM.vew.split(u_id=inputs.sess_id, start_time=i*600, duration=600, video_input_path=path_file, output_path=output_precut_path, mute=False, fast=True)
            # Create a Kafka producer instance
            message = InputDataWorker(sess_id=inputs.sess_id, v_id=v_id, name=name_v_precut, path_file=output_precut_path, overview=inputs.overview, category=inputs.category)
            await producer.send_and_wait(
                inputs.topic_name,
                value=message.__dict__,
                key=message.sess_id.encode() if message.sess_id else None
            )
    
        if duration - n_video_10m*600 > 60:
            name_v = f"{name_v}_{n_video_10m}" if name_v else ""
            output_precut_path = f"{os.path.splitext(path_file)[0]}_precut_{n_video_10m}{os.path.splitext(path_file)[1]}"
            await MULTIW.VM.vew.split(u_id=inputs.sess_id, start_time=n_video_10m*600, duration=duration - n_video_10m*600, video_input_path=path_file, output_path=output_precut_path, mute=False, fast=True)
            if os.path.exists(path_file):
                os.remove(path_file)
            path_file = output_precut_path
    
    # Create a Kafka producer instance
    message = InputDataWorker(sess_id=inputs.sess_id, v_id=v_id, name=name_v, path_file=path_file, overview=inputs.overview, category=inputs.category, mute=inputs.mute)
    await producer.send_and_wait(
        inputs.topic_name,
        value=message.__dict__,
        key=message.sess_id.encode() if message.sess_id else None
    )
    MULTIW.VM.dataw.update_status(MULTIW.cur, message.sess_id, "data", {}, 0, "pending")
    return JSONResponse(status_code=201, content=str(f"Message delivered to {inputs.topic_name}"))

@app.post("/api/createVideo")
@HTTPException() 
async def createVideo(inputs: InputQueryWorker = Body(...)):
    MULTIW.cur.execute("SELECT DISTINCT array_agg(session_id) FROM tasks;")
    list_session_id = MULTIW.cur.fetchone()[0]
    if list_session_id is not None:
        if inputs.sess_id in list_session_id:
            return JSONResponse(status_code=409, content=str(f"The session_id is duplicated!"))
    
    value = inputs.__dict__
    producer = app.state.producer
    await producer.send_and_wait(
        Config.TOPIC_QUERY,
        value=value,
        key=inputs.sess_id.encode() if inputs.sess_id else None
    )
    MULTIW.VM.dataw.update_status(MULTIW.cur, inputs.sess_id, "query", {}, 0, "pending")
    return JSONResponse(status_code=201, content=str(f"Message delivered to {Config.TOPIC_QUERY}"))

@app.post("/api/getStatus")
@HTTPException() 
async def getStatus(inputs: Status = Body(...)):
    columns = ["session_id", "type", "result", "percent", "status"]
    res = MULTIW.VM.dataw.get_status(MULTIW.cur, columns, inputs.sess_id)
    if not res["success"]:
        return JSONResponse(status_code=404, content="The session ID not found!")
    return JSONResponse(status_code=200, content=res["result"])

# @app.post("/api/interruptTask")
# @HTTPException() 
# async def interruptTask(inputs: Status = Body(Status)):  # Use this when task is running (percent > 0)
#     columns = ["result", "percent", "status"]
#     num_try = 0
#     res = MULTIW.VM.dataw.get_status(MULTIW.cur, columns, inputs.sess_id)
#     if res["success"]:
#         if res["result"]["status"] == "pending" and res["result"]["percent"] != "0":
#             MULTIW.VM.dataw.update_status(MULTIW.cur, inputs.sess_id, "", {}, 0, "interrupted")
#             MULTIW.VM.is_making_mv = False
#             MULTIW.VM.is_processing_data = False
#             while True:
#                 res = MULTIW.VM.dataw.get_status(MULTIW.cur, columns, inputs.sess_id)
#                 if res["success"]:
#                     if res["result"]["status"] == "deleted":
#                         delete_folder_exist(*res["result"]["result"]["local_path_delete"])
#                         MULTIW.VM.dataw.delete_file_bucket(bucket_name=Config.BUCKET_NAME, folder_name=Config.COLLECTION_NAME, list_file_name=res["result"]["result"]["minio_path_delete"])
#                         MULTIW.VM.dataw.delete_vector(collection_name=Config.COLLECTION_NAME, list_v_id=res["result"]["result"]["v_id_delete"])
#                         break
#                 await asyncio.sleep(1)
#                 num_try += 1
#                 if num_try > 60:
#                     break
            
#     MULTIW.VM.dataw.cur.execute(
#         "DELETE FROM tasks WHERE session_id = %s;",
#         (inputs.sess_id,)
#     )
#     path_uid = os.path.join(PATH_TEMP, inputs.sess_id)
#     delete_folder_exist(path_uid)
#     return JSONResponse(status_code=200, content=f"Task {inputs.sess_id} has been interrupted!")

@app.post("/api/deleteTask")
@HTTPException() 
async def deleteTask(inputs: Status = Body(...)): # Use this when task done or percent of task is 0
    columns = ["result", "percent", "status"]
    num_try = 0
    res = MULTIW.VM.dataw.get_status(MULTIW.cur, columns, inputs.sess_id)
    if res["success"]:
        if res["result"]["status"] == "pending" and res["result"]["percent"] != "0":
            MULTIW.VM.dataw.update_status(MULTIW.cur, inputs.sess_id, "", {}, 0, "interrupted")
            MULTIW.VM.is_making_mv = False
            MULTIW.VM.is_processing_data = False
            while True:
                res = MULTIW.VM.dataw.get_status(MULTIW.cur, columns, inputs.sess_id)
                if res["success"]:
                    if res["result"]["status"] == "deleted":
                        delete_folder_exist(*res["result"]["result"]["local_path_delete"])
                        MULTIW.VM.dataw.delete_file_bucket(bucket_name=Config.BUCKET_NAME, folder_name=Config.COLLECTION_NAME, list_file_name=res["result"]["result"]["minio_path_delete"])
                        MULTIW.VM.dataw.delete_vector(collection_name=Config.COLLECTION_NAME, list_v_id=res["result"]["result"]["v_id_delete"])
                        break
                await asyncio.sleep(1)
                num_try += 1
                if num_try > 60:
                    break
            
    MULTIW.VM.dataw.cur.execute(
        "DELETE FROM tasks WHERE session_id = %s;",
        (inputs.sess_id,)
    )
    path_uid = os.path.join(PATH_TEMP, inputs.sess_id)
    delete_folder_exist(path_uid)
    return JSONResponse(status_code=200, content=f"Task {inputs.sess_id} has been deleted!")

@app.post("/api/deleteVideo")
@HTTPException() 
async def deleteVideo(inputs: VideoId = Body(...)):
    print(inputs)
    columns = ["root_path", "paths"]
    res = MULTIW.VM.dataw.get_row(MULTIW.cur, inputs.table_name, columns, inputs.v_ids)
    if res["success"]:
        list_paths = [eval(s) for s in res["result"]["paths"]]
        list_paths = list(chain.from_iterable(list_paths))
        # minio_path_delete = list_paths + res["result"]["root_path"]
        MULTIW.VM.dataw.delete_file_bucket(bucket_name=Config.BUCKET_NAME, folder_name=Config.COLLECTION_NAME, list_file_name=list_paths)
        MULTIW.VM.dataw.delete_file_bucket(bucket_name=Config.BUCKET_NAME, folder_name=f"{Config.COLLECTION_NAME}_backup", list_file_name=res["result"]["root_path"])
        MULTIW.VM.dataw.delete_vector(collection_name=Config.COLLECTION_NAME, list_v_id=inputs.v_ids)
        
        MULTIW.VM.dataw.cur.execute(
            f"DELETE FROM {inputs.table_name} WHERE v_id = ANY(%s);",
            (inputs.v_ids,)
        )
    else:
        return JSONResponse(status_code=404, content=res["error"])
    return JSONResponse(status_code=200, content=f"Video {str(inputs.v_ids).strip('[]')} has been deleted!")

@app.post("/api/checkCreateVideo")
@HTTPException() 
async def checkCreateVideo(inputs: InputQueryWorker = Body(...)):
    old_memory = []
    if MULTIW.VM.dataw.redisClient.exists(inputs.sess_id):
        old_memory = json.loads(MULTIW.VM.dataw.redisClient.hget(inputs.sess_id, MULTIW.VM.dataw.dbmemory_name))
    print(f"----old_memory: {old_memory}")
    print(inputs.query)
    print(inputs.sess_id)
    #-------------------------------------------------------
    def OutputStructured(BaseModel):
        """Format the response as JSON including the response of chatbot, with key is 'tool'"""
        # response: str = field(description="the response of chatbot to answer the user's query")
        # create_video: bool = field(description="the flag to check creating video or not")
            
    prompt = PROMPT_CHOOSE_TOOL
    structured_output = MULTIW.VM.openai.with_structured_output(OutputStructured)
    chat_prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content="You are a customer assistant."),
            HumanMessage(content=prompt.format(query=inputs.query, memory=old_memory))
        ]
    )
    chain = chat_prompt | structured_output 
    result_tool = chain.invoke({})
    print(result_tool)
    #/////////////////////////////////////////////////////////    
    
    #-------------------------------------------------------
    def OutputStructured1(BaseModel):
        """Format the response as JSON including the response of chatbot, with keys are 'response' and 'new_query'"""
            
    prompt = PROMPT_ANSWER
    structured_output = MULTIW.VM.openai.with_structured_output(OutputStructured1)
    chat_prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content="You are a customer assistant."),
            HumanMessage(content=prompt.format(query=inputs.query, memory=old_memory))
        ]
    )
    chain = chat_prompt | structured_output 
    result = chain.invoke({})
    print(result)
    if result_tool["tool"] == "create_video":
        result["response"] += "Tôi sẽ tạo video dựa vào những đặc điểm bạn đã cung cấp."
    result.update(result_tool)
    #///////////////////////////////////////////////////////// 
    
    #---------------------------------------------------------
    def OutputStructuredBase(BaseModel):
        """Format the response as JSON with value is text and key is 'result'"""
    prompt = PROMPT_GET_MEMORY
    structured_output = MULTIW.VM.openai.with_structured_output(OutputStructuredBase)
    chat_prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content="You are a helpful assistant"),
            HumanMessage(content=prompt.format(query=result["new_query"], message=result["response"]))
        ]
    )
    chain = chat_prompt | structured_output 
    result_mem = chain.invoke({})
    print(result_mem["result"])
    old_memory.insert(0, f"Created at {time.strftime('%H:%M:%S', time.gmtime())}: " + result_mem["result"])
    MULTIW.VM.dataw.redisClient.hset(inputs.sess_id, MULTIW.VM.dataw.dbmemory_name, json.dumps(old_memory[:10]))
    MULTIW.VM.dataw.redisClient.expire(inputs.sess_id, 1800)

    return JSONResponse(status_code=200, content=result)

@app.post("/api/createTopic")
@HTTPException() 
async def createTopic(inputs: Topic = Body(...)):
    #----setup kafka----
    # conf = {
    #     'bootstrap.servers': 'localhost:9094'  # Use the address of one of your brokers
    # }
    # kafka_client = AdminClient(conf)
    kafka_client = app.state.kafka_client
    res = MULTIW.VM.dataw.create_topic(client=kafka_client, topic_name=inputs.topic_name, num_partitions=inputs.num_partitions, replication_factor=inputs.replication_factor, message_size=inputs.message_size)
    if res["success"]:
        return JSONResponse(status_code=200, content=str(res["message"]))
    else:
        return JSONResponse(status_code=500, content=str(res["error"]))
    
@app.post("/api/deleteTopic")
@HTTPException() 
async def deleteTopic(topic_name: dict = Body({"topic_name":"video_upload"})):
    #----setup kafka----
    # conf = {
    #     'bootstrap.servers': 'localhost:9094'  # Use the address of one of your brokers
    # }
    # kafka_client = AdminClient(conf)
    kafka_client = app.state.kafka_client
    res = MULTIW.VM.dataw.delete_topic(client=kafka_client, topic_name=topic_name["topic_name"])
    if res["success"]:
        return JSONResponse(status_code=200, content=str(res["message"]))
    else:
        return JSONResponse(status_code=500, content=str(res["error"]))
    
    
if __name__=="__main__":
    host = "0.0.0.0"
    port = 8386
    uvicorn.run("controller:app", host=host, port=port, log_level="info", reload=False)
    
    
    
    
    
"""
1xx: Informational
100	Continue	Server received the request headers.
101	Switching Protocols	Protocol switch is accepted (rare).

2xx: Success
200	OK	Request succeeded, and response returned.
201	Created	New resource was successfully created.
202	Accepted	Request accepted, processing later.
204	No Content	Request succeeded, but no content to return.

3xx: Redirection
301	Moved Permanently	Resource has a new permanent URI.
302	Found (Redirect)	Resource temporarily moved.
304	Not Modified	Client's cached version is still valid.

4xx: Client Errors
400	Bad Request	Malformed syntax or invalid parameters.
401	Unauthorized	Missing or invalid authentication.
403	Forbidden	Authenticated, but no permission.
404	Not Found	Resource not found.
405	Method Not Allowed	Method not allowed for this endpoint.
409	Conflict	Conflict in request (e.g., duplicate).
422	Unprocessable Entity	Semantic error in request (e.g., FastAPI validation).

5xx: Server Errors
500	Internal Server Error	Server-side error.
501	Not Implemented	Feature not supported.
503	Service Unavailable	Server is down or overloaded.
"""
import jwt
import uuid
import json
import uvicorn
from dataclasses import dataclass, field
from string import ascii_letters, digits, punctuation
import aiofiles
import tempfile
import tqdm

from app import *
from models import Topic, ProduceInput, InputDataWorker

@app.post("/api/uploadData")
@HTTPException() 
async def uploadData(inputs: ProduceInput = Depends(ProduceInput), video_file: UploadFile = File(...)):
    path_uid = os.path.join(PATH_TEMP, inputs.sess_id)
    check_folder_exist(path_uid=path_uid)
    path_file = f"{path_uid}{os.sep}{video_file.filename}"
    async with aiofiles.open(path_file, 'wb') as out_file:
        # while chunk := await video_file.read(1024 * 1024):  # 1 MB at a time
        while True:
            chunk = await video_file.read(1024 * 1024)
            if not chunk:
                break
            await out_file.write(chunk)
    
    # Create a Kafka producer instance
    message = InputDataWorker(sess_id=inputs.sess_id, path_file=path_file, overview=inputs.overview, category=inputs.category)
    
    producer = app.state.producer
    await producer.send_and_wait(
        inputs.topic_name,
        value=message.__dict__,
        key=message.sess_id.encode() if message.sess_id else None
    )

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=str(f"Message delivered to {inputs.topic_name}"))
    

@app.post("/api/createTopic")
@HTTPException() 
async def createTopic(inputs: Topic = Body(Topic)):
    #----setup kafka----
    # conf = {
    #     'bootstrap.servers': 'localhost:9094'  # Use the address of one of your brokers
    # }
    # kafka_client = AdminClient(conf)
    kafka_client = app.state.admin_client
    res = DATAW.create_topic(client=kafka_client, topic_name=inputs.topic_name, num_partitions=inputs.num_partitions, replication_factor=inputs.replication_factor, message_size=inputs.message_size)
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
    kafka_client = app.state.admin_client
    res = DATAW.delete_topic(client=kafka_client, topic_name=topic_name["topic_name"])
    if res["success"]:
        return JSONResponse(status_code=200, content=str(res["message"]))
    else:
        return JSONResponse(status_code=500, content=str(res["error"]))
    
if __name__=="__main__":
    host = "0.0.0.0"
    port = 8386
    uvicorn.run("controller:app", host=host, port=port, log_level="info", reload=False)
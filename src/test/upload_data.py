import requests
import os

url = "http://192.168.6.190:8386/api/uploadData"

payload = {}
headers = {}
params = {"sess_id": "test1", "topic_name": "video_upload"}

folder_vtest = '/home/mq/disk2T/son/code/GitHub/MMV/data_storage/test'
# for v_name in os.listdir(folder_vtest):
#     v_path = os.path.join(folder_vtest, v_name)
#     files=[('video_file',(os.path.basename(v_path),open(v_path,'rb'),'application/octet-stream'))]

#     response = requests.request("POST", url, headers=headers, data=payload, params=params, files=files)
#     print(response.text)

# for v_name in ["KvDJiMMDl8k.mp4", "e0kFf4mfang.mp4", "tfeUDjwlnrY.mp4", "4Q6l-XMDQh8.mp4", "OMrV8ncqClE.mp4", "YPe86b7OzLo.mp4", "HyV3bBKZ9L8.mp4", "1xS1W5qAJRs.mp4", "sRMZnRSK35w.mp4", "uu-N7eSjD1g.mp4"]:
for v_name in ["HblLU47qTfM.mp4"]:  
    v_path = os.path.join(folder_vtest, v_name)
    files=[('video_file',(os.path.basename(v_path),open(v_path,'rb'),'application/octet-stream'))]

    response = requests.request("POST", url, headers=headers, data=payload, params=params, files=files)
    print(response.text)
    exit()

# files=[('video_file',('1g3qunDMg34.mp4',open('/home/mq/disk2T/son/code/GitHub/MMV/data_storage/test/1g3qunDMg34.mp4','rb'),'application/octet-stream'))]

# response = requests.request("POST", url, headers=headers, data=payload, params=params, files=files)
# print(response.text)
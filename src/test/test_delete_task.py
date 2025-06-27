import requests
import json

url = "http://192.168.6.190:8386/api/deleteTask"

payload = json.dumps({
  "sess_id": "ancd"
})
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
print(response.json())
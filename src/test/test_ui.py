import streamlit as st
import requests
import json
from minio import Minio
from minio.error import S3Error
import io
import base64
from datetime import datetime
import uuid
import requests
import time
import pandas as pd

# Page configuration
st.set_page_config(
    page_title="MMV Chatbot",
    page_icon="🤖",
    layout="wide"
)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'minio_client' not in st.session_state:
    st.session_state.minio_client = None

def init_minio_client(endpoint, access_key, secret_key, secure=True):
    """Initialize MinIO client"""
    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        return client
    except Exception as e:
        st.error(f"Failed to connect to MinIO: {str(e)}")
        return None

def upload_to_minio(client, bucket_name, file_data, file_name, content_type):
    """Upload file to MinIO"""
    try:
        # Create bucket if it doesn't exist
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
        
        # Upload file
        client.put_object(
            bucket_name,
            file_name,
            io.BytesIO(file_data),
            len(file_data),
            content_type=content_type
        )
        return True
    except S3Error as e:
        st.error(f"MinIO upload error: {str(e)}")
        return False

def get_from_minio(client, bucket_name, file_name):
    bucket_name = bucket_name.replace("_", "-")
    print(bucket_name)
    print(file_name)
    try:
        response = client.get_object(bucket_name, file_name)
        return response.read()
    except S3Error as e:
        st.error(f"MinIO download error: {str(e)}")
        return None
    
def create_scenario(sender_id, name, description):
    url = "http://localhost:8386/api/createScenario"
        
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sender_id": sender_id,
        "name": name, 
        "description": description
    })
    res = requests.request("POST", url, headers=headers, data=payload)
    content = res.json()
    
    if res.status_code == 500:
        content = f"Cannot generate scenario because {content}"
    
    result = eval(content['scenes'])
    des = result.values()
    scene_name = []
    for i in range(len(des)):
        scene_name.append(f"Scene_{i+1}")
    result = dict(zip(scene_name, des))
    print(result)
    return result

def update_scenario(sender_id, name, scenes):
    url = "http://localhost:8386/api/updateScenario"
        
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sender_id": sender_id,
        "name": name, 
        "scenes": json.dumps(scenes)
    })
    res = requests.request("POST", url, headers=headers, data=payload)
    content = res.json()
    
    if res.status_code == 500:
        content = f"Cannot generate scenario because {content}"
    
    result = eval(content['scenes'])
    des = result.values()
    scene_name = []
    for i in range(len(des)):
        scene_name.append(f"Scene_{i+1}")
    result = dict(zip(scene_name, des))
    print(result)
    return result

def get_scenario(sender_id, name):
    url = "http://localhost:8386/api/getScenario"
        
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sender_id": sender_id,
        "name": name,
    })
    res = requests.request("POST", url, headers=headers, data=payload)
    content = res.json()
    
    if res.status_code == 500:
        content = f"Cannot get scenario because {content}"
    
    result = eval(content['scenes'])
    des = result.values()
    scene_name = []
    for i in range(len(des)):
        scene_name.append(f"Scene_{i+1}")
    result = dict(zip(scene_name, des))
    print(result)
    return result

def get_list_scenario(sender_id):
    url = "http://localhost:8386/api/getListScenario"
        
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sender_id": sender_id
    })
    res = requests.request("POST", url, headers=headers, data=payload)
    content = res.json()
    
    print(content)
    return content


def delete_scenario(sender_id, name):
    url = "http://localhost:8386/api/deleteScenario"
        
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sender_id": sender_id,
        "name": name
    })
    res = requests.request("POST", url, headers=headers, data=payload)
    content = res.json()
    
    print(content)
    return content
    
def prepare_video(sender_id, sess_id, video_name, topic_name, overview, category, mute, scenario_name, video):
    url = "http://localhost:8386/api/uploadData"
        
    headers = {}
    if category == "Select category...":
        category = ""
    
    params = {
        "sender_id": sender_id,
        "sess_id": sess_id,
        "name": video_name,
        "topic_name": topic_name,
        "overview": overview,
        "category": category,
        "mute": mute,
        "scenario_name": scenario_name
    }
    print(params)
    
    files = [('video_file',(video.name,video,video.type))]
    print(type(video))
    
    res = requests.request("POST", url, headers=headers, params=params, files=files)
    
    if res.status_code == 201:
        text_response = "Upload video success!"
        is_processing = True
    else:
        text_response = f"Can't upload video because {res.json()}"
        is_processing = False
        
    return text_response, is_processing

def process_query(sender_id, query, sess_id):
    is_create_video = False
    url = "http://localhost:8386/api/checkCreateVideo"
        
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sender_id": sender_id,
        "sess_id": sess_id,
        "query": query
    })
    res = requests.request("POST", url, headers=headers, data=payload).json()
    
    text_response = res['response']
    new_query = res['new_query']
    tool = res['tool']
    is_create_video = False
    
    # # # Simulate chatbot response
    # # text_response = f"Processing your query: '{query}'\n\nThis is a sample response. Replace this function with your actual chatbot logic that processes the query and generates appropriate text and video responses."
    
    if tool == 'create_video':
    #     # Generate a sample video response (you can replace this with actual video generation)
    #     video_filename = f"final_video/mv_abcd.mp4"
        text_response = "Xin hãy chờ một chút, tôi đang tạo video cho bạn"
        is_create_video = True
    # else:
    #     video_filename = ""
    
    # # For demonstration, we'll create a placeholder for video
    # # In real implementation, this would be your generated video
    # video_url = None  # You would set this to your actual video URL or path
    
    return text_response, new_query, is_create_video

def process_video(sender_id, query, sess_id, scenario_name):
    url = "http://localhost:8386/api/createVideo"
        
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sender_id": sender_id,
        "sess_id": sess_id,
        "query": query,
        "scenario_name": scenario_name
    })
    res = requests.request("POST", url, headers=headers, data=payload)
    
    if res.status_code == 201:
        content = res.json()
        text_response = content
        
        text_response = ""
        is_processing = True
        return text_response, is_processing
    
    else:
        text_response = f"Can't create video because {res.json()}"
        is_processing = False
        return text_response, is_processing

def update_status(sess_id):
    url = "http://localhost:8386/api/getStatus"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sess_id": sess_id,
    })
    
    res = requests.request("POST", url, headers=headers, data=payload)
    content = res.json()
    
    percent = float(content["percent"])
    status = content["status"]
    text_response = ""
    video_filename = ""
    video_url = None
    if percent==100 and status=="done":
        text_response = "Dưới đây là video của bạn"
        video_filename = json.loads(content["result"])["list_path_new"]
    elif status=="error":
        text_response = f"Can't create the video because {json.loads(content['result'])['error']}"
    
    return percent, status, text_response, video_filename, video_url

def delete_task(sess_id):
    url = "http://localhost:8386/api/deleteTask"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    payload = json.dumps({
        "sess_id": sess_id,
    })
    
    res = requests.request("POST", url, headers=headers, data=payload)
    content = res.json()
    print(content)

# st.session_state["sess_id"] = "abcd"
# if "sess_id" not in st.session_state:
st.session_state["sess_id"] = str(uuid.uuid4())
if "sender_id" not in st.session_state:
    st.session_state["sender_id"] = "abcd"
if "scenario" not in st.session_state:
    st.session_state["scenario"] = None
if 'list_scenario' not in st.session_state:
    st.session_state["list_scenario"] = get_list_scenario(st.session_state["sender_id"])
if 'scenario_name' not in st.session_state:
    st.session_state["scenario_name"] = ""
if 'scenario_select' not in st.session_state:
    st.session_state["scenario_select"] = ""
    
# Sidebar for MinIO configuration
with st.sidebar:
    st.header("MinIO Configuration")
    
    minio_endpoint = st.text_input("MinIO Endpoint", value="localhost:9000")
    minio_access_key = st.text_input("Access Key", value="demo")
    minio_secret_key = st.text_input("Secret Key", type="password", value="demo123456")
    minio_secure = st.checkbox("Use HTTPS", value=False)
    bucket_name = st.text_input("Bucket Name", value="data-mmv")
    
    if st.button("Connect to MinIO"):
        if minio_endpoint and minio_access_key and minio_secret_key:
            client = init_minio_client(
                minio_endpoint, 
                minio_access_key, 
                minio_secret_key, 
                minio_secure
            )
            if client:
                st.session_state.minio_client = client
                st.success("Successfully connected to MinIO!")
            else:
                st.error("Failed to connect to MinIO")
        else:
            st.error("Please fill in all MinIO configuration fields")
    
    # Connection status
    if st.session_state.minio_client:
        st.success("✅ MinIO Connected")
    else:
        st.warning("⚠️ MinIO Not Connected")
    
    st.divider()
    st.header("Generate Scenario")
    scenario_name = st.text_input("Scenario Name", value="demo1")
    scenario_description = st.text_area(
        "Description",
        placeholder="Describe your video ...",
        height=100,
        help="Provide a detailed description of your video"
    )
    if st.button("Generate", type="primary", use_container_width=True):
        st.session_state["scenario_name"] = scenario_name
        with st.spinner("Generating scenario..."):
            st.session_state["scenario"] = create_scenario(st.session_state["sender_id"], st.session_state["scenario_name"], scenario_description)
        if isinstance(st.session_state["scenario"], str):
            st.error(st.session_state["scenario"])
    if st.session_state["scenario"] is not None:
        df = pd.DataFrame(st.session_state["scenario"].items(), columns=['Scene', 'Description'])
        edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic", key=f"scenario_data")
        col1, col2 = st.columns([2, 2])
        with col1:
            if st.button("Got it!"):
                st.session_state["scenario"] = None
                if st.session_state["scenario_name"] not in st.session_state["list_scenario"]:
                    st.session_state["list_scenario"].append(st.session_state["scenario_name"])
                st.rerun()
        with col2:
            if st.button("Update"):
                edited_df = edited_df.dropna()
                scenario_update = edited_df.to_dict(orient='list')
                scenario_new = dict(zip(scenario_update['Scene'], scenario_update['Description']))
                st.session_state["scenario"] = update_scenario(st.session_state["sender_id"], st.session_state["scenario_name"], scenario_new)
                if isinstance(st.session_state["scenario"], str):
                    st.error(st.session_state["scenario"])
                else:
                    st.success("Update successfully!")
    scenario_box = st.selectbox(
        "Scenario Name",
        options=st.session_state["list_scenario"],
        help="Choose your scenario"
    )
    st.session_state["scenario_select"] = scenario_box
    scenario_data = get_scenario(st.session_state["sender_id"], scenario_box)
    df_2 = pd.DataFrame(scenario_data.items(), columns=['Scene', 'Description'])
    edited_df_2 = st.data_editor(df_2, use_container_width=True, num_rows="dynamic", key=f"scenario_data_2", disabled=True)
    st.divider()
    
    # Sidebar with upload form
    st.header("📤 Upload Video")
    # Video upload
    uploaded_file = st.file_uploader(
        "Choose video file",
        type=['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv'],
        help="Supported formats: MP4, AVI, MOV, WMV, FLV, WebM, MKV"
    )
    
    if uploaded_file is not None:
        st.success(f"✅ Uploaded: {uploaded_file.name}")
        st.write(f"File size: {uploaded_file.size / (1024*1024):.2f} MB")
                 
        # st.divider()
        
        # Video metadata form
        st.subheader("📝 Video Details")
        
        # Title
        video_name = st.text_input(
            "Video Name",
            value=uploaded_file.name,
            placeholder="Enter video name...",
            help="Required field"
        )
        
        # Description
        video_description = st.text_area(
            "Description",
            placeholder="Describe your video content...",
            height=100,
            help="Provide a detailed description of your video"
        )
        
        # Category
        category = st.selectbox(
            "Category*",
            options=[
                "Select category...",
                "Business",
                "Education",
                "Entertainment", 
                "Technology",
                "Marketing",
                "Training",
                "Tutorial",
                "Presentation",
                "Documentary",
                "Other"
            ],
            help="Choose the most appropriate category"
        )
        
        mute_video = st.checkbox(
            "Mute Video",
            value=True,
            help="Remove audio from video"
        )
        
        # Volume control
        if not mute_video:
            volume_level = st.slider(
                "Volume Level",
                min_value=0,
                max_value=100,
                value=100,
                help="Adjust audio volume (0-100%)"
            )
            
        # Quality settings
        st.subheader("⚙️ Quality Settings")
        
        quality = st.select_slider(
            "Video Quality",
            options=["Low (480p)", "Medium (720p)", "High (1080p)", "Ultra (4K)"],
            value="High (1080p)",
            help="Higher quality = larger file size"
        )
        
        # Compression
        compress_video = st.checkbox(
            "Compress Video",
            value=False,
            help="Reduce file size with minimal quality loss"
        )
        
        # st.divider()
        
        if st.button("📤 Upload", type="primary", use_container_width=True):
            if uploaded_file and video_name:
                # Simulate upload process
                progress_bar = st.progress(0)
                status_text = st.empty()
                with st.spinner("Uploading video..."):                     
                    text_response, is_processing = prepare_video(st.session_state["sender_id"], st.session_state["sess_id"], video_name, "video_upload", video_description, category, mute_video, st.session_state["scenario_select"], uploaded_file)
                    
                    if is_processing:
                        while True:
                            time.sleep(1)
                            percent, status, text_response, _, _ = update_status(st.session_state["sess_id"])
                            # print(percent)
                            progress_bar.progress(percent/100)
                            status_text.text(f"Processing... {percent}%")
                            if status == "done":
                                st.success("✅ Video uploaded successfully!")
                                st.balloons()
                                break
                            elif status == "error":
                                st.error("❌ Can't upload video")
                                break
                        delete_task(st.session_state["sess_id"])
                        progress_bar.empty()
                        status_text.empty()
                        
                    else:
                        st.error(f"❌ {text_response}")
                    
            else:
                st.error("❌ Please fill required fields and select a video file")
        
        # Clear form
        if st.button("🗑️ Clear Form", use_container_width=True):
            st.rerun()

# Main chat interface
st.title("🤖 MMV Chatbot")
st.markdown("Send queries and receive text and video responses stored in MinIO")

# Display chat messages
chat_container = st.container()
with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            # Display video if present
            if "video_data" in message and message["video_data"]:
                st.video(message["video_data"])

# Chat input
if prompt := st.chat_input("Enter your query..."):
    if not st.session_state.minio_client:
        st.error("Please connect to MinIO first using the sidebar configuration.")
    else:
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Process the query
        with st.chat_message("assistant"):
            with st.spinner("Waiting a minutes..."):
                text_response, new_query, is_create_video = process_query(
                    st.session_state["sender_id"],
                    prompt, 
                    st.session_state["sess_id"]
                )
                
                # Display text response
                st.write(text_response)
                
                # Add assistant response to chat
                assistant_message = {
                    "role": "assistant", 
                    "content": text_response
                }
            
            if is_create_video:
                progress_bar = st.progress(0)
                status_text = st.empty()    
                with st.spinner("Creating video, please wait a minute..."):
                    video_url = ""
                    video_filename = ""
                    text_response, is_processing = process_video(
                        st.session_state["sender_id"],
                        new_query, 
                        st.session_state["sess_id"],
                        st.session_state["scenario_select"],
                    )
                    if is_processing:
                        while True:
                            time.sleep(1)
                            percent, status, text_response, video_filename, video_url = update_status(st.session_state["sess_id"])
                            print(percent)
                            progress_bar.progress(percent/100)
                            status_text.text(f"Processing... {percent}%")
                            if status == "done" or status == "error":
                                delete_task(st.session_state["sess_id"])
                                break
                        progress_bar.empty()
                        status_text.empty()
                    
                    # Display text response
                    st.write(text_response)
                    
                    # Add assistant response to chat
                    assistant_message = {
                        "role": "assistant", 
                        "content": text_response
                    }
                        
                    # Handle video response
                    video_data = None
                    if video_url:
                        # If you have a video URL, display it
                        st.video(video_url)
                        video_data = video_url
                    elif video_filename:
                        # Try to get video from MinIO
                        video_bytes = get_from_minio(
                            st.session_state.minio_client, 
                            bucket_name, 
                            video_filename
                        )
                        if video_bytes:
                            st.video(video_bytes)
                            video_data = video_bytes
                
                if video_data:
                    assistant_message["video_data"] = video_data
                
            st.session_state.messages.append(assistant_message)

# # File upload section
st.markdown("---")
st.markdown("*Built with DXSON* 🚀")

# uploaded_file = st.file_uploader(
#     "Choose a file to upload to MinIO", 
#     type=['mp4', 'avi', 'mov', 'txt', 'pdf', 'jpg', 'png']
# )

# if uploaded_file and st.session_state.minio_client:
#     if st.button("Upload File"):
#         file_bytes = uploaded_file.read()
#         file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}"
        
#         success = upload_to_minio(
#             st.session_state.minio_client,
#             bucket_name,
#             file_bytes,
#             file_name,
#             uploaded_file.type
#         )
        
#         if success:
#             st.success(f"File uploaded successfully as: {file_name}")
#         else:
#             st.error("Failed to upload file")

# Clear chat button
if st.button("🗑️ Clear Chat History"):
    st.session_state.messages = []
    del st.session_state["sess_id"]
    st.rerun()

# Instructions
with st.expander("ℹ️ Instructions"):
    st.markdown("""
    ### How to use this chatbot:
    
    1. **Configure MinIO Connection:**
       - Enter your MinIO endpoint (e.g., localhost:9000)
       - Provide your access key and secret key
       - Specify the bucket name for storing responses
       - Click "Connect to MinIO"
    
    2. **Send Queries:**
       - Type your question in the chat input
       - The bot will process your query and provide text + video responses
       - Responses are stored in and retrieved from your MinIO service
    
    3. **Upload Files:**
       - Use the file uploader to add files to your MinIO bucket
       - Supports various formats including videos, images, and documents
    
    4. **Customize:**
       - Replace the `process_query()` function with your actual chatbot logic
       - Integrate with your preferred AI/ML models for generating responses
       - Modify video handling based on your specific requirements
    """)

# Requirements section
with st.expander("📋 Requirements"):
    st.code("""
# Install required packages:
pip install streamlit minio requests

# Or create requirements.txt with:
streamlit>=1.28.0
minio>=7.1.0
requests>=2.31.0
    """)
    
    
# streamlit run src/test/test_ui.py --server.port 8501
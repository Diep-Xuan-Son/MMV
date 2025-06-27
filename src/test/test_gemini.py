from langchain_google_genai import ChatGoogleGenerativeAI
import cv2
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import base64

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-001",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # other params...
    api_key="AIzaSyDfWvKke29AsKTYWAvucRzTggfSMmP7Q8o",
)

image = cv2.imread("./src/static/image_highlight/video_12.jpg")
# result = hl.get_description(llm, image)
_, buffer = cv2.imencode('.png', image)
base64Image = base64.b64encode(buffer).decode('utf-8')

prompt = ChatPromptTemplate.from_messages([
    SystemMessage(content="You are a marketing expert that analyze the scene and identify potential viral moment. The scene represents a significant scene change or important moment."),
    HumanMessage(content=[{"type":"text", "text":"describe the image, write in vietnamese"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64Image}"}}])
])

chain = prompt | llm 
response = chain.invoke({})
print(response)
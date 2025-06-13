import cv2
import jwt
import time
import torch
import base64
import random
import re as regex
from libs.utils import MyException
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from lighthouse.models import CGDETRPredictor
from typing import Literal, Tuple, List, Dict, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

class HighlightWorker(object):
    def __init__(self, scene_dict: dict, model_hl='./weights/model_highlight.ckpt', model_slowfast='./weights/SLOWFAST_8x8_R50.pkl', model_clip='./weights/ViT-B-32.pt',):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CGDETRPredictor(model_hl, device=device,
                        feature_name='clip_slowfast', slowfast_path=model_slowfast, clip_path=model_clip)
        self.scene_dict = scene_dict
    
    def get_image_from_timestamp(self, video_path: str, timestamp: int):
        video_capture = cv2.VideoCapture(video_path)
        fps = video_capture.get(cv2.CAP_PROP_FPS)
        video_capture.set(cv2.CAP_PROP_POS_FRAMES, timestamp*fps)
        success, frame = video_capture.read()
        if success:
            return frame
        return None
    
    def get_description(self, llm: object, image: str, query: str):
        def OutputStructured(BaseModel):
            """Format the response as JSON with these fields: description, viralPotential, suggestedTitle, suggestedHashtags."""
            description_vi: str = Field(description="")
            viralPotential_vi: str = Field(description="")
            suggestedTitle_vi: str = Field(description="")
            suggestedHashtags_vi: List[str] = Field(description="")

        _, buffer = cv2.imencode('.png', image)
        base64Image = base64.b64encode(buffer).decode('utf-8')
        prompt = """
        The user query: {query}
  
        Doing these tasks below to analyze the scene:
        1. Introducing the scene content and what makes it engaging. The description is about the brand that the user want to introduce
        2. Rate its viral potential (1-10) based on visual appeal and content
        3. Suggest a catchy title that captures the scene's essence
        4. Suggest relevant hashtags for social media
        Format the response as JSON like below: 
        {{
            "description_vi": <value of description in vietnamese>, 
            "viralPotential_vi": <value of viralPotential in vietnamese>, 
            "suggestedTitle_vi": <value of suggestedTitle in vietnamese>, 
            "suggestedHashtags_vi": [<list value of suggestedHashtags in vietnamese>]
        }}
        
        # RULE
        - The respone must be English fields and Vietnamese values of fields
        """
        # - The description is under 50 words
        parser = PydanticOutputParser(pydantic_object=OutputStructured)
  
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="You are a marketing expert that analyze the scene and identify potential viral moment. The scene represents a significant scene change or important moment."),
            HumanMessage(content=[{"type":"text", "text":prompt.format(query=query)}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64Image}"}}])
        ])

        chain = prompt | llm 
        response = chain.invoke({})
        pattern = r'{.*}'
        clean_answer = regex.findall(pattern, response.content.replace("```", "").strip(), regex.DOTALL)
        if isinstance(clean_answer, list):
            clean_answer = clean_answer[0]
        result = eval(clean_answer)
        return result

    def get_matching_description(self, llm: object, descriptions: dict, n_video: int, query: str):
        def OutputStructured(BaseModel):
            """Format the response as JSON with value is a dictionary including id (id video) and new description"""
            result: dict = Field(description="id video and new description")
   
        prompt = """
        The user's query: {query}
  
        ID videos and their description: {descriptions}

        Doing these tasks below to make a good marketing video:
        - Based on the user's query, you have to analyze, grading score and get {n_video} videos that have the most reasonable description to make a introducing video.
        - Rewriting the new description for these matching videos. 
        - Using conjunctions in the new desciptions to form a cohesive introduce paragraph.
  
        ## RULE 
        Format the response as JSON type like below:
        {{
            <id video>: <new description>
        }}
        Let's INTRODUCE, don't DESCRIBE
        The number of words in each description is under 80 words
        The new description is in Vietnamese 
          """
        # If in desciption having english word, please convert all english word to type: [en-us]{{<english word>}}. Example: massage converts to [en-us]{{massage}}
        structured_output = llm.with_structured_output(OutputStructured)
        chat_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content="You are a marketing expert that analyze these video descriptions below and select some descriptions to make a good marketing video."),
                HumanMessage(content=prompt.format(query=query, descriptions=descriptions, n_video=n_video))
                # HumanMessage(content=prompt)
            ]
        )
        chain = chat_prompt | structured_output 
        result = chain.invoke({})
        print(result)
        return result

    def choose_scene(self, llm: object, descriptions: str):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is the id video and value is the name of scene"""
            result: dict = Field(description="id video and name of scene")
            
        prompt = """
        The video descriptions: {descriptions}
        
        ## TASKS
        - Based on the definitions of scenes below, select the best scene that matches with each video description.

        Scenes and their descriptions: {scene_dict}
        """
        # - Only select the most relevant pairs of scene and video description so that each scene just has an id video
        structured_output = llm.with_structured_output(OutputStructured)
        chat_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content="You are a review expert that analyze the video description and classify in  appropriate scene"),
                HumanMessage(content=prompt.format(descriptions=descriptions, scene_dict=self.scene_dict))
                # HumanMessage(content=prompt)
            ]
        )
        chain = chat_prompt | structured_output 
        result = chain.invoke({})
        print(result)
        return result
    
    def choose_description4scene(self, llm: object, descriptions: dict):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is the scene name, and value is the video id of the most relevant description"""
            result: dict = Field(description="scene name and video id")
            
        prompt = """
        Some of descriptions for each scene: {descriptions}
        
        Based on the definitions of scenes below, select the most relevant description with each scene.
        Scenes and their definitions: {scene_dict}
        """
        # scene_id = list(descriptions.keys())[0]
        # scene = {scene_id: self.scene_dict[scene_id]}
        structured_output = llm.with_structured_output(OutputStructured)
        chat_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content="You are a review expert that analyzes descriptions and select the most relevant description"),
                HumanMessage(content=prompt.format(descriptions=descriptions, scene_dict=self.scene_dict))
                # HumanMessage(content=prompt)
            ]
        )
        chain = chat_prompt | structured_output 
        result = chain.invoke({})
        print(result)
        return result
    
    def write_overall_description(self, llm: object, description_parts: dict):
        def OutputStructured(BaseModel):
            """Format the response as JSON with key is 'result' and value is the overall description"""
            result: str = Field(description="the overall description")
            
        prompt = """
        The descriptions for each part of video: {descriptions}
        
        Based on the description of each part video, Write an overall description that gives an overview of the video content.
        
        ## RULE
        Write the overall description in Vietnamese
        """
        structured_output = llm.with_structured_output(OutputStructured)
        chat_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content="You are a review expert that analyzes descriptions and select the most relevant description"),
                HumanMessage(content=prompt.format(descriptions=description_parts, scene_dict=self.scene_dict))
                # HumanMessage(content=prompt)
            ]
        )
        chain = chat_prompt | structured_output 
        result = chain.invoke({})
        print(result)
        return result
        
    @MyException()
    def __call__(self, query, video_path):
        print(f"----video_path: {video_path}")
        self.model.encode_video(video_path)
        prediction = self.model.predict(query)
        return {"success": True,"result": prediction}

if __name__=="__main__":
    scene_dict = {
            "opening_scene": "Quay toàn cảnh bên ngoài spa, làm nổi bật logo, bảng hiệu và không khí chào đón. Thể hiện rõ nhận diện thương hiệu với hình ảnh sáng sủa, sạch sẽ và thu hút.",
            "reception_scene": "Ghi lại khoảnh khắc lễ tân đón tiếp khách với nụ cười thân thiện. Không gian chuyên nghiệp nhưng gần gũi, tạo cảm giác thoải mái ngay từ lúc khách bước vào.",
            "consultation_scene": "Quay nhân viên đang tư vấn cho khách, trao đổi về nhu cầu làm đẹp và các dịch vụ. Nhấn mạnh sự lắng nghe chăm chú và phong cách tư vấn chuyên nghiệp, tận tình.",
            "service_scene": "Quay các dịch vụ như massage, chăm sóc da mặt, tắm trắng, xông hơi... Tập trung vào: Góc quay cận cảnh bàn tay nhẹ nhàng thao tác, Các thiết bị máy móc hiện đại đang vận hành, Làn da khách mịn màng, sáng khỏe. Tạo cảm giác về sự cao cấp, chuyên nghiệp và tinh tế trong dịch vụ",
            "interior_scene": "Quay toàn bộ các khu vực bên trong spa: phòng trị liệu, phòng thư giãn, khu trang điểm... Thể hiện một không gian yên tĩnh, sang trọng và sạch sẽ, mang lại cảm giác thư thái cho khách.",
            "staff_scene": "Ghi hình đội ngũ nhân viên chuyên nghiệp, thân thiện. Có thể quay cảnh nhân viên đang làm việc cùng nhau hoặc chụp ảnh nhóm thể hiện tinh thần đoàn kết và chuyên môn cao.",
            "customer_scene": "Quay cảnh khách hàng bày tỏ cảm xúc và sự hài lòng sau khi sử dụng dịch vụ. Tập trung vào biểu cảm tự nhiên, vui vẻ và những lời nhận xét chân thành",
            "product_scene": "Quay cận cảnh các sản phẩm chăm sóc da và làm đẹp được spa sử dụng. Làm nổi bật bao bì sản phẩm, thành phần và chất lượng, tạo sự tin tưởng và chuyên nghiệp",
            "closing_scene": "Hiển thị đầy đủ thông tin liên hệ, trang fanpage và các chương trình ưu đãi hiện có. Thiết kế hình ảnh rõ ràng, hấp dẫn, kêu gọi khách hàng theo dõi và đến trải nghiệm."
        }
    hl = HighlightWorker(scene_dict=scene_dict)
    # result = hl("the fire", "./src/static/short_videos/spa/1.mp4")
    # print(f"----result: {result}")
    # exit()
 
    # result = hl.get_image_from_timestamp("./data_test/fire2.mp4", int(32.124))
    # print(f"----result: {result.shape}")
    # cv2.imshow("dfsasdf", result)
    # cv2.waitKey()
 
    SECRET_KEY = "MMV"
    token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5IjoiQUl6YVN5QS12aGZOalRFYmNzOUNDTHNDbmIyMmdDQjFtU0tMeWZ3In0.iUeorjiPqQ0XSCGovWw0gEY9EAg-SxVedUWdvZt4X94'
    API_KEY = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
    # llm = ChatGoogleGenerativeAI(
    # 	model="gemini-2.0-flash-001",
    # 	temperature=0,
    # 	max_tokens=None,
    # 	timeout=None,
    # 	max_retries=2,
    # 	# other params...
    # 	api_key=API_KEY,
    # )
    # image = cv2.imread("./src/static/image_highlight/video_12.jpg")
    # print(image.shape)
    # result = hl.get_description(llm, image)
    # print(f"----result: {result}")
    # exit()
 
    descriptions = {
            "video_0": 'Cảnh này cho thấy cận cảnh quá trình cấy tóc bằng phương pháp SMP (Scalp Micropigmentation). Sự tỉ mỉ trong từng thao tác và kết quả tự nhiên mà nó mang lại có thể thu hút sự chú ý của những người đang tìm kiếm giải pháp cho vấn đề rụng tóc. Thương hiệu có thể nhấn mạnh vào tính chuyên nghiệp và hiệu quả của dịch vụ.', 
            "video_2": 'Cảnh này giới thiệu một người phụ nữ đang thư giãn trong một bể nổi, được chiếu sáng bằng ánh sáng xanh và tím dịu nhẹ. Sự kết hợp giữa công nghệ hiện đại và sự thư giãn sâu sắc tạo nên một hình ảnh hấp dẫn, gợi ý về một trải nghiệm độc đáo và sang trọng.', 
            "video_3": 'Cảnh này giới thiệu một người phụ nữ đang thiền trong một bể nổi, được chiếu sáng bằng ánh sáng màu xanh lam và tím dịu nhẹ. Sự kết hợp giữa sự yên bình và màu sắc độc đáo tạo nên một hình ảnh hấp dẫn, hoàn hảo để quảng bá các dịch vụ chăm sóc sức khỏe và thư giãn.', 
            "video_4": 'Hình ảnh cận cảnh một người phụ nữ đang thiền định trong môi trường ánh sáng dịu nhẹ, tạo cảm giác thư thái và tĩnh lặng. Đây là khoảnh khắc lý tưởng để giới thiệu các sản phẩm hoặc dịch vụ liên quan đến sức khỏe tinh thần, thiền định, hoặc các liệu pháp thư giãn.', 
            "video_6": 'Hình ảnh cho thấy một người phụ nữ đang tận hưởng liệu pháp mát-xa mặt tại Sancy Spa. Sự tập trung vào sự thư giãn và chăm sóc bản thân làm cho nó trở nên hấp dẫn, đặc biệt là đối với những người quan tâm đến sức khỏe và sắc đẹp.', 
            "video_7": "Cảnh này giới thiệu một không gian độc đáo có tên là 'Rainfall Room', nơi người xem có thể trải nghiệm cảm giác đứng giữa cơn mưa mà không bị ướt. Sự tương phản giữa hiệu ứng mưa và khả năng giữ khô tạo nên một trải nghiệm thị giác hấp dẫn và đầy tò mò.", 
            "video_8": 'Cảnh này cho thấy một quy trình chăm sóc da chuyên nghiệp, trong đó một người đang được thoa bùn lên chân. Sự tỉ mỉ trong từng động tác và kết cấu của bùn tạo nên một trải nghiệm thị giác hấp dẫn, gợi cảm giác thư giãn và làm đẹp. Đây là cơ hội tuyệt vời để giới thiệu các sản phẩm và dịch vụ spa cao cấp, nhấn mạnh vào lợi ích của việc chăm sóc da chuyên sâu.', 
            "video_9": 'Trong cảnh này, một người phụ nữ đang ngồi trên ghế sofa và trò chuyện, có thể là trong một cuộc phỏng vấn hoặc một cuộc trò chuyện thân mật. Sự hấp dẫn nằm ở biểu cảm và cử chỉ tay của cô ấy, cho thấy sự nhiệt tình và đam mê với chủ đề đang thảo luận. Nếu thương hiệu muốn giới thiệu sự chuyên nghiệp, sự tự tin và khả năng giao tiếp, đây có thể là một khoảnh khắc phù hợp.', 
            "video_10": 'Cảnh này cho thấy một người phụ nữ đang nằm trên giường điều trị, có lẽ là để làm đẹp hoặc trị liệu sức khỏe. Sự tương tác giữa bệnh nhân và thiết bị công nghệ cao có thể thu hút sự chú ý của những người quan tâm đến các phương pháp làm đẹp và chăm sóc sức khỏe tiên tiến.', 
            "video_11": 'Hình ảnh này giới thiệu các lợi ích sức khỏe đa dạng mà thương hiệu của bạn cung cấp, từ phục hồi chấn thương và giảm đau nhức đến cải thiện các vấn đề về da và hỗ trợ giảm cân. Sự đa dạng này có thể thu hút nhiều đối tượng khác nhau.', 
            "video_12": 'Cảnh này giới thiệu một người phụ nữ trong chiếc áo trắng giản dị, đứng trước một khung cảnh bãi biển tươi mát với cây cối và kiến trúc hiện đại. Sự kết hợp giữa phong cách cá nhân và không gian xung quanh tạo nên một hình ảnh thu hút, phù hợp để quảng bá các sản phẩm thời trang hoặc phong cách sống.'
        }
    
    # {'video_0': 'service_scene', 'video_2': 'interior_scene', 'video_3': 'interior_scene', 'video_4': 'interior_scene', 'video_6': 'service_scene', 'video_7': 'interior_scene', 'video_8': 'service_scene', 'video_9': 'customer_scene', 'video_10': 'service_scene', 'video_11': 'product_scene', 'video_12': 'interior_scene'}
 
    descriptions2 = {'video_0': 'Video cận cảnh quá trình cấy tóc thẩm mỹ tại MQ Spa, tập trung vào sự tỉ mỉ và chuyên nghiệp của kỹ thuật viên. Màu sắc tương phản giữa găng tay tím và da đầu tạo điểm nhấn thị giác.', 
                  'video_1': 'Video này giới thiệu dịch vụ massage tại MQ Spa, tập trung vào trải nghiệm thư giãn và chuyên nghiệp. Hình ảnh cận cảnh các động tác massage nhẹ nhàng, dầu massage bóng bẩy và không gian yên tĩnh tạo cảm giác thư thái, thu hút người xem muốn trải nghiệm dịch vụ.', 
                  'video_2': 'Video giới thiệu về trải nghiệm thư giãn độc đáo tại MQ Spa, nơi khách hàng có thể tận hưởng liệu pháp floatation therapy trong một không gian yên tĩnh, ánh sáng dịu nhẹ, giúp giảm căng thẳng và tái tạo năng lượng.', 
                  'video_3': 'Video giới thiệu MQ Spa với hình ảnh một người phụ nữ đang thư giãn trong bồn tắm nổi, ánh sáng tím và xanh tạo cảm giác yên bình và thư thái. Sự tập trung vào trải nghiệm cá nhân và không gian spa sang trọng có thể thu hút sự chú ý của khán giả.', 
                  'video_4': 'Cảnh quay cận cảnh một người phụ nữ đang thư giãn trong không gian spa với ánh sáng dịu nhẹ màu hồng và xanh lam. Sự tập trung vào biểu cảm thanh thản và không gian yên bình tạo nên sự hấp dẫn, gợi cảm giác thư giãn và tái tạo năng lượng.', 
                  'video_5': 'Video giới thiệu dịch vụ massage Shiatsu tại MQ Spa. Cảnh quay tập trung vào sự thư giãn và thoải mái mà khách hàng trải nghiệm trong quá trình massage, với ánh sáng dịu nhẹ và không gian yên tĩnh. Các động tác massage chuyên nghiệp được thể hiện, nhấn mạnh lợi ích về sức khỏe và làn da.', 
                  'video_6': 'Video giới thiệu về liệu trình spa tại MQ Spa, tập trung vào trải nghiệm thư giãn và chăm sóc da mặt. Góc quay từ trên xuống tạo cảm giác sang trọng và chuyên nghiệp, làm nổi bật sự thoải mái của khách hàng.', 
                  'video_7': "Cảnh này giới thiệu 'Phòng Mưa' tại MQ Spa, một không gian độc đáo và thư giãn. Hiệu ứng mưa nhân tạo tạo ra một bầu không khí thanh bình và hấp dẫn, hứa hẹn một trải nghiệm spa khác biệt và đáng nhớ.", 
                  'video_8': 'Video này cho thấy cận cảnh quá trình trị liệu bùn khoáng tại MQ Spa, tập trung vào sự tỉ mỉ và chuyên nghiệp của kỹ thuật viên. Màu sắc tự nhiên của bùn khoáng kết hợp với ánh sáng dịu nhẹ tạo nên cảm giác thư giãn và sang trọng.', 
                  'video_9': 'Video giới thiệu về MQ Spa, tập trung vào không gian sang trọng và dịch vụ chăm sóc sức khỏe toàn diện. Sự tương tác giữa hai người phụ nữ tạo cảm giác gần gũi, tin cậy, khuyến khích người xem tìm hiểu thêm về spa.', 
                  'video_10': 'Video này giới thiệu trải nghiệm tại MQ Spa, nơi khách hàng được tận hưởng các liệu pháp làm đẹp và thư giãn hiện đại. Điểm nhấn là công nghệ tiên tiến và sự thoải mái, sang trọng trong không gian spa.', 
                  'video_11': 'Video này giới thiệu các dịch vụ đa dạng của MQ Spa, từ phục hồi chấn thương, điều trị các bệnh về da đến giảm cân. Điểm hấp dẫn là sự tập trung vào các vấn đề sức khỏe cụ thể và giải pháp mà spa cung cấp.', 
                  'video_12': 'Video giới thiệu về MQ Spa, tập trung vào trải nghiệm thư giãn và sang trọng mà spa mang lại. Bối cảnh tươi sáng, hiện đại và người đại diện thương hiệu thân thiện tạo cảm giác gần gũi, thu hút.'}
    
    SECRET_KEY = "MMV"
    token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5Ijoic2stcHJvai1QSDNHNnlMVEticmdvaU9ieTA4YlVMNHc0eVYxR3NJa25IeEltTl9VMFI1WmVsOWpKcDI0MzZuNUEwOTdVdTVDeXVFMDJha1RqNVQzQmxia0ZKX3dJTUw2RHVrZzh4eWtsUXdsMTN0b2JfcGVkV1c0T1hsNzhQWGVIcDhOLW1DNjY1ZE1CdUlLMFVlWEt1bzRRUnk2Ylk1dDNYSUEifQ.2qjUENU0rafI6syRlTfnKIsm6O4zuhHRqahUcculn8E'
    API_KEY = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["api_key"]

    descriptions2_list = list(descriptions2.items())
    random.shuffle(descriptions2_list)
    descriptions2 = dict(descriptions2_list)
    llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=None,
                timeout=None,
                max_retries=2,
                api_key=API_KEY,  # if you prefer to pass api key in directly instaed of using env vars
                # base_url="...",
                # organization="...",
                # other params...,
                streaming=True
            )
    # result = hl.get_matching_description(llm, descriptions2, n_video=5)

    # result = hl.choose_scene(llm, descriptions=descriptions2)
    
    result = hl.write_overall_description(llm, description_parts=descriptions2)
    exit()
    
    # descriptions = {"service_scene": ['Cảnh này cho thấy cận cảnh quá trình cấy tóc bằng phương pháp SMP (Scalp Micropigmentation). Sự tỉ mỉ trong từng thao tác và kết quả tự nhiên mà nó mang lại có thể thu hút sự chú ý của những người đang tìm kiếm giải pháp cho vấn đề rụng tóc. Thương hiệu có thể nhấn mạnh vào tính chuyên nghiệp và hiệu quả của dịch vụ.', 'Hình ảnh cho thấy một người phụ nữ đang tận hưởng liệu pháp mát-xa mặt tại Sancy Spa. Sự tập trung vào sự thư giãn và chăm sóc bản thân làm cho nó trở nên hấp dẫn, đặc biệt là đối với những người quan tâm đến sức khỏe và sắc đẹp.', 'Cảnh này cho thấy một quy trình chăm sóc da chuyên nghiệp, trong đó một người đang được thoa bùn lên chân. Sự tỉ mỉ trong từng động tác và kết cấu của bùn tạo nên một trải nghiệm thị giác hấp dẫn, gợi cảm giác thư giãn và làm đẹp. Đây là cơ hội tuyệt vời để giới thiệu các sản phẩm và dịch vụ spa cao cấp, nhấn mạnh vào lợi ích của việc chăm sóc da chuyên sâu.', 'Cảnh này cho thấy một người phụ nữ đang nằm trên giường điều trị, có lẽ là để làm đẹp hoặc trị liệu sức khỏe. Sự tương tác giữa bệnh nhân và thiết bị công nghệ cao có thể thu hút sự chú ý của những người quan tâm đến các phương pháp làm đẹp và chăm sóc sức khỏe tiên tiến.', 'Cảnh này giới thiệu một người phụ nữ trong chiếc áo trắng giản dị, đứng trước một khung cảnh bãi biển tươi mát với cây cối và kiến trúc hiện đại. Sự kết hợp giữa phong cách cá nhân và không gian xung quanh tạo nên một hình ảnh thu hút, phù hợp để quảng bá các sản phẩm thời trang hoặc phong cách sống.'], "interior_scene": ['Cảnh này giới thiệu một người phụ nữ đang thư giãn trong một bể nổi, được chiếu sáng bằng ánh sáng xanh và tím dịu nhẹ. Sự kết hợp giữa công nghệ hiện đại và sự thư giãn sâu sắc tạo nên một hình ảnh hấp dẫn, gợi ý về một trải nghiệm độc đáo và sang trọng.', 'Cảnh này giới thiệu một người phụ nữ đang thiền trong một bể nổi, được chiếu sáng bằng ánh sáng màu xanh lam và tím dịu nhẹ. Sự kết hợp giữa sự yên bình và màu sắc độc đáo tạo nên một hình ảnh hấp dẫn, hoàn hảo để quảng bá các dịch vụ chăm sóc sức khỏe và thư giãn.', 'Hình ảnh cận cảnh một người phụ nữ đang thiền định trong môi trường ánh sáng dịu nhẹ, tạo cảm giác thư thái và tĩnh lặng. Đây là khoảnh khắc lý tưởng để giới thiệu các sản phẩm hoặc dịch vụ liên quan đến sức khỏe tinh thần, thiền định, hoặc các liệu pháp thư giãn.', "Cảnh này giới thiệu một không gian độc đáo có tên là 'Rainfall Room', nơi người xem có thể trải nghiệm cảm giác đứng giữa cơn mưa mà không bị ướt. Sự tương phản giữa hiệu ứng mưa và khả năng giữ khô tạo nên một trải nghiệm thị giác hấp dẫn và đầy tò mò.", 'Cảnh này giới thiệu một người phụ nữ trong chiếc áo trắng giản dị, đứng trước một khung cảnh bãi biển tươi mát với cây cối và kiến trúc hiện đại. Sự kết hợp giữa phong cách cá nhân và không gian xung quanh tạo nên một hình ảnh thu hút, phù hợp để quảng bá các sản phẩm thời trang hoặc phong cách sống.', 'Cảnh này cho thấy cận cảnh quá trình cấy tóc bằng phương pháp SMP (Scalp Micropigmentation). Sự tỉ mỉ trong từng thao tác và kết quả tự nhiên mà nó mang lại có thể thu hút sự chú ý của những người đang tìm kiếm giải pháp cho vấn đề rụng tóc. Thương hiệu có thể nhấn mạnh vào tính chuyên nghiệp và hiệu quả của dịch vụ.'],"product_scene": ['Hình ảnh này giới thiệu các lợi ích sức khỏe đa dạng mà thương hiệu của bạn cung cấp, từ phục hồi chấn thương và giảm đau nhức đến cải thiện các vấn đề về da và hỗ trợ giảm cân. Sự đa dạng này có thể thu hút nhiều đối tượng khác nhau.']}
    descriptions = {
        "service_scene": {
            "video_0": 'Cảnh này cho thấy cận cảnh quá trình cấy tóc bằng phương pháp SMP (Scalp Micropigmentation). Sự tỉ mỉ trong từng thao tác và kết quả tự nhiên mà nó mang lại có thể thu hút sự chú ý của những người đang tìm kiếm giải pháp cho vấn đề rụng tóc. Thương hiệu có thể nhấn mạnh vào tính chuyên nghiệp và hiệu quả của dịch vụ.', 
            "video_2": 'Cảnh này giới thiệu một người phụ nữ đang thư giãn trong một bể nổi, được chiếu sáng bằng ánh sáng xanh và tím dịu nhẹ. Sự kết hợp giữa công nghệ hiện đại và sự thư giãn sâu sắc tạo nên một hình ảnh hấp dẫn, gợi ý về một trải nghiệm độc đáo và sang trọng.', 
            "video_3": 'Cảnh này giới thiệu một người phụ nữ đang thiền trong một bể nổi, được chiếu sáng bằng ánh sáng màu xanh lam và tím dịu nhẹ. Sự kết hợp giữa sự yên bình và màu sắc độc đáo tạo nên một hình ảnh hấp dẫn, hoàn hảo để quảng bá các dịch vụ chăm sóc sức khỏe và thư giãn.', 
            "video_4": 'Hình ảnh cận cảnh một người phụ nữ đang thiền định trong môi trường ánh sáng dịu nhẹ, tạo cảm giác thư thái và tĩnh lặng. Đây là khoảnh khắc lý tưởng để giới thiệu các sản phẩm hoặc dịch vụ liên quan đến sức khỏe tinh thần, thiền định, hoặc các liệu pháp thư giãn.', 
            "video_6": 'Hình ảnh cho thấy một người phụ nữ đang tận hưởng liệu pháp mát-xa mặt tại Sancy Spa. Sự tập trung vào sự thư giãn và chăm sóc bản thân làm cho nó trở nên hấp dẫn, đặc biệt là đối với những người quan tâm đến sức khỏe và sắc đẹp.',},
        "interior_scene": {
            "video_7": "Cảnh này giới thiệu một không gian độc đáo có tên là 'Rainfall Room', nơi người xem có thể trải nghiệm cảm giác đứng giữa cơn mưa mà không bị ướt. Sự tương phản giữa hiệu ứng mưa và khả năng giữ khô tạo nên một trải nghiệm thị giác hấp dẫn và đầy tò mò.", 
            "video_8": 'Cảnh này cho thấy một quy trình chăm sóc da chuyên nghiệp, trong đó một người đang được thoa bùn lên chân. Sự tỉ mỉ trong từng động tác và kết cấu của bùn tạo nên một trải nghiệm thị giác hấp dẫn, gợi cảm giác thư giãn và làm đẹp. Đây là cơ hội tuyệt vời để giới thiệu các sản phẩm và dịch vụ spa cao cấp, nhấn mạnh vào lợi ích của việc chăm sóc da chuyên sâu.', 
            "video_9": 'Trong cảnh này, một người phụ nữ đang ngồi trên ghế sofa và trò chuyện, có thể là trong một cuộc phỏng vấn hoặc một cuộc trò chuyện thân mật. Sự hấp dẫn nằm ở biểu cảm và cử chỉ tay của cô ấy, cho thấy sự nhiệt tình và đam mê với chủ đề đang thảo luận. Nếu thương hiệu muốn giới thiệu sự chuyên nghiệp, sự tự tin và khả năng giao tiếp, đây có thể là một khoảnh khắc phù hợp.', 
            "video_10": 'Cảnh này cho thấy một người phụ nữ đang nằm trên giường điều trị, có lẽ là để làm đẹp hoặc trị liệu sức khỏe. Sự tương tác giữa bệnh nhân và thiết bị công nghệ cao có thể thu hút sự chú ý của những người quan tâm đến các phương pháp làm đẹp và chăm sóc sức khỏe tiên tiến.', 
            "video_11": 'Hình ảnh này giới thiệu các lợi ích sức khỏe đa dạng mà thương hiệu của bạn cung cấp, từ phục hồi chấn thương và giảm đau nhức đến cải thiện các vấn đề về da và hỗ trợ giảm cân. Sự đa dạng này có thể thu hút nhiều đối tượng khác nhau.', 
            "video_12": 'Cảnh này giới thiệu một người phụ nữ trong chiếc áo trắng giản dị, đứng trước một khung cảnh bãi biển tươi mát với cây cối và kiến trúc hiện đại. Sự kết hợp giữa phong cách cá nhân và không gian xung quanh tạo nên một hình ảnh thu hút, phù hợp để quảng bá các sản phẩm thời trang hoặc phong cách sống.'},
        "product_scene":{
            "video_11": 'Hình ảnh này giới thiệu các lợi ích sức khỏe đa dạng mà thương hiệu của bạn cung cấp, từ phục hồi chấn thương và giảm đau nhức đến cải thiện các vấn đề về da và hỗ trợ giảm cân. Sự đa dạng này có thể thu hút nhiều đối tượng khác nhau.', 
        }
    }
    result = hl.choose_description4scene(llm, descriptions=descriptions)
 
# {
#     "video_0": 'Cảnh này cho thấy cận cảnh quá trình cấy tóc bằng phương pháp SMP (Scalp Micropigmentation). Sự tỉ mỉ trong từng thao tác và kết quả tự nhiên mà nó mang lại có thể thu hút sự chú ý của những người đang tìm kiếm giải pháp cho vấn đề rụng tóc. Thương hiệu có thể nhấn mạnh vào tính chuyên nghiệp và hiệu quả của dịch vụ.', 
#     "video_2": 'Cảnh này giới thiệu một người phụ nữ đang thư giãn trong một bể nổi, được chiếu sáng bằng ánh sáng xanh và tím dịu nhẹ. Sự kết hợp giữa công nghệ hiện đại và sự thư giãn sâu sắc tạo nên một hình ảnh hấp dẫn, gợi ý về một trải nghiệm độc đáo và sang trọng.', 
#     "video_3": 'Cảnh này giới thiệu một người phụ nữ đang thiền trong một bể nổi, được chiếu sáng bằng ánh sáng màu xanh lam và tím dịu nhẹ. Sự kết hợp giữa sự yên bình và màu sắc độc đáo tạo nên một hình ảnh hấp dẫn, hoàn hảo để quảng bá các dịch vụ chăm sóc sức khỏe và thư giãn.', 
#     "video_4": 'Hình ảnh cận cảnh một người phụ nữ đang thiền định trong môi trường ánh sáng dịu nhẹ, tạo cảm giác thư thái và tĩnh lặng. Đây là khoảnh khắc lý tưởng để giới thiệu các sản phẩm hoặc dịch vụ liên quan đến sức khỏe tinh thần, thiền định, hoặc các liệu pháp thư giãn.', 
#     "video_6": 'Hình ảnh cho thấy một người phụ nữ đang tận hưởng liệu pháp mát-xa mặt tại Sancy Spa. Sự tập trung vào sự thư giãn và chăm sóc bản thân làm cho nó trở nên hấp dẫn, đặc biệt là đối với những người quan tâm đến sức khỏe và sắc đẹp.', 
#     "video_7": "Cảnh này giới thiệu một không gian độc đáo có tên là 'Rainfall Room', nơi người xem có thể trải nghiệm cảm giác đứng giữa cơn mưa mà không bị ướt. Sự tương phản giữa hiệu ứng mưa và khả năng giữ khô tạo nên một trải nghiệm thị giác hấp dẫn và đầy tò mò.", 
#     "video_8": 'Cảnh này cho thấy một quy trình chăm sóc da chuyên nghiệp, trong đó một người đang được thoa bùn lên chân. Sự tỉ mỉ trong từng động tác và kết cấu của bùn tạo nên một trải nghiệm thị giác hấp dẫn, gợi cảm giác thư giãn và làm đẹp. Đây là cơ hội tuyệt vời để giới thiệu các sản phẩm và dịch vụ spa cao cấp, nhấn mạnh vào lợi ích của việc chăm sóc da chuyên sâu.', 
#     "video_9": 'Trong cảnh này, một người phụ nữ đang ngồi trên ghế sofa và trò chuyện, có thể là trong một cuộc phỏng vấn hoặc một cuộc trò chuyện thân mật. Sự hấp dẫn nằm ở biểu cảm và cử chỉ tay của cô ấy, cho thấy sự nhiệt tình và đam mê với chủ đề đang thảo luận. Nếu thương hiệu muốn giới thiệu sự chuyên nghiệp, sự tự tin và khả năng giao tiếp, đây có thể là một khoảnh khắc phù hợp.', 
#     "video_10": 'Cảnh này cho thấy một người phụ nữ đang nằm trên giường điều trị, có lẽ là để làm đẹp hoặc trị liệu sức khỏe. Sự tương tác giữa bệnh nhân và thiết bị công nghệ cao có thể thu hút sự chú ý của những người quan tâm đến các phương pháp làm đẹp và chăm sóc sức khỏe tiên tiến.', 
#     "video_11": 'Hình ảnh này giới thiệu các lợi ích sức khỏe đa dạng mà thương hiệu của bạn cung cấp, từ phục hồi chấn thương và giảm đau nhức đến cải thiện các vấn đề về da và hỗ trợ giảm cân. Sự đa dạng này có thể thu hút nhiều đối tượng khác nhau.', 
#     "video_12": 'Cảnh này giới thiệu một người phụ nữ trong chiếc áo trắng giản dị, đứng trước một khung cảnh bãi biển tươi mát với cây cối và kiến trúc hiện đại. Sự kết hợp giữa phong cách cá nhân và không gian xung quanh tạo nên một hình ảnh thu hút, phù hợp để quảng bá các sản phẩm thời trang hoặc phong cách sống.'
# }
import os
import re
import jwt
import cv2
import shutil
import asyncio
import numpy as np
from tts_worker import TTS
from datetime import datetime
from data_worker import DBWorker
from models import VideoHighlight
from multi_agent import MultiAgent
from langchain_openai import ChatOpenAI
from dataclasses import dataclass, field
from highlight_worker import HighlightWorker
from video_editor_worker import VideoEditorWorker
from langchain_google_genai import ChatGoogleGenerativeAI
from libs.utils import MyException, check_folder_exist, delete_folder_exist

import sys
from pathlib import Path 
FILE = Path(__file__).resolve()
DIR = FILE.parents[0]
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

class VideoMaketing(object):
    SCENE_DICT = {
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
    
    def __init__(self, 
                 model_hl_path: str='./weights/model_highlight.ckpt',
                 model_slowfast_path: str='./weights/SLOWFAST_8x8_R50.pkl',
                 model_clip_path: str='./weights/ViT-B-32.pt',
                 
                 tts_model_path: str='./weights/style_tts2/model.pth',
                 tts_config_path: str='./weights/style_tts2/config.yml',
                 nltk_data_path: str='./weights/nltk_data',
                 
                 dir_final_video: str=f'{DIR}{os.sep}static{os.sep}final_video',
                 
                 api_key_openai: str='',
                 api_key_gem: str='',
                 
                 qdrant_url="http://localhost:7000", 
                 collection_name="mmv",
                 minio_url="localhost:9000", 
                 minio_access_key="demo",
                 minio_secret_key="demo123456",
                 bucket_name="data_mmv",
                 redis_url="redis://:root@localhost:6669", 
                 redis_password="RedisAuth",
                 dbmemory_name="memory",
                 psyconpg_url="http://localhost:6670",
                 dbname="mmv",
                 psyconpg_user='demo',
                 psyconpg_password='demo123456',
                 table_name='videos',
                 sparse_model_path=f"./weights/all_miniLM_L6_v2_with_attentions", 
                 dense_model_path=f"./weights/Vietnamese_Embedding", 
                 ):
        self.dir_split_video = f"{DIR}{os.sep}static{os.sep}videos_splitted"
        self.dir_final_video = dir_final_video
        self.dir_audio = f"{DIR}{os.sep}static{os.sep}audio_transcribe"
        self.dir_audio_background = f"{DIR}{os.sep}static{os.sep}audio_background"
        check_folder_exist(dir_split_video=self.dir_split_video, dir_final_video=self.dir_final_video, dir_audio=self.dir_audio, dir_audio_background=self.dir_audio_background)
        
        self.n_scene = len(self.SCENE_DICT)
        self.duration_scene = 20
        self.duration_mini_video = 60
        self.duration_effect = 2
        self.duration_get_image = 20
        self.is_making_mv = True
        self.is_processing_data = True
        self.collection_name = collection_name
        self.bucket_name = bucket_name
        
        # init workers
        self.hlw = HighlightWorker(scene_dict=self.SCENE_DICT, model_hl=model_hl_path, model_slowfast=model_slowfast_path, model_clip=model_clip_path)
        self.ttsw = TTS(model_path=tts_model_path, config_path=tts_config_path, nltk_data_path=nltk_data_path, output_dir=self.dir_audio)
        self.vew = VideoEditorWorker(duration_effect=self.duration_effect)
        self.dataw = DBWorker(
            qdrant_url, 
            collection_name,
            minio_url, 
            minio_access_key,
            minio_secret_key,
            bucket_name,
            redis_url, 
            redis_password,
            dbmemory_name,
            psyconpg_url,
            dbname,
            psyconpg_user,
            psyconpg_password,
            table_name,
            sparse_model_path, 
            dense_model_path, 
        )
        
        self.gem = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-001",
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            # other params...
            api_key=api_key_gem,
        )
        # api_key_gem = "AIzaSyDfWvKke29AsKTYWAvucRzTggfSMmP7Q8o"
  
        self.openai = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            api_key=api_key_openai,  # if you prefer to pass api key in directly instaed of using env vars
            # base_url="...",
            # organization="...",
            # other params...,
            streaming=True
        )
        
        self.openai_med = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.4,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            api_key=api_key_openai,  # if you prefer to pass api key in directly instaed of using env vars
            streaming=True
        )
        
        self.MA = MultiAgent(self.openai)
        self.MA_med = MultiAgent(self.openai_med)
  
    def make_audio(self, vtexts: dict, u_id: str):
        audios = {}
        for v_id, text in vtexts.items():
            output_dir = self.ttsw(text=text, u_id=u_id)
            audios[v_id] = output_dir
        return audios
        
    def make(self, u_id: str, query: str):
        # ----init folder for u_id----
        # output_splitted_dir = os.path.join(self.dir_split_video, u_id)
        # if not os.path.exists(output_splitted_dir):
        # 	os.makedirs(output_splitted_dir)
        final_output_dir = os.path.join(self.dir_final_video, u_id)
        if not os.path.exists(final_output_dir):
            os.makedirs(final_output_dir)
        #/////////////////////////////
     
        # ----retrieval----
        # /////////////////
        
        # # ----check video length----
        # folder_vtest = "./src/static/short_videos/spa"
        # vhighlight = {}
        # for v_name in os.listdir(folder_vtest):
        # 	v_path = os.path.join(folder_vtest, v_name)
        # 	duration = self.vew.get_duration(v_path)
        # 	if duration < 120:
        # 		vid = f"video_{len(vhighlight)}"
        # 		vhighlight[vid] = VideoHighlight(id=vid, path_video=v_path)
        # 	else:
        # 		for i in range(int(duration/120)):
        # 			vid = f"video_{len(vhighlight)}"
        # 			v_splitted_name = f"{os.path.splitext(v_name)[0]}_splitted_{i}{os.path.splitext(v_name)[1]}"
                    # output_splitted_path = f"{output_splitted_dir}{os.sep}{v_splitted_name}"
        # 			result = self.vew.split(u_id=u_id, start_time=i*120, duration=120, video_input_path=v_path, output_path=output_splitted_path)
        # 			if result["success"]:
        # 				vhighlight[vid] = VideoHighlight(id=vid, path_video=result["path_video"])
        # #///////////////////////////
        
        # #----highlight and get image----
        # descriptions = {}
        # for vid, vh in vhighlight.items():
        # 	result = self.hlw(query, vh.path_video)
        # 	if result["success"]:
        # 		print(result["result"]["pred_relevant_windows"])
        # 		result_best = result["result"]["pred_relevant_windows"][0]
        # 		vh.highlight_time = (result_best[0] + result_best[1])/2
        # 		vh.start_time = min(0,vh.highlight_time-4)
        # 		vh.end_time = min(0,vh.highlight_time+4)
        # 		image = self.hlw.get_image_from_timestamp(vh.path_video, int(vh.highlight_time))
        # 		cv2.imwrite(f"./src/static/image_highlight/{vid}.jpg", image)
        # #///////////////////////////////
        # 		#----gen description----
        # 		des = self.hlw.get_description(self.gem, vh.path_video, int(vh.highlight_time), query)
        # 		descriptions[vid] = des
        # 		#///////////////////////
        
        #----get matching v_id----
        # new_descriptions = self.hlw.get_matching_description(self.openai, descriptions, self.n_scene, query)
        new_descriptions = {'video_2': 'Chào mừng bạn đến với MQ Spa, nơi bạn có thể trải nghiệm sự thư giãn tuyệt đối trong không gian bể nổi được chiếu sáng bằng ánh sáng xanh và tím dịu nhẹ. Tại đây, chúng tôi kết hợp công nghệ hiện đại với những liệu pháp thư giãn sâu sắc, mang đến cho bạn một trải nghiệm độc đáo và sang trọng mà bạn không thể bỏ lỡ.', 'video_3': 'Tại MQ Spa, chúng tôi mời bạn tham gia vào hành trình thiền định trong không gian bể nổi, nơi ánh sáng màu xanh lam và tím dịu nhẹ tạo ra một bầu không khí yên bình. Hãy để tâm hồn bạn được thư giãn và tái tạo năng lượng trong một trải nghiệm chăm sóc sức khỏe hoàn hảo.', 'video_4': 'MQ Spa mang đến cho bạn những khoảnh khắc thư thái và tĩnh lặng với các liệu pháp thiền định trong môi trường ánh sáng dịu nhẹ. Đây là cơ hội tuyệt vời để bạn chăm sóc sức khỏe tinh thần và tìm lại sự cân bằng trong cuộc sống.', 'video_6': 'Tại MQ Spa, bạn sẽ được tận hưởng liệu pháp mát-xa mặt chuyên nghiệp, giúp bạn thư giãn và chăm sóc bản thân một cách hoàn hảo. Hãy đến và trải nghiệm sự chăm sóc tận tình của chúng tôi, đặc biệt dành cho những ai yêu thích sức khỏe và sắc đẹp.', 'video_8': 'Chúng tôi tại MQ Spa tự hào giới thiệu quy trình chăm sóc da chuyên nghiệp, trong đó bạn sẽ được trải nghiệm sự tỉ mỉ khi thoa bùn lên chân. Hãy để chúng tôi mang đến cho bạn cảm giác thư giãn và làm đẹp, đồng thời khám phá các sản phẩm và dịch vụ spa cao cấp của chúng tôi.'}
        #/////////////////////////
        
        #----tts----
        # audios = self.make_audio(vtexts=new_descriptions, u_id=u_id)
        # print(audios)
        audios = {'video_2': '/home/mq/disk2T/son/code/GitHub/MMV/src/static/audio_transcribe/spa/0.wav', 'video_3': '/home/mq/disk2T/son/code/GitHub/MMV/src/static/audio_transcribe/spa/1.wav', 'video_4': '/home/mq/disk2T/son/code/GitHub/MMV/src/static/audio_transcribe/spa/2.wav', 'video_6': '/home/mq/disk2T/son/code/GitHub/MMV/src/static/audio_transcribe/spa/3.wav', 'video_8': '/home/mq/disk2T/son/code/GitHub/MMV/src/static/audio_transcribe/spa/4.wav'}
        #///////////
  
        #----merge video----
        # list_video = []
        # list_time = []
        # for v_id, des in new_descriptions.items():
        # 	list_video.append(vhighlight[v_id].path_video)
        # 	list_time.append(vhighlight[v_id].start_time)
        # print(list_video)
        # print(list_time)
  
        # list_video = ['/home/mq/disk2T/son/code/GitHub/MMV/src/static/videos_splitted/spa/6_splitted_0.mp4', '/home/mq/disk2T/son/code/GitHub/MMV/src/static/videos_splitted/spa/6_splitted_1.mp4', '/home/mq/disk2T/son/code/GitHub/MMV/src/static/videos_splitted/spa/6_splitted_2.mp4', '/home/mq/disk2T/son/code/GitHub/MMV/src/static/videos_splitted/spa/4_splitted_0.mp4', '/home/mq/disk2T/son/code/GitHub/MMV/src/static/videos_splitted/spa/5_splitted_1.mp4']
        # list_time = np.array([79.3931, 102.401, 9.5761, 97.44495, 106.99995000000001])
        
        # list_mini_video = []
        # list_duration_mini_video = []
        # for i, t in enumerate(list_time):
        # 	mini_video_path = f"{final_output_dir}{os.sep}final_mini_video_{i}.mp4"
        # 	result = self.vew.split(u_id=u_id, start_time=max(t-self.duration_scene//2,0), duration=self.duration_scene, video_input_path=list_video[i], output_path=mini_video_path)
        # 	if result["success"]:
        # 		list_mini_video.append(mini_video_path)
                # list_duration_mini_video.append(int(self.vew.get_duration(mini_video_path))*1000)
        # print(list_mini_video)
        # exit()
   
        list_mini_video = ['./src/static/final_video/spa/final_mini_video_0.mp4', './src/static/final_video/spa/final_mini_video_1.mp4', './src/static/final_video/spa/final_mini_video_2.mp4', './src/static/final_video/spa/final_mini_video_3.mp4', './src/static/final_video/spa/final_mini_video_4.mp4']
        final_video_file = f"{final_output_dir}{os.sep}final_video.mp4"
        # self.vew.add_effect(["circleopen","fade","hrslice","radial"], list_mini_video, final_video_file)
        #///////////////////
  
        #----add audio and text----
        duration_final_video_file = self.vew.get_duration(final_video_file)
        duration_mini_video = duration_final_video_file/len(list_mini_video)
        list_duration_mini_video = [int(duration_mini_video)*i*1000 for i in range(len(list_mini_video))]
        print(list_duration_mini_video)
        final_video_audio_file = f"{final_output_dir}{os.sep}final_video_audio.mp4"
        result = self.vew.add_audio(final_video_file, list(audios.values()), list_duration_mini_video, "./data_test/bm1.mp3",final_video_audio_file)
        print(result)
        #/////////////////
        if result["success"]:
            return {"success": True, "final_video": final_video_audio_file}
        pass
    
    def make2(self, u_id: str, query: str):
        # ----init folder for u_id----
        output_splitted_dir = os.path.join(self.dir_split_video, u_id)
        final_output_dir = os.path.join(self.dir_final_video, u_id)
        audio_output_dir = os.path.join(self.dir_audio, u_id)
        check_folder_exist(output_splitted_dir=output_splitted_dir, final_output_dir=final_output_dir, audio_output_dir=audio_output_dir)
        #/////////////////////////////
        
        # ----retrieval----
        # /////////////////
        
        # ----check video length----
        folder_vtest = "./src/static/short_videos/spa"
        vhighlight = {}
        for v_name in os.listdir(folder_vtest):
            v_path = os.path.join(folder_vtest, v_name)
            duration = self.vew.get_duration(v_path)
            if duration < self.duration_mini_video:
                vid = f"video_{len(vhighlight)}"
                vhighlight[vid] = VideoHighlight(id=vid, path_video=v_path)
            else:
                for i in range(int(duration/self.duration_mini_video)):
                    vid = f"video_{len(vhighlight)}"
                    v_splitted_name = f"{os.path.splitext(v_name)[0]}_splitted_{i}{os.path.splitext(v_name)[1]}"
                    output_splitted_path = f"{output_splitted_dir}{os.sep}{v_splitted_name}"
                    result = self.vew.split(u_id=u_id, start_time=i*self.duration_mini_video, duration=self.duration_mini_video, video_input_path=v_path, output_path=output_splitted_path, mute=False, fast=True)
                    if result["success"]:
                        vhighlight[vid] = VideoHighlight(id=vid, path_video=result["path_video"])
        #///////////////////////////
        
        #----highlight and get image----
        descriptions = {}
        for vid, vh in vhighlight.items():
            result = self.hlw(query, vh.path_video)
            if result["success"]:
                print(result["result"]["pred_relevant_windows"])
                result_best = result["result"]["pred_relevant_windows"][0]
                vh.highlight_time = (result_best[0] + result_best[1])/2
                vh.start_time = min(0,vh.highlight_time-4)
                vh.end_time = min(0,vh.highlight_time+4)
                image = self.hlw.get_image_from_timestamp(vh.path_video, int(vh.highlight_time))
                # cv2.imwrite(f"./src/static/image_highlight/{vid}.jpg", image)
        #///////////////////////////////
                #----gen description----
                des = self.hlw.get_description(self.gem, vh.path_video, int(vh.highlight_time), query)
                descriptions[vid] = des["description_vi"]
                #///////////////////////
        print(f"----descriptions: {descriptions}")
        
        #----get matching v_id----
        descriptions_list = list(descriptions.items())
        np.random.shuffle(descriptions_list)
        descriptions = dict(descriptions_list)
        new_descriptions = self.hlw.get_matching_description(self.openai, descriptions, self.n_scene, query)
        print(f"----new_description: {new_descriptions}")
        #/////////////////////////
        
        audios = {}
        list_mini_video = []
        list_duration_mini_video = []
        duration_mini_video = 0
        list_word_en = ["massage", "MQ", "Spa"]
        for i, (v_id, des) in enumerate(new_descriptions.items()):
            mini_video_path = f"{final_output_dir}{os.sep}final_mini_video_{i}.mp4"
            mute = True
            # if vhighlight[v_id].type == "interview":
            #     mute = False
            result = self.vew.split(u_id=u_id, start_time=max(vhighlight[v_id].highlight_time - self.duration_scene//2, 0), duration=self.duration_scene, video_input_path=vhighlight[v_id].path_video, output_path=mini_video_path, mute=mute, fast=True)
            if result["success"]:
                list_mini_video.append(mini_video_path)
                duration_mini_video = (i*int(self.vew.get_duration(mini_video_path)) - i*(self.duration_effect) + 0.5)*1000
                # if vhighlight[v_id].type == "interview":
                #     continue
                list_duration_mini_video.append(duration_mini_video)
                
            #----tts----
            for word in list_word_en:
                if word in des:
                    des = des.replace(word, f"[en-us]{{{word}}}")
            output_dir = self.ttsw(text=des, output_dir=audio_output_dir)
            audios[v_id] = output_dir
            #///////////
        print(list_duration_mini_video)
        
        #----merge video----
        final_video_file = f"{final_output_dir}{os.sep}final_video.mp4"
        self.vew.add_effect(["circleopen","fade","hrslice","radial"], list_mini_video, final_video_file)
        #///////////////////
        
        #----add audio and text----
        final_video_audio_file = f"{final_output_dir}{os.sep}final_video_audio.mp4"
        result = self.vew.add_audio(final_video_file, list(audios.values()), list_duration_mini_video, "./data_test/bm1.mp3",final_video_audio_file)
        print(result)
        #/////////////////
        if result["success"]:
            return {"success": True, "final_video": final_video_audio_file}
    
    async def preprocess_data(self, data: dict):
        # ----check video length----
        vhighlight = {}
        # for v_name in os.listdir(folder_vtest):
        v_path = data["path_file"]
        v_name = os.path.basename(v_path)
        output_splitted_dir = os.path.dirname(v_path)
        duration = await self.vew.get_duration(v_path)
        threadw = []
        results = []
        if duration < self.duration_mini_video:
            vid = f"video_{len(vhighlight)}"
            vhighlight[vid] = VideoHighlight(id=vid, path_video=v_path, duration=duration)
        else:
            for i in range(int(duration/self.duration_mini_video)):
                vid = f"video_{len(vhighlight)}"
                v_splitted_name = f"{os.path.splitext(v_name)[0]}_splitted_{i}{os.path.splitext(v_name)[1]}"
                output_splitted_path = f"{output_splitted_dir}{os.sep}{v_splitted_name}"
                # result = await self.vew.split(u_id=data["sess_id"], start_time=i*self.duration_mini_video, duration=self.duration_mini_video, video_input_path=v_path, output_path=output_splitted_path, mute=False)
                # if result["success"]:
                #     vhighlight[vid] = VideoHighlight(id=vid, path_video=result["path_video"])
                threadw.append(self.vew.split(u_id=data["sess_id"], start_time=i*self.duration_mini_video, duration=self.duration_mini_video, video_input_path=v_path, output_path=output_splitted_path, mute=False, fast=True))
                if len(threadw)>5:
                    result = await asyncio.gather(*threadw)
                    results += result
                    threadw.clear()
            if len(threadw):
                result = await asyncio.gather(*threadw)
                results += result    
            for r in results:
                if r["success"]:
                    vid = f"video_{len(vhighlight)}"
                    vhighlight[vid] = VideoHighlight(id=vid, path_video=r["path_video"], duration=self.duration_mini_video)
        #///////////////////////////
        
        #----highlight and get image----
        list_path_full = []
        descriptions = {}
        for vid, vh in vhighlight.items():
            result = self.hlw("the most beautiful scene", vh.path_video)
            if result["success"]:
                print(result["result"]["pred_relevant_windows"])
                result_best = result["result"]["pred_relevant_windows"][0]
                vh.highlight_time = (result_best[0] + result_best[1])/2
                vh.start_time = min(0,vh.highlight_time-4)
                vh.end_time = min(0,vh.highlight_time+4)
            else:
                # duration = await self.vew.get_duration(vh.path_video)
                duration = vh.duration
                vh.highlight_time = duration/2
            # image = self.hlw.get_image_from_timestamp(vh.path_video, int(vh.highlight_time))
            # cv2.imwrite(f"./src/static/image_highlight/{vid}.jpg", image)
        #///////////////////////////////
            #----gen description----
            des = self.hlw.get_description(self.gem, vh.path_video, int(vh.highlight_time), "Describe the image")
            descriptions[vid] = des["description_vi"]
            #///////////////////////
            list_path_full.append(vh.path_video)
        print(descriptions)
        
        #----write overview----
        overview = data["overview"]
        if not overview:
            result = self.hlw.write_overall_description(self.openai, description_parts=descriptions)
            overview = result["result"]
        else:
            result = self.hlw.rewrite_description_rely_on_overview(self.openai, description_parts=descriptions, overview=overview)
            descriptions = result["result"]
        #//////////////////////
        
        #----choose scene for each description----
        result = self.hlw.choose_scene(self.openai, descriptions=descriptions, category=data["category"])
        # print(result)
        scene_list_des = {}
        for vid, vname in result.items():
            if vname not in scene_list_des:
                scene_list_des[vname] = {vid: descriptions[vid]}
            else:
                scene_list_des[vname][vid] = descriptions[vid]
        #/////////////////////////////////////////
        
        #----get unique description for scene----
        scene_vid = self.hlw.choose_description4scene(self.openai, descriptions=scene_list_des)
        #////////////////////////////////////////
        print(f"----scene_vid: {scene_vid}")
        
        list_des = []
        list_path = []
        list_htime = []
        list_duration = []
        for sn in self.SCENE_DICT.keys():
            if sn in scene_vid:
                vid = scene_vid[sn]
                list_des.append(descriptions[vid])
                list_path.append(vhighlight[vid].path_video)
                list_htime.append(vhighlight[vid].highlight_time)
                list_duration.append(vhighlight[vid].duration)
            else:
                list_des.append("")
                list_path.append("")
                list_htime.append(0)
                list_duration.append(0)
        print(f"----list_des: {list_des}")
        print(f"----list_path: {list_path}")
        print(f"----list_htime: {list_htime}")
        
        list_category = list(scene_vid.keys())
        if data["category"]:
            category = data["category"]
            list_category = re.sub(r",\s+", ",", category).split(",")
        
        response = {
            "list_des": list_des,
            "list_path": list_path,
            "list_htime": list_htime,
            "overview": overview,
            "category": list_category,
            "list_path_full": list_path_full,
            "list_duration": list_duration
        }
        
        return response
    
    async def preprocess_data_nohl(self, data: dict):
        self.is_processing_data = True
        SCENE_DICT = data["scene_dict"]
        # ----check video length----
        vhighlight = {}
        # for v_name in os.listdir(folder_vtest):
        v_path = data["path_file"]
        v_name = os.path.basename(v_path)
        output_splitted_dir = os.path.dirname(v_path)
        list_path_delete = [output_splitted_dir]
        
        duration = await self.vew.get_duration(v_path)
        descriptions = {}
        if duration < self.duration_mini_video:
            vid = f"video_{len(vhighlight)}"
            duration_get_image_temp = self.duration_get_image 
            if duration < self.duration_get_image:
                self.duration_get_image = duration - 1e-3
            for n in range(int(duration/self.duration_get_image)):
                vhighlight[vid] = VideoHighlight(id=vid, path_video=v_path, duration=duration, highlight_time=n*self.duration_get_image + self.duration_get_image/2)
                #----gen description----
                des = await self.hlw.get_description(self.gem, vhighlight[vid].path_video, int(vhighlight[vid].highlight_time), "Describe the image")
                descriptions[vid] = des["description_vi"]
                #///////////////////////
            self.duration_get_image = duration_get_image_temp
        else:
            thread_des = []
            thread_vid = []
            for i in range(int(duration/self.duration_mini_video)):
                for n in range(int(self.duration_mini_video//self.duration_get_image)):
                    # vid = f"video_{len(vhighlight)}"
                    vid = f"video_{len(thread_des)}"
                    vhighlight[vid] = VideoHighlight(id=vid, path_video=v_path, duration=self.duration_mini_video, start_time=i*self.duration_mini_video+1, highlight_time=i*self.duration_mini_video + n*self.duration_get_image + self.duration_get_image/2)
                    #----gen description----
                    # des = await self.hlw.get_description(self.gem, vhighlight[vid].path_video, int(vhighlight[vid].highlight_time), "Describe the image")
                    # descriptions[vid] = des["description_vi"]
                    thread_des.append(self.hlw.get_description(self.gem, vhighlight[vid].path_video, int(vhighlight[vid].highlight_time), "Describe the image"))
                    thread_vid.append(vid)
                    #///////////////////////
                if not self.is_processing_data:
                    {"success": False, "list_path_delete": list_path_delete}
                # self.dataw.update_status(self.dataw.cur, data["sess_id"], "data", {}, round((i+1)*30/int(duration/self.duration_mini_video),2), "pending")
            result = await asyncio.gather(*thread_des)
            result = [d["description_vi"] for d in result]
            descriptions.update(dict(zip(thread_vid, result)))
        #///////////////////////////
        if not self.is_processing_data:
            {"success": False, "list_path_delete": list_path_delete}
        self.dataw.update_status(self.dataw.cur, data["sess_id"], "data", {}, 30, "pending")
        print(descriptions)
        
        #----write overview----
        overview = data["overview"]
        if not overview:
            result = await self.MA.write_overall_description(description_parts=descriptions)
            overview = result["result"]
        else:
            result = await self.MA.rewrite_description_rely_on_overview(overview=overview, description_parts=descriptions)
            descriptions = result["result"]
        #//////////////////////
        if not self.is_processing_data:
            {"success": False, "list_path_delete": list_path_delete}
        self.dataw.update_status(self.dataw.cur, data["sess_id"], "data", {}, 40, "pending")
        
        #----choose scene for each description----
        result = await self.MA.choose_scene(scene_dict=SCENE_DICT, descriptions=descriptions, category=data["category"])
        # print(result)
        scene_list_des = {}
        for vid, vname in result.items():
            if vname not in scene_list_des:
                scene_list_des[vname] = {vid: descriptions[vid]}
            else:
                scene_list_des[vname][vid] = descriptions[vid]
        #/////////////////////////////////////////
        if not self.is_processing_data:
            {"success": False, "list_path_delete": list_path_delete}
        self.dataw.update_status(self.dataw.cur, data["sess_id"], "data", {}, 50, "pending")

        #----get unique description for scene----
        scene_vid = await self.MA.choose_description4scene(scene_dict=SCENE_DICT, descriptions=scene_list_des)
        #////////////////////////////////////////
        print(f"----scene_vid: {scene_vid}")
        
        threadw = []
        list_path_full = []
        list_path_is_splitting = []
        list_des = []
        list_path = []
        list_htime = []
        list_duration = []
        for i, sn in enumerate(SCENE_DICT.keys()):
            if sn in scene_vid:
                vid = scene_vid[sn]
                if vhighlight[vid].start_time:
                    v_name = os.path.basename(vhighlight[vid].path_video)
                    v_splitted_name = f"{os.path.splitext(v_name)[0]}_splitted_{int(vhighlight[vid].start_time/self.duration_mini_video)}{os.path.splitext(v_name)[1]}"
                    output_splitted_path = f"{output_splitted_dir}{os.sep}{v_splitted_name}"
                    if output_splitted_path not in list_path_is_splitting:
                        threadw.append(self.vew.split(u_id=data["sess_id"], start_time=vhighlight[vid].start_time, duration=vhighlight[vid].duration, video_input_path=vhighlight[vid].path_video, output_path=output_splitted_path, mute=False, fast=True))
                    list_path_is_splitting.append(output_splitted_path)
                    vhighlight[vid].path_video = output_splitted_path
                    vhighlight[vid].highlight_time = vhighlight[vid].highlight_time - vhighlight[vid].start_time + 1
                list_des.append(descriptions[vid])
                list_path.append(vhighlight[vid].path_video)
                list_htime.append(vhighlight[vid].highlight_time)
                list_duration.append(vhighlight[vid].duration)
                list_path_full.append(vhighlight[vid].path_video)
            else:
                list_des.append("")
                list_path.append("")
                list_htime.append(0)
                list_duration.append(0)
            self.dataw.update_status(self.dataw.cur, data["sess_id"], "data", {}, 50 + round((i+1)*25/len(SCENE_DICT),2), "pending")
        if len(threadw):
            result = await asyncio.gather(*threadw)
        if not self.is_processing_data:
            {"success": False, "list_path_delete": list_path_delete}
            
        print(f"----list_des: {list_des}")
        print(f"----list_path: {list_path}")
        print(f"----list_htime: {list_htime}")
        
        list_category = list(scene_vid.keys())
        if data["category"]:
            category = data["category"]
            list_category = re.sub(r",\s+", ",", category).split(",")
        
        response = {
            "success": True,
            "list_des": list_des,
            "list_path": list_path,
            "list_htime": list_htime,
            "overview": overview,
            "category": list_category,
            "list_path_full": list_path_full,
            "list_duration": list_duration,
            "list_path_delete": list_path_delete,
        }
        
        if not self.is_processing_data:
            return {"success": False, "list_path_delete": list_path_delete}
        self.dataw.update_status(self.dataw.cur, data["sess_id"], "data", {}, 80, "pending")
        return response
        
    async def make_mv(self, u_id: str, query: str, SCENE_DICT: str, **kwargs):
        self.is_making_mv = True
        # ----init folder for u_id----
        output_splitted_dir = os.path.join(self.dir_split_video, u_id)
        final_output_dir = os.path.join(self.dir_final_video, u_id)
        audio_output_dir = os.path.join(self.dir_audio, u_id)
        audio_background_dir = os.path.join(self.dir_audio_background, u_id)
        check_folder_exist(final_output_dir=final_output_dir, output_splitted_dir=output_splitted_dir, audio_output_dir=audio_output_dir, audio_background_dir=audio_background_dir)
        list_path_delete = [output_splitted_dir, final_output_dir, audio_output_dir, audio_background_dir]
        #/////////////////////////////
        
        #----retrieve----
        result = await self.MA.get_advanced_query(query=query, scene_dict=SCENE_DICT)
        scene_names = list(result.keys())
        advanced_querys = list(result.values())
        res = self.dataw.retrieve(collection_name=self.collection_name, text_querys=advanced_querys, categories=scene_names)
        #////////////////
        if not self.is_making_mv:
            {"success": False, "list_path_delete": list_path_delete}
        self.dataw.update_status(self.dataw.cur, u_id, "query", {}, 20, "pending")
        
        #----rewrite the description for each scene----
        res["list_paths"] = list(filter(None, res["list_paths"]))
        if not res["list_paths"]:
            return {"success": False, "error": "Don't find any good enough video for the user!"}
        res["list_htimes"] = list(filter(None, res["list_htimes"]))
        res["list_durations"] = list(filter(None, res["list_durations"]))
        list_des = res["list_des"]
        dict_des = dict(zip(scene_names, list_des))
        dict_des = {k:v for k,v in dict_des.items() if v}
        result = await self.MA.select_matching_description(descriptions=dict_des, query=query)
        dict_path = {}
        dict_htime = {}
        dict_duration = {}
        scene_des = {}
        for i, (k,v) in enumerate(result.items()):
            if dict_des[k]:
                scene_des[k] = dict_des[k][v]
                dict_path[k] = res["list_paths"][i][v]
                dict_htime[k] = res["list_htimes"][i][v] - 4    #back 4s video for 2s effect and then come to main content will be reasonable
                dict_duration[k] = res["list_durations"][i][v]
        print(scene_des)
        new_descriptions = await self.MA_med.rewrite_description(descriptions=scene_des, query=query)
        # vtype = await self.MA.get_type_video(query=query)
        # new_descriptions = await self.MA_med.rewrite_description_2(descriptions=scene_des, query=query, purpose=vtype["purpose"], vtype=vtype["type"])
        #/////////////////////////////////////////////
        print(new_descriptions)
        print(dict_path)
        print(dict_htime)
        print(dict_duration)
        # exit()
        if not self.is_making_mv:
            {"success": False, "list_path_delete": list_path_delete}
        self.dataw.update_status(self.dataw.cur, u_id, "query", {}, 30, "pending")
        
        # new_descriptions = {'opening_scene': 'Chào mừng bạn đến với MQ Spa, nơi không gian sang trọng và dịch vụ hoàn hảo hòa quyện. Hãy cùng khám phá những trải nghiệm tuyệt vời mà chúng tôi mang đến cho bạn.', 'reception_scene': 'Khi bước vào MQ Spa, bạn sẽ ngay lập tức cảm nhận được sự sang trọng từ khu vực lễ tân hiện đại, với ánh sáng ấm áp và những chi tiết trang trí tinh tế, tạo nên không khí thư giãn và chào đón.', 'consultation_scene': 'Tại MQ Spa, chúng tôi luôn chú trọng đến sự hài lòng của khách hàng. Đội ngũ nhân viên tư vấn tận tình sẽ lắng nghe và giúp bạn chọn lựa dịch vụ phù hợp nhất để mang lại trải nghiệm thư giãn tối ưu.', 'service_scene': 'Hãy để bản thân được chăm sóc với liệu trình massage đá nóng tại MQ Spa. Bạn sẽ cảm nhận được sự thư giãn tuyệt đối khi những viên đá ấm áp được áp lên cơ thể, giúp xua tan mọi căng thẳng.', 'interior_scene': 'MQ Spa không chỉ là nơi làm đẹp mà còn là thiên đường thư giãn. Với không gian sang trọng, giường massage được trang trí tinh tế và ánh sáng dịu nhẹ, chúng tôi cam kết mang đến cho bạn những giây phút thư giãn tuyệt vời.', 'staff_scene': 'Đội ngũ nhân viên chuyên nghiệp và thân thiện của MQ Spa luôn sẵn sàng chào đón bạn. Với nụ cười tươi tắn và trang phục đồng bộ, chúng tôi tạo nên một không khí ấm áp và gần gũi.', 'customer_scene': 'Sau khi trải nghiệm dịch vụ tại MQ Spa, bạn sẽ thấy sự tự tin và hài lòng hiện rõ trên khuôn mặt mình. Chúng tôi cam kết mang đến cho bạn vẻ đẹp và sự thư giãn trong không gian sang trọng.', 'product_scene': 'Tại MQ Spa, chúng tôi sử dụng các sản phẩm làm đẹp cao cấp, giúp bạn tỏa sáng với vẻ đẹp thanh lịch và quyến rũ. Hãy đến và trải nghiệm sự khác biệt mà chúng tôi mang lại cho bạn.', 'closing_scene': 'Đừng bỏ lỡ cơ hội trải nghiệm dịch vụ tuyệt vời tại MQ Spa với chương trình khuyến mãi hấp dẫn. Hãy đến và cảm nhận sự tươi mới, thư giãn và làm đẹp ngay hôm nay!'}
        # dict_path = {'opening_scene': 'mmv1/7xBxQwvSQ6I_splitted_0.mp4', 'reception_scene': 'mmv1/H0OIDtXvyO4_splitted_0.mp4', 'consultation_scene': 'mmv1/Q7eHOsD-nB8_splitted_0.mp4', 'service_scene': 'mmv1/Q7eHOsD-nB8_splitted_2.mp4', 'interior_scene': 'mmv1/dq5MukeT1Jc.mp4', 'staff_scene': 'mmv1/Rg5stO6mSEk_splitted_0.mp4', 'customer_scene': 'mmv1/EuidyMKu2ss_splitted_2.mp4', 'product_scene': 'mmv1/hZtULkW3m70.mp4', 'closing_scene': 'mmv1/WG8KQdPL5D4_splitted_0.mp4'}
        # dict_htime = {'opening_scene': 0.0, 'reception_scene': 10.0, 'consultation_scene': 50.0, 'service_scene': 50.0, 'interior_scene': 8.7305, 'staff_scene': 10.0, 'customer_scene': 50.0, 'product_scene': 30.0, 'closing_scene': 50.0}
        # dict_duration = {'opening_scene': 60, 'reception_scene': 60, 'consultation_scene': 60, 'service_scene': 60, 'interior_scene': 17.462, 'staff_scene': 60, 'customer_scene': 60, 'product_scene': 43.259, 'closing_scene': 60}
        
        for scene, path in dict_path.items():
            res = self.dataw.download_file(bucket_name=self.bucket_name, object_name=path, folder_local=output_splitted_dir)
            dict_path[scene] = res["file_path"]
        
        threadw = []
        threadw2 = []
        audios = {}
        list_mini_video = []
        list_mini_video_text = []
        list_duration_mini_video = []
        duration_mini_video = 500
        list_word_en = ["massage", "MQ", "Spa"]
        for i, (v_id, des) in enumerate(new_descriptions.items()):
            mini_video_path = f"{final_output_dir}{os.sep}final_mini_video_{i}.mp4"
            mute = True
            # if vhighlight[v_id].type == "interview":
            #     mute = False
            
            #----tts----
            output_dir = await self.ttsw(text=des, output_dir=audio_output_dir)
            audios[v_id] = output_dir
            #///////////
            
            # num_word = len(des.split())
            # duration_scene = num_word//4
            duration_scene = await self.vew.get_duration(output_dir) + 1
            # total_video_time = await self.vew.get_duration(dict_path[v_id])
            total_video_time = dict_duration[v_id]
            spare_time = (dict_htime[v_id] + duration_scene) - (total_video_time - self.duration_effect)

            # result = await self.vew.split(u_id=u_id, start_time=max(dict_htime[v_id] - duration_scene//2, 0), duration=duration_scene+self.duration_effect, video_input_path=dict_path[v_id], output_path=mini_video_path, mute=mute)
            
            if duration_scene > total_video_time - self.duration_effect:
                shutil.copy2(dict_path[v_id], mini_video_path)
            else:
                if spare_time>0:
                    dict_htime[v_id] -= spare_time + 0.5
                # result = await self.vew.split(u_id=u_id, start_time=max(dict_htime[v_id], 0), duration=round(duration_scene+self.duration_effect), video_input_path=dict_path[v_id], output_path=mini_video_path, mute=mute, fast=True)
                threadw.append(self.vew.split(u_id=u_id, start_time=max(dict_htime[v_id], 0), duration=round(duration_scene+self.duration_effect), video_input_path=dict_path[v_id], output_path=mini_video_path, mute=mute, fast=True))
            list_mini_video.append(mini_video_path)
        
        if len(threadw):
            result = await asyncio.gather(*threadw)
        
        for i, (v_id, des) in enumerate(new_descriptions.items()):    
            #----add text----
            mini_video_text_path = f"{final_output_dir}{os.sep}final_mini_video_text_{i}.mp4"
            duration_mini_video_current = int(await self.vew.get_duration(list_mini_video[i])) - (self.duration_effect)
            # threadw2.append(self.vew.add_text(text=des, video_input_path=list_mini_video[i], video_output_path=mini_video_text_path, fast=False, start_time=1-i/len(new_descriptions)))
            threadw2.append(self.vew.add_text2(texts=[des], video_input_path=list_mini_video[i], video_output_path=mini_video_text_path, fast=False, start_time=[1-i/len(new_descriptions), duration_mini_video_current], text_position=[300, 300, 600]))
            #////////////////
            
            # list_mini_video.append(mini_video_path)
            list_mini_video_text.append(mini_video_text_path)
            # duration_mini_video = (i*int(await self.vew.get_duration(mini_video_path)) - i*(self.duration_effect) + 0.5)*1000
            # if i:
            #     duration_mini_video += (int(await self.vew.get_duration(list_mini_video[i-1])) - (self.duration_effect))*1000
            # if vhighlight[v_id].type == "interview":
            #     continue
            duration_mini_video += duration_mini_video_current*1000
            list_duration_mini_video.append(duration_mini_video + 500)
                
            # #----tts----
            # for word in list_word_en:
            #     if word in des:
            #         des = des.replace(word, f"[en-us]{{{word}}}")
            # output_dir = await self.ttsw(text=des, output_dir=audio_output_dir)
            # audios[v_id] = output_dir
            # #///////////
            if not self.is_making_mv:
                {"success": False, "list_path_delete": list_path_delete}
            self.dataw.update_status(self.dataw.cur, u_id, "query", {}, round(30 + (i+1)*50/len(new_descriptions),2), "pending")
        print(list_duration_mini_video)
        
        if len(threadw):
            # result = await asyncio.gather(*threadw)
            result = await asyncio.gather(*threadw2)
        
        #----merge video----
        final_video_file = f"{final_output_dir}{os.sep}final_video.mp4"
        await self.vew.add_effect(["circleopen","fade","hrslice","radial"], list_mini_video_text, final_video_file, False)
        #///////////////////
        if not self.is_making_mv:
            {"success": False, "list_path_delete": list_path_delete}
        self.dataw.update_status(self.dataw.cur, u_id, "query", {}, 90, "pending")
        
        #----add audio----
        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        final_video_audio_file = f"{final_output_dir}{os.sep}mv_{u_id}_{timestamp}.mp4"
        result = await self.vew.add_audio(final_video_file, list(audios.values()), [700] + list_duration_mini_video[:-1], f"{DIR}{os.sep}data{os.sep}audio_background{os.sep}ba1.mp3", final_video_audio_file)
        #/////////////////
        if not self.is_making_mv:
            {"success": False, "list_path_delete": list_path_delete}
        self.dataw.update_status(self.dataw.cur, u_id, "query", {}, 95, "pending")
        
        # if result["success"]:
            # return {"success": True, "final_video": final_video_audio_file, "list_path_delete": list_path_delete}
        return {"success": True, "final_video": final_video_audio_file, "list_path_delete": list_path_delete}
        pass

if __name__=="__main__":
    SECRET_KEY = os.getenv('SECRET_KEY', "MMV")
    token = os.getenv("API_KEY", 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5IjoiQUl6YVN5Q1BKSHNJYUxXaGdMakllQkZVS3E4VHFrclRFdWhGd2xzIn0.7iN_1kRmOahYrT7i5FUplOYeda1s7QhYzk-D-AlgWgE')
    API_KEY_GEM = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
    token = os.getenv("API_KEY", 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5Ijoic2stcHJvai1QSDNHNnlMVEticmdvaU9ieTA4YlVMNHc0eVYxR3NJa25IeEltTl9VMFI1WmVsOWpKcDI0MzZuNUEwOTdVdTVDeXVFMDJha1RqNVQzQmxia0ZKX3dJTUw2RHVrZzh4eWtsUXdsMTN0b2JfcGVkV1c0T1hsNzhQWGVIcDhOLW1DNjY1ZE1CdUlLMFVlWEt1bzRRUnk2Ylk1dDNYSUEifQ.2qjUENU0rafI6syRlTfnKIsm6O4zuhHRqahUcculn8E')
    API_KEY_OPENAI = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
    vm = VideoMaketing(api_key_openai=API_KEY_OPENAI,api_key_gem=API_KEY_GEM)
    u_id = "spa2"
    # vm.make2(u_id, "Give me a marketing video that introduces the MQ spa")
    
    # data = {"sess_id":"aaa", "path_file":"./src/static/short_videos/spa/5.mp4"}
    # vm.preprocess_data(data=data)
    
    data = {"path_file": "/home/mq/disk2T/son/code/GitHub/MMV/data_storage/test/KvDJiMMDl8k.mp4", "sess_id": "test1", "overview": "", "category": ""} #mcB-UEKulhw.mp4 , tuYrBt9Sfe4.mp4, KvDJiMMDl8k.mp4, e0kFf4mfang_.mp4, tfeUDjwlnrY.mp4, 4Q6l-XMDQh8.mp4, OMrV8ncqClE.mp4
    # asyncio.run(vm.preprocess_data(data=data))
    # asyncio.run(vm.preprocess_data_nohl(data=data))
    # exit()
    
    query = "cho tôi video giới thiệu về MQ spa với không gian sang trọng"
    asyncio.run(vm.make_mv(u_id=u_id, query=query, SCENE_DICT=vm.SCENE_DICT))
    
# """
# 1. Ngoai canh/ mat tien spa / canh thuong hieu
# 2. Canh le tan chao don khach
# 3. Cảnh khách được tư vấn
# 4. Cảnh dịch vụ đang thực hiện
#     - Các dịch vụ chính: massage, chăm sóc da mặt, tắm trắng, xông hơi, v.v.
#     - Chú trọng góc quay cận cảnh bàn tay nhẹ nhàng, máy móc hiện đại, da khách mịn màng.
# 5. Cảnh không gian spa
# 	- Quay các khu vực như phòng trị liệu, phòng thư giãn, khu trang điểm.
# 6. Cảnh đội ngũ nhân viên
# 7. Canh khac noi ve cam nhan sau dich vu
# 8. Cảnh sản phẩm sử dụng trong spa
# 9. Canh thông tin liên hệ, fanpage, chương trình khuyến mãi.
# """
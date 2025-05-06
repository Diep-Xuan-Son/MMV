import os
import jwt
import cv2
import numpy as np
from tts_worker import TTS
from langchain_openai import ChatOpenAI
from dataclasses import dataclass, field
from highlight_worker import HighlightWorker
from video_editor_worker import VideoEditorWorker
from libs.utils import MyException, check_folder_exist
from langchain_google_genai import ChatGoogleGenerativeAI

import sys
from pathlib import Path 
FILE = Path(__file__).resolve()
DIR = FILE.parents[0]
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
    
@dataclass
class VideoHighlight:
    id: str
    start_time: float = 0.0
    end_time: float = 0.0
    highlight_time: float = 0.0
    path_video: str = ""
    description: str = ""

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
                 ):
        self.duration_scene = 20
        self.n_scene = 5
        self.dir_split_video = f"{DIR}{os.sep}static{os.sep}videos_splitted"
        self.dir_final_video = dir_final_video
        
        self.duration_mini_video = 120
        self.duration_effect = 2
        
        # init workers
        self.hlw = HighlightWorker(scene_dict=self.SCENE_DICT, model_hl=model_hl_path, model_slowfast=model_slowfast_path, model_clip=model_clip_path)
        # self.ttsw = TTS(model_path=tts_model_path, config_path=tts_config_path, nltk_data_path=nltk_data_path)
        self.vew = VideoEditorWorker(duration_effect=self.duration_effect)
        
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
        # 		des = self.hlw.get_description(self.gem, image, query)
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
        check_folder_exist(output_splitted_dir=output_splitted_dir, final_output_dir=final_output_dir)
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
                    result = self.vew.split(u_id=u_id, start_time=i*self.duration_mini_video, duration=self.duration_mini_video, video_input_path=v_path, output_path=output_splitted_path, mute=False)
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
                des = self.hlw.get_description(self.gem, image, query)
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
            result = self.vew.split(u_id=u_id, start_time=max(vhighlight[v_id].highlight_time - self.duration_scene//2, 0), duration=self.duration_scene, video_input_path=vhighlight[v_id].path_video, output_path=mini_video_path, mute=mute)
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
            output_dir = self.ttsw(text=des, u_id=u_id)
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
    
    def preprocess_data(self, data: dict):
        # ----check video length----
        vhighlight = {}
        # for v_name in os.listdir(folder_vtest):
        v_path = data["path_file"]
        v_name = os.path.basename(v_path)
        output_splitted_dir = os.path.dirname(v_path)
        duration = self.vew.get_duration(v_path)
        if duration < self.duration_mini_video:
            vid = f"video_{len(vhighlight)}"
            vhighlight[vid] = VideoHighlight(id=vid, path_video=v_path)
        else:
            for i in range(int(duration/self.duration_mini_video)):
                vid = f"video_{len(vhighlight)}"
                v_splitted_name = f"{os.path.splitext(v_name)[0]}_splitted_{i}{os.path.splitext(v_name)[1]}"
                output_splitted_path = f"{output_splitted_dir}{os.sep}{v_splitted_name}"
                result = self.vew.split(u_id=data["sess_id"], start_time=i*self.duration_mini_video, duration=self.duration_mini_video, video_input_path=v_path, output_path=output_splitted_path, mute=False)
                if result["success"]:
                    vhighlight[vid] = VideoHighlight(id=vid, path_video=result["path_video"])
        #///////////////////////////
        
        #----highlight and get image----
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
                duration = self.vew.get_duration(vh.path_video)
                vh.highlight_time = duration/2
            image = self.hlw.get_image_from_timestamp(vh.path_video, int(vh.highlight_time))
            # cv2.imwrite(f"./src/static/image_highlight/{vid}.jpg", image)
        #///////////////////////////////
            #----gen description----
            des = self.hlw.get_description(self.gem, image, "Describe the image")
            descriptions[vid] = des["description_vi"]
            #///////////////////////
        print(descriptions)
        
        #----write overview----
        overview = data["overview"]
        if not overview:
            result = self.hlw.write_overall_description(self.openai, description_parts=descriptions)
            overview = result["result"]
        #//////////////////////
        
        #----choose scene for each description----
        result = self.hlw.choose_scene(self.openai, descriptions=descriptions)
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
        for sn in self.SCENE_DICT.keys():
            if sn in scene_vid:
                vid = scene_vid[sn]
                list_des.append(descriptions[vid])
                list_path.append(vhighlight[vid].path_video)
                list_htime.append(vhighlight[vid].highlight_time)
            else:
                list_des.append("")
                list_path.append("")
                list_htime.append(0)
        print(f"----list_des: {list_des}")
        print(f"----list_path: {list_path}")
        print(f"----list_htime: {list_htime}")
        
        category = "other"
        if data["category"]:
            category = data["category"]
        
        response = {
            "list_des": list_des,
            "list_path": list_path,
            "list_htime": list_htime,
            "overview": overview,
            "category": category
        }
        
        return response
    
    def make_mv(self,):
        pass

if __name__=="__main__":
    SECRET_KEY = os.getenv('SECRET_KEY', "MMV")
    token = os.getenv("API_KEY", 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5IjoiQUl6YVN5QS12aGZOalRFYmNzOUNDTHNDbmIyMmdDQjFtU0tMeWZ3In0.iUeorjiPqQ0XSCGovWw0gEY9EAg-SxVedUWdvZt4X94')
    API_KEY_GEM = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
    token = os.getenv("API_KEY", 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcGlfa2V5Ijoic2stcHJvai1QSDNHNnlMVEticmdvaU9ieTA4YlVMNHc0eVYxR3NJa25IeEltTl9VMFI1WmVsOWpKcDI0MzZuNUEwOTdVdTVDeXVFMDJha1RqNVQzQmxia0ZKX3dJTUw2RHVrZzh4eWtsUXdsMTN0b2JfcGVkV1c0T1hsNzhQWGVIcDhOLW1DNjY1ZE1CdUlLMFVlWEt1bzRRUnk2Ylk1dDNYSUEifQ.2qjUENU0rafI6syRlTfnKIsm6O4zuhHRqahUcculn8E')
    API_KEY_OPENAI = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["api_key"]
    
    vm = VideoMaketing(api_key_openai=API_KEY_OPENAI,api_key_gem=API_KEY_GEM)
    u_id = "spa"
    # vm.make2(u_id, "Give me a marketing video that introduces the MQ spa")
    
    data = {"sess_id":"aaa", "path_file":"./src/static/short_videos/spa/5.mp4"}
    vm.preprocess_data(data=data)
    
    
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
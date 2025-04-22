import sys
from pathlib import Path 
FILE = Path(__file__).resolve()
DIR = FILE.parents[0]
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from StyleTTS2.inference import StyleTTS2
import os
import soundfile as sf
import torch

class TTS(object):
    def __init__(self, 
                 model_path: str="./weights/style_tts2/model.pth", 
                 config_path: str="./weights/style_tts2/config.yml",
                 reference_path: list=[f"{DIR}/StyleTTS2/reference_audio/vn_3.wav"],
                 nltk_data_path: str="./weights/nltk_data",
                 output_dir: str=f"{DIR}/static/audio_transcribe",
                 device: str="cpu"):
        self.model_path = model_path
        self.output_dir = output_dir
        self.speakers = {}
        for i, path in enumerate(reference_path, 1):
            self.speakers[f"id_{i}"] = {
                                "path": path,   #Ref audio path
                                "lang": "vi",                           #Default language
                                "speed": 1.0,                           #Speaking speed
                            }
        # self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.device = 'cuda' if torch.cuda.is_available() and device!="cpu" else 'cpu'
        self.model = StyleTTS2(config_path, self.model_path, nltk_data_path).eval().to(self.device)

    def __call__(self, text: str, u_id: str, default_speaker: str="[id_1]", avg_style: bool=True, stabilize: bool=True, denoise: float=0.6, n_merge: int=20):
        with torch.no_grad():
            styles = self.model.get_styles(self.speakers, denoise, avg_style)
            r = self.model.generate(text, styles, stabilize, n_merge, default_speaker)
            output_dir = os.path.join(self.output_dir, u_id)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            n_file = len(os.listdir(output_dir))
            output_dir = f"{output_dir}{os.sep}{n_file}.wav"
            with open(output_dir, "wb") as f:
                sf.write(f.name, r, 24000)
            return output_dir

if __name__=="__main__":
    tts = TTS()
    # text = '''[id_1][en-us]{What's up hommie}, dạo này đang học tí [en-us]{English}. Thấy bảo [en-us]{Building a strong vocabulary} khá là quan trọng. [en-us]{Bro} thấy sao?

    # [id_1][en-us]{That's right}, tôi thấy [en-us]{bro} nên bắt đầu với việc đọc sách và báo tiếng Anh để quen với cách sử dụng từ, cũng như tập trung vào [en-us]{listening exercises} để cải thiện khả năng nghe.

    # [id_1]Nghe nói rằng [en-us]{speaking practice} là bước quan trọng để giao tiếp tự tin. [en-us]{Bro} có muốn luyện tập với tôi không?

    # [id_1][en-us]{For sure my hommie} à, cứ cho mình cái hẹn nhé.
    # '''
    text = "mình muốn ra nước ngoài để tiếp xúc nhiều công ty lớn, sau đó mang những gì học được về việt nam giúp xây dựng các công trình tốt hơn"
    tts(text=text, u_id="abcd")

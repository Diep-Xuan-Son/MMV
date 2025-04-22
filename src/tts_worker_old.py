import os
import re
import numpy as np
import soundfile as sf
from omegaconf import OmegaConf
from importlib.resources import files

from f5_tts.infer.utils_infer import (
    mel_spec_type,
    target_rms,
    cross_fade_duration,
    nfe_step,
    cfg_strength,
    sway_sampling_coef,
    speed,
    fix_duration,
    infer_process,
    load_model,
    load_vocoder,
    preprocess_ref_audio_text,
    remove_silence_for_generated_wav,
)
from f5_tts.model import DiT, UNetT  # noqa: F401. used for config

import sys
from pathlib import Path 
FILE = Path(__file__).resolve()
DIR = FILE.parents[0]
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

class TTS(object):
    def __init__(self, 
                 model_path: str="./weights/f5_tts_model/model_500000.pt", 
                 vocoder_local_path: str="./weights/vocos_24khz",
                 vocab_file_path: str="./weights/f5_tts_model/vocab_500000.txt",
                 output_dir: str=f"{DIR}/static/audio_transcribe"):
        self.model_path = model_path
        self.ref_audio = f"{DIR}/f5_tts/reference_data/ref.wav"
        self.ref_text = "cả hai bên hãy cố gắng hiểu cho nhau"
        self.vocoder_name = "vocos"
        self.output_dir = output_dir

        # ----Load vocoder----
        self.vocoder = load_vocoder(vocoder_name=self.vocoder_name, is_local=True, local_path=vocoder_local_path)

        # ----Load model tts----
        model_cfg = OmegaConf.load(str(files("f5_tts").joinpath(f"configs/F5TTS_Base.yaml"))).model
        model_cls = globals()[model_cfg.backbone]
        self.ema_model = load_model(model_cls, model_cfg.arch, model_path, mel_spec_type=self.vocoder_name, vocab_file=vocab_file_path)

    def __call__(self, gen_text: str, speed: float=1.0, save_chunk: bool=False, remove_silence: bool=False, u_id: str="abcd"):
        reg1 = r"(?=\[\w+\])"
        chunks = re.split(reg1, gen_text)
        reg2 = r"\[(\w+)\]"
        generated_audio_segments = []
        for text in chunks:
            if not text.strip():
                continue
            match = re.match(reg2, text)
            text = re.sub(reg2, "", text)
            gen_text_ = text.strip()
            audio_segment, final_sample_rate, spectragram = infer_process(
                self.ref_audio,
                self.ref_text,
                gen_text,
                self.ema_model,
                self.vocoder,
                mel_spec_type=self.vocoder_name,
                target_rms=target_rms,
                cross_fade_duration=cross_fade_duration,
                nfe_step=nfe_step,
                cfg_strength=cfg_strength,
                sway_sampling_coef=sway_sampling_coef,
                speed=speed,
                fix_duration=fix_duration,
            )
            generated_audio_segments.append(audio_segment)

            if save_chunk:
                if len(gen_text_) > 200:
                    gen_text_ = gen_text_[:200] + " ... "
                sf.write(
                    os.path.join(output_dir, f"{len(generated_audio_segments)-1}_{gen_text_}.wav"),
                    audio_segment,
                    final_sample_rate,
                )

        if generated_audio_segments:
            final_wave = np.concatenate(generated_audio_segments)

            output_dir = os.path.join(self.output_dir, u_id)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            n_file = len(os.listdir(output_dir))

            with open(f"{output_dir}{os.sep}{n_file}.wav", "wb") as f:
                sf.write(f.name, final_wave, final_sample_rate)
                # Remove silence
                if remove_silence:
                    remove_silence_for_generated_wav(f.name)
                print(f.name)

if __name__=="__main__":
    tts = TTS()
    tts(gen_text="mình muốn ra nước ngoài để tiếp xúc nhiều công ty lớn, sau đó mang những gì học được về việt nam giúp xây dựng các công trình tốt hơn")

import os
import re as regex
import time
import random
import asyncio
import subprocess

import sys
from pathlib import Path 
FILE = Path(__file__).resolve()
DIR = FILE.parents[0]
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

class VideoEditorWorker(object):
    def __init__(self, 
                dir_info_scene_change: str=f"{DIR}{os.sep}static{os.sep}info_scene_change",
                duration_effect: int=2):
        super().__init__()
        self.dir_info_scene_change = dir_info_scene_change
        self.duration_effect = duration_effect
        self.num_word_per_2second = 10

    async def detect_scene_change(self, u_id: str, video_path: str, threshold: float=0.3):
        print(f"----running detect_scene_change----")
        output_dir = os.path.join(self.dir_info_scene_change, u_id)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        proc = await asyncio.create_subprocess_exec('ffmpeg', '-i', video_path, '-vf', f'select=gt(scene\\,{threshold}),metadata=print:file={output_dir}{os.sep}{os.path.basename(video_path)}_scenes.txt', '-f', 'null', '-', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stdout, stderr = await proc.communicate()
        return {"success": True}

    async def split(self, u_id: str, start_time: float, duration: float, video_input_path: str, output_path: str, mute: bool, fast: bool):
        print(f"----running split----")
        # output_dir = os.path.join(self.dir_split_video, u_id)
        # if not os.path.exists(output_dir):
        #     os.makedirs(output_dir)
        if not output_path.endswith(".mp4"):
            output_path += ".mp4"
        # output_path_video = f"{output_dir}{os.sep}{output_name}"
        # if os.path.exists(output_path):
        #     return {"success": True, "path_video": output_path}
        if mute:
            if fast:
                cmd = ['ffmpeg', "-y", "-ss", f"{start_time}", "-i", video_input_path, "-t", f"{duration}", "-an", "-c", "copy", output_path]
            else:
                cmd = ['ffmpeg', "-y", "-i", video_input_path, "-ss", f"{start_time}", "-t", f"{duration}", "-an", "-c:v", "libx264", "-crf", "20", output_path]
        else:
            if fast:
                cmd = ['ffmpeg', "-y", "-ss", f"{start_time}", "-i", video_input_path, "-t", f"{duration}", "-c", "copy", output_path]
            else:
                cmd = ['ffmpeg', "-y", "-i", video_input_path, "-ss", f"{start_time}", "-t", f"{duration}", "-c:v", "libx264", "-crf", "20", output_path]
            
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stdout, stderr = await proc.communicate()
        return {"success": True, "path_video": output_path}

    async def merge(self, list_video_path: list, path_video_merged: str):
        print(f"----running merge----")
        # path_info_merged = f'{os.path.splitext(path_video_merged)[0]}.txt'
        path_info_merged = path_video_merged.replace(".mp4", ".txt")
        ftxt = open(path_info_merged, 'w')
        for v in list_video_path:
            ftxt.write(f"file '{v}'\n")
        cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-y', '-i', path_info_merged, '-c', 'copy', path_video_merged]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stdout, stderr = await proc.communicate()
        return {"success": True}

    async def add_text(self, text: str, video_input_path: str, video_output_path: str, fast: bool, start_time: float=0):
        print(f"----running add_text----")
        list_word = regex.sub(r'[^\w\s]', '', text).split()
        text_infos = ""
        for i in range(0,len(list_word),self.num_word_per_2second):
            text_mini = " ".join(list_word[i:i+self.num_word_per_2second])
            len_text_mini = len(text_mini)
            text_mini = ""
            for j, w in enumerate(list_word[i:i+self.num_word_per_2second]):
                text_mini += w + " "
                text_infos += f"drawtext=text={text_mini}:fontcolor=yellow:fontsize=h/30:box=1:boxcolor=black@0.5:boxborderw=5:x=(w-{len_text_mini}*h/55)/2:y=h-th-100:enable='between(t,{2*i//self.num_word_per_2second + j*2/self.num_word_per_2second + start_time},{2*i//self.num_word_per_2second+(j+1)*2/self.num_word_per_2second + start_time})',"
                # text_infos += f"drawtext=text={text_mini}:fontcolor=white:fontsize=24:box=1:boxcolor=black@0.5:boxborderw=5:x=(w-text_w)/2:y=h-th-10:enable='between(t,{2*i//8 + j*2/8},{2*i//8+2})',"
        if fast:
            cmd = ['ffmpeg', "-y", "-i", video_input_path, "-vf", text_infos[:-1], "-c:v", "h264_nvenc", "-preset", "fast", "-crf", "23", "-c:a", "copy", video_output_path]
        else:
            cmd = ['ffmpeg', "-y", "-i", video_input_path, "-vf", text_infos[:-1], "-c:v", "libx264", "-c:a", "copy", video_output_path]
        # print(cmd)
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stdout, stderr = await proc.communicate()
        return {"success": True}
    
    async def get_duration(self, vinput: str):
        # def _probe():
        #     return ffmpeg.probe(vinput)
        # probe = await asyncio.to_thread(_probe)
        # duration = float(probe["format"]["duration"])
        
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration","-of", "default=noprint_wrappers=1:nokey=1", vinput]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {stderr.decode().strip()}")
        return float(stdout.decode().strip())
        
    async def add_effect(self, effect_type: list, list_video_path: list, video_output_path: str, fast: bool):
        print(f"----running add_effect----")
        inputs = []
        info_convert = ""
        video_fades = ""
        last_fade_output = "vid0"
        # video_length = 0
        for i, inp in enumerate(list_video_path[::-1]):
            i_choice = random.choice(range(len(effect_type)))
            duration = await self.get_duration(inp)
            # duration = 8
            inputs += ["-i", inp]
            info_convert += f'[{i}:v]fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2[vid{i}];'
            if i==0:
                # video_length += duration
                continue
            next_fade_output = f"v{i-1}{i}"
            if i == len(list_video_path)-1:
                video_fades += f'[vid{i}][{last_fade_output}]xfade=transition={effect_type[i_choice]}:duration={self.duration_effect}:offset={round(duration-2)}'
            else:
                video_fades += f'[vid{i}][{last_fade_output}]xfade=transition={effect_type[i_choice]}:duration={self.duration_effect}:offset={round(duration-2)}[{next_fade_output}];'
                last_fade_output = next_fade_output
                # video_length += duration
        # print(info_convert)
        # print(video_fades)
        # exit()
        # cmd = ['ffmpeg', '-y'] + inputs + ['-filter_complex', f'[0:v]fps=30,format=yuv420p[vid1]; [1:v]fps=30,format=yuv420p[vid2];[vid1][vid2]xfade=transition={effect_type}:duration=2:offset=60,format=yuv420p', video_output_path]
        if fast:
            cmd = ['ffmpeg', '-y'] + inputs + ['-filter_complex', f'{info_convert}{video_fades}', "-c:v", "h264_nvenc", "-preset", "fast", "-c:a", "copy", "-crf", "20", video_output_path]
        else:
            cmd = ['ffmpeg', '-y'] + inputs + ['-filter_complex', f'{info_convert}{video_fades}', "-c:v", "libx264", "-crf", "20", video_output_path]
        print(f"----cmd: {cmd}")
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stdout, stderr = await proc.communicate()
        return {"success": True}

    async def change_ratio(self, scale: list, video_input_path: str, video_output_path: str):
        print(f"----running change_ratio----")
        cmd = ['ffmpeg', '-y', "-i", video_input_path, '-vf', f'scale={scale[0]}:{scale[1]}', video_output_path]
        print(f"----cmd: {cmd}")
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stdout, stderr = await proc.communicate()
        return {"success": True}

    async def add_audio(self, video_input_path: str, list_audio_path: list, list_audio_time: list, audio_background_path: str, video_output_path: str):   #audio time in miliseconds
        print(f"----running add_audio----")
        if len(list_audio_path)!=len(list_audio_time):
            return {"success": False, "error": "The number of time start and the number of audio path is not the same"}
        a_inputs = ["-i", video_input_path]
        a_info = ""
        a_ids = ""
        list_audio_time += [-1]
        for i, inp in enumerate(list_audio_path):
            # duration_audio = float(ffmpeg.probe(inp)["format"]["duration"])
            # n_audio = int((list_audio_time[i+1]-list_audio_time[i])*1e-3//duration_audio)-1 if list_audio_time[i+1]>=0 else 0
            # a_inputs += ["-stream_loop", f"{n_audio}", "-i", inp]
            a_inputs += ["-stream_loop", "0", "-i", inp]
            a_info += f"[{i+1}:a]adelay={list_audio_time[i]}|{list_audio_time[i]},volume=100[a{i+1}];"
            a_ids += f"[a{i+1}]"
        # adding background audio
        duration_audio = await self.get_duration(audio_background_path)
        duration_video_input = await self.get_duration(video_input_path)
        n_audio = int(duration_video_input//duration_audio)-1 # subtract 1 because it is once itself
        a_inputs += ["-stream_loop", f"{n_audio}", "-i", audio_background_path]
        a_info += f"[{len(list_audio_path)+1}:a]adelay=0|0,volume=5[a{len(list_audio_path)+1}];"
        a_ids += f"[a{len(list_audio_path)+1}]"

        cmd = ['ffmpeg', '-y'] + a_inputs + ['-filter_complex', f'{a_info}{a_ids}amix=inputs={len(list_audio_path)+1}[a]', '-map', '0:v', '-map', '[a]', "-c:v", "copy", "-c:a", "aac", "-shortest", video_output_path]
        print(f"----cmd: {cmd}")
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stdout, stderr = await proc.communicate()
        return {"success": True}

if __name__=="__main__":
    vew = VideoEditorWorker()
    # result = asyncio.run(vew.detect_scene_change(u_id="abc", video_path="./data_storage/test/5wsDJfdPuq0.mp4"))
    # print(f"----result: {result}")
    # exit()

    # output_dir = os.path.join(f"{DIR}{os.sep}static{os.sep}videos_splitted", "abc")
    # if not os.path.exists(output_dir):
    #     os.makedirs(output_dir)
    # output_path = f"{output_dir}{os.sep}{"test2"}"
    # result = vew.split(u_id="abc", start_time=1, duration=60, video_input_path="./data_test/vtv24.mp4", output_path=output_path, mute=False, fast=True)
    # print(f"----result: {result}")

    # result = asyncio.run(vew.add_text('Chào mừng bạn đến với MQ Spa, nơi không gian sang trọng và dịch vụ hoàn hảo hòa quyện. Hãy cùng khám phá những trải nghiệm tuyệt vời mà chúng tôi mang đến cho bạn.', "./data_test/fire2.mp4", "abc.mp4", True))
    # print(f"----result: {result}")
    # exit()

    result = asyncio.run(vew.add_effect(["circleopen","fade","hrslice","radial"], ['/home/mq/disk2T/son/code/GitHub/MMV/src/static/final_video/spa2/final_mini_video_text_7.mp4', '/home/mq/disk2T/son/code/GitHub/MMV/src/static/final_video/spa2/final_mini_video_text_6.mp4', '/home/mq/disk2T/son/code/GitHub/MMV/src/static/final_video/spa2/final_mini_video_text_5.mp4'], "abc.mp4", True))
    print(f"----result: {result}")
    exit()

    # result = vew.change_ratio([640,480], "./data_test/fire2.mp4", "fire22.mp4")
    # print(f"----result: {result}")

    # result = vew.add_audio("abc.mp4", ["./data_test/bm1.mp3", "./data_test/bm1.mp3"], [0,10000], audio_background_path="./data_test/bm1.mp3", "abc1.mp4")
    # print(f"----result: {result}")
    
    # result = vew.get_duration("./src/static/videos_splitted/spa/4_splitted_0.mp4")
    # print(f"----result: {result}")
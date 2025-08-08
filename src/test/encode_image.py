import subprocess


cmd = ['ffmpeg', "-y", "-i", img_input, "-c:v", "libx264", "-c:a", "copy", img_output]
subprocess.run(cmd, check=True)




import ffmpeg

stream = ffmpeg.input(img_path + '.jpg')
stream = ffmpeg.output(stream, img_path + '.jpg')
ffmpeg.run(stream, overwrite_output=True)

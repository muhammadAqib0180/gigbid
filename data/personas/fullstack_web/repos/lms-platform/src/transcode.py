subprocess.run(["ffmpeg", "-i", src, "-c:v", "libx264", "-f", "hls", out], check=True)

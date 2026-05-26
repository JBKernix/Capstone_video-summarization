import ffmpeg
import json

video_file = "video.mp4"
probe = ffmpeg.probe(video_file)
video_stream = next(
    stream for stream in probe['streams']
    if stream['codec_type'] == 'video'
)
audio_exists = any(
    stream['codec_type'] == 'audio'
    for stream in probe['streams']
)
video_info = {
    "파일명": video_file,
    "해상도": f"{video_stream['width']}x{video_stream['height']}",
    "FPS": eval(video_stream['r_frame_rate']),
    "코덱": video_stream['codec_name'],
    "영상 길이(초)": probe['format']['duration'],
    "오디오 포함 여부": audio_exists
}
print(json.dumps(video_info, indent=4, ensure_ascii=False))
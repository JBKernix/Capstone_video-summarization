import subprocess

input_video = "video.mp4"
output_audio = "audio.wav"

# FFmpeg 명령어를 리스트 형태로 구성
command = ["ffmpeg", "-i", input_video, "-vn", "-acodec", "pcm_s16le", output_audio]

try:
    # subprocess를 사용하여 직접 명령어 실행
    subprocess.run(command, check=True)
    print("오디오 추출 완료")
except FileNotFoundError:
    print("오류: 시스템에 FFmpeg가 설치되어 있지 않거나 환경 변수가 설정되지 않았습니다.")
except subprocess.CalledProcessError:
    print("오류: 오디오 추출 과정에서 문제가 발생했습니다.")
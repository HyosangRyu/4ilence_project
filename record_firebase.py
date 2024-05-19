#-------------------------------------------------------
# 파이어베이스에서 데이터 가져와 녹음시작 (저장경로:record)
#-------------------------------------------------------
import os
import pyaudio
import wave
import datetime
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# Firebase 설정
cred = credentials.Certificate("/home/pi/practice/google-services.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://record-ad034-default-rtdb.firebaseio.com/'
})

# 녹음 설정
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 10
current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")  # 현재 시간을 yyyyMMdd_HHmmss 형식으로 포맷



# 파일 저장 경로 설정
save_directory = "/home/pi/record"
if not os.path.exists(save_directory):
    os.makedirs(save_directory)  # 저장할 디렉토리가 없으면 생성
WAVE_OUTPUT_FILENAME = os.path.join(save_directory, f"record_{current_time}.wav") # 출력 파일 이름에 현재 날짜와 시간 포함

# Firebase 데이터베이스에서 신호 읽기
def wait_for_start_signal():
    start_signal_ref = db.reference('start_signal')
    start_signal = start_signal_ref.get()
    while start_signal != 1:
        start_signal = start_signal_ref.get()

# 녹음 함수
def record_audio():
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("녹음을 시작합니다...")
    frames = []
    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK)
        frames.append(data)
    print("녹음이 완료되었습니다.")
    stream.stop_stream()
    stream.close()
    audio.terminate()
    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    print(f"파일이 저장되었습니다: {WAVE_OUTPUT_FILENAME}")
    return True

# 메인 루프
while True:
    print("녹음 시작 신호를 기다리는 중...")
    wait_for_start_signal()
    if record_audio():
        db.reference('start_signal').set(0)  # 녹음 완료 후 신호 리셋

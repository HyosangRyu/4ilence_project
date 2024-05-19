#---------------------------------
# 바로 녹음시작해서 파일명 오늘날짜로
#---------------------------------
import pyaudio
import wave
import datetime

# 녹음 설정
FORMAT = pyaudio.paInt16  # 데이터 포맷
CHANNELS = 1              # 모노, 2는 스테레오
RATE = 44100              # 샘플링 레이트
CHUNK = 1024              # 데이터 블록의 크기
RECORD_SECONDS = 10       # 녹음할 시간(초)
current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")  # 현재 시간을 yyyyMMdd_HHmmss 형식으로 포맷
WAVE_OUTPUT_FILENAME = f"record_{current_time}.wav"  # 출력 파일 이름에 현재 날짜와 시간 포함

# PyAudio 객체 초기화
audio = pyaudio.PyAudio()

# 녹음을 위한 스트림 열기
stream = audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True,
                    frames_per_buffer=CHUNK)

print("녹음을 시작합니다...")

frames = []

# 지정된 시간 동안 오디오 데이터 읽기
for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK)
    frames.append(data)

print("녹음이 완료되었습니다.")

# 스트림 정지 및 닫기
stream.stop_stream()
stream.close()
audio.terminate()

# 녹음 데이터를 WAV 파일로 저장
wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
wf.setnchannels(CHANNELS)
wf.setsampwidth(audio.get_sample_size(FORMAT))
wf.setframerate(RATE)
wf.writeframes(b''.join(frames))
wf.close()

print(f"파일이 저장되었습니다: {WAVE_OUTPUT_FILENAME}")

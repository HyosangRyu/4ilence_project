#--------------------------------------
#ver1
#---------------------------------------
import os
import pyaudio
import wave
import numpy as np
import matplotlib.pyplot as plt
import firebase_admin
from firebase_admin import credentials, db, storage
from datetime import datetime
#import time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Firebase 설정 (test)
cred = credentials.Certificate("/home/pi/practice/google-test.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://test-a974c-default-rtdb.firebaseio.com/',
    'storageBucket': 'test-a974c.appspot.com'
})

# InfluxDB 접속 설정
url = "http://192.168.137.146:8086"
token = "CfguosLPqLJ-ZU0t0OUjs2WQ8Hupjw0MCHDXKhze5MAyMGZUCG3W9euF72wgCggkfsTRfDbuxkxIcOoyn93cYw=="
org = "7588d9ea22db1d3d"
bucket = "decibel"

# InfluxDB 클라이언트 생성
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

# 녹음 설정
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 10
current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
time = datetime.now()
timestamp = int(time.timestamp() * 1e9)

# 파일 저장 경로 설정
save_directory = "/home/pi/record"
if not os.path.exists(save_directory):
    os.makedirs(save_directory)
WAVE_OUTPUT_FILENAME = os.path.join(save_directory, f"record_{current_time}.wav")
GRAPH_OUTPUT_FILENAME = os.path.join(save_directory, f"decibel_graph_{current_time}.png")

# Firebase 데이터베이스에서 신호 읽기 // record
def wait_for_start_signal():
    record_ref = db.reference('F_4ilence/record') 
    record = record_ref.get()
    while record != "1":
        record = record_ref.get()

# 녹음 함수
def record_audio():
    WAVE_OUTPUT_FILENAME = os.path.join(save_directory, f"record_{current_time}.wav")

    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("녹음을 시작합니다...")
    frames = []
    
    # 녹음 중 데이터 전송
    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK)
        frames.append(data)
        
        # 데시벨 계산
        decoded = np.frombuffer(data, dtype=np.int16)
        if np.mean(decoded**2) != 0:
            rms = 20 * np.log10(np.sqrt(np.mean(decoded**2)))
            point = Point("decibel").tag("location", "home").field("level", rms).time(timestamp + i * CHUNK * 1e9 / RATE, WritePrecision.NS)
            write_api.write(bucket=bucket, org=org, record=point)
        
    print("녹음이 완료되었습니다.")
    stream.stop_stream()
    stream.close()
    audio.terminate()

    # 파일 저장
    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

    # 데시벨 측정 및 그래프 생성
    decoded = np.frombuffer(b''.join(frames), dtype=np.int16)
    rms_values = [20 * np.log10(np.sqrt(np.mean(decoded[i:i+CHUNK]**2))) if np.mean(decoded[i:i+CHUNK]**2) != 0 else 0 for i in range(0, len(decoded), CHUNK)]
    plt.figure(figsize=(10, 4))
    plt.plot(rms_values, label="Decibel Level")
    plt.xlabel("Time (in chunks)")
    plt.ylabel("Decibel (dB)")
    plt.title("Decibel Level Over Time")
    plt.legend()
    plt.savefig(GRAPH_OUTPUT_FILENAME)
    plt.close()
    print("그래프 저장이 완료되었습니다.")


    # 데시벨 측정 및 InfluxDB에 데이터 업로드
    decoded = np.frombuffer(b''.join(frames), dtype=np.int16)
    rms_values = [20 * np.log10(np.sqrt(np.mean(decoded[i:i+CHUNK]**2))) if np.mean(decoded[i:i+CHUNK]**2) != 0 else 0 for i in range(0, len(decoded), CHUNK)]
    for i, rms in enumerate(rms_values):
        point = Point("decibel").tag("device", "raspberry_pi").field("level", rms).time(time, WritePrecision.NS)
        write_api.write(bucket=bucket, org=org, record=point)
    print(f"파일이 저장되었습니다: {WAVE_OUTPUT_FILENAME}")
    return True




# 메인 루프

def update_logs(current_time):
    # 기존 로그 값을 임시 리스트에 저장
    logs = [db.reference(f'Log/log{i}').get() for i in range(1, 10)]

    # 로그 값을 한 칸씩 뒤로 밀기
    for i in range(8, 0, -1):  # log9는 필요 없으므로 업데이트에서 제외
        if logs[i-1] is not None:  # 비어있지 않은 경우에만 업데이트
            db.reference(f'Log/log{i+1}').set(logs[i-1])

    # log1에 새로운 current_time 저장
    db.reference('Log/log1').set(current_time)


while True:
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("녹음 시작 신호를 기다리는 중...")
    wait_for_start_signal()
    if record_audio():
        db.reference('F_4ilence/record').set(0)  # 녹음 완료 후 신호 리셋
        update_logs(current_time)  # 로그 업데이트 함수 호출
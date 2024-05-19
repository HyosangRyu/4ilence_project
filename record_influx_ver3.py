#--------------------------------------
# ver3 _ 조금 더 정확한 데시벨 측정 및 이동평균 (라즈베리파이 마이크 감도 60%로 설정 햇을 때)
#---------------------------------------
import os

#import audio
import pyaudio
import wave

#import math
import numpy as np
import math
import matplotlib.pyplot as plt
import pandas as pd

#import firebase
import firebase_admin
from firebase_admin import credentials, db, storage

#import influxdb
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

#import time
from datetime import timezone
from zoneinfo import ZoneInfo 
from datetime import datetime

# Firebase 설정 (test)
cred = credentials.Certificate("/home/pi/practice/google-test.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://test-a974c-default-rtdb.firebaseio.com/',
    'storageBucket': 'test-a974c.appspot.com'
})
#==============================================================================================================

# InfluxDB 접속 설정
url = "http://192.168.137.146:8086"
token = "CfguosLPqLJ-ZU0t0OUjs2WQ8Hupjw0MCHDXKhze5MAyMGZUCG3W9euF72wgCggkfsTRfDbuxkxIcOoyn93cYw=="
org = "7588d9ea22db1d3d"
bucket = "decibel"

# InfluxDB 클라이언트 생성
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

#==============================================================================================================

# 녹음 설정
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 10 #<<------------변경필요!!----------------
influx_time = datetime.now()
timestamp = int(influx_time.timestamp() * 1e9)

# #청각 설정
# reference_pressure = 20e-6 


# 마이크와 ADC 설정 <<------------변경필요!!----------------
mic_sensitivity = 126.0e-3  # mV/Pa, 마이크 사양에 맞게 조정
adc_max_voltage = 1.0       # V, ADC 최대 입력 전압
adc_bits = 16
max_int = 2**(adc_bits - 1) - 1
reference_pressure = 10e-2 # 기준 압력 (Pascal)

#==============================================================================================================

# 파일 저장 경로 설정
save_directory = "/home/pi/record"
if not os.path.exists(save_directory):
    os.makedirs(save_directory)

# Firebase 데이터베이스에서 신호 읽기 // record
def wait_for_start_signal():
    record_ref = db.reference('F_4ilence/record') 
    record = record_ref.get()
    while record != "1":
        record = record_ref.get()

#==============================================================================================================
# 현재 시간을 한국 시간대로 가져와서 에포크(1970-01-01)부터의 나노초를 계산합니다.
def get_nanoseconds_timestamp():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return int((now - epoch).total_seconds() * 1e9)

#rms 계산
def calculate_rms(data_chunk):
    decoded = np.frombuffer(data_chunk, dtype=np.int16)
    mean_squared = np.mean(decoded**2)
    if mean_squared == 0:
        return 0
    rms_normalized = np.sqrt(mean_squared) / max_int
    rms_voltage = rms_normalized * adc_max_voltage
    rms_pressure = rms_voltage / (mic_sensitivity / 1000)
    return rms_pressure

#==============================================================================================================

# 녹음함수
def record_audio():
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("녹음을 시작합니다...")
    frames = []
    
    for i in range(0, int(44100 / 1024 * 10)):  # RECORD_SECONDS = 10 <<------------변경필요!!----------------
        data = stream.read(1024)
        frames.append(data)

        #rms값 업로드 먼저
        rms = calculate_rms(data)
        rms = float(rms)  # 부동 소수점 수로 명시적 변환
        current_timestamp = get_nanoseconds_timestamp()
        point = Point("raw_data").tag("location", "home").field("rms_value", rms).time(current_timestamp, WritePrecision.NS)
        write_api.write(bucket=bucket, org=org, record=point)
        
    print("녹음이 완료되었습니다.")
    stream.stop_stream()
    stream.close()
    audio.terminate()

    # 현재 시간 업데이트
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")  # 현재 시간을 yyyyMMdd_HHmmss 형식으로 포맷

    # 파일명 설정
    WAVE_OUTPUT_FILENAME = os.path.join(save_directory, f"record_{current_time}.wav") # 출력 파일 이름에 현재 날짜와 시간 포함
    GRAPH_OUTPUT_FILENAME = os.path.join(save_directory, f"decibel_graph_{current_time}.png")



    # 파일 저장
    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

    # InfluxDB에서 데이터 조회 및 그래프 생성
    query_api = client.query_api()
    query = f'from(bucket: "{bucket}") |> range(start: -10s) |> filter(fn: (r) => r._measurement == "raw_data")'
    result = query_api.query(query)
    times = []
    db_values = []

    #데이터 받아와 데시벨 변환 함수 <<------------변경필요!!----------------
    for table in result:
        for record in table.records:
            rms_value = record.get_value()
            if rms_value > 0:
                db_value = 20 * np.log10(rms_value / reference_pressure)  # 참조 압력 값 설정 필요
                #db_value = rms_value  # 참조 압력 값 설정 필요
                db_values.append(db_value)
                # UTC 시간을 KST로 변환
                utc_time = record.get_time()
                kst_time = utc_time.astimezone(ZoneInfo("Asia/Seoul"))
                times.append(kst_time)




# 데이터 프레임 생성 및 이동 평균 계산
    df = pd.DataFrame({
        'Time': times,
        'Decibel': db_values
    })
    df['Moving Average'] = df['Decibel'].rolling(window=10).mean()

    # 그래프 그리기
    plt.figure(figsize=(12, 6))
    plt.plot(df['Time'], df['Decibel'], label='Original Decibel Level', alpha=0.5)
    plt.plot(df['Time'], df['Moving Average'], label='Average Decibel Level', color='red')
    plt.xlabel('Time (KST)')
    plt.ylabel('Decibel (dB)')
    plt.title('Decibel Graph (with Average)')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()
    plt.savefig(GRAPH_OUTPUT_FILENAME)
    plt.close()
    print("그래프 저장이 완료되었습니다.")

    # 업로드 함수 호출
    upload_to_firebase(GRAPH_OUTPUT_FILENAME)
    update_logs(current_time)  # 로그 업데이트 함수 호출
    print(f"그래프 파일이 Firebase에 업로드되었습니다.")
    return True


# # 기존 그래프 그리기
#     plt.figure(figsize=(10, 4))
#     plt.plot(times, db_values, label="Decibel Level")
#     plt.xlabel("Time")
#     plt.ylabel("Decibel (dB)")
#     plt.title("Decibel Graph")
#     plt.legend()
#     plt.savefig(GRAPH_OUTPUT_FILENAME)
#     plt.close()
#     print("그래프 저장이 완료되었습니다.")

#     # 업로드 함수 호출
#     upload_to_firebase(GRAPH_OUTPUT_FILENAME)
#     update_logs(current_time)  # 로그 업데이트 함수 호출
#     print(f"그래프 파일이 Firebase에 업로드되었습니다.")
#     return True

#==============================================================================================================

# 파일을 파이어베이스 스토리지에 업로드하는 함수
def upload_to_firebase(file_path):
    bucket = storage.bucket()
    blob = bucket.blob(os.path.basename(file_path))
    blob.upload_from_filename(file_path)
    print(f"Uploaded {file_path} to Firebase Storage.")

#==============================================================================================================

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
    print("녹음 시작 신호를 기다리는 중...")
    wait_for_start_signal()
    if record_audio():
        db.reference('F_4ilence/record').set(0)  # 녹음 완료 후 신호 리셋
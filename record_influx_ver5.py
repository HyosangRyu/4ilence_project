#----------------------------------------------------------------------
# ver5 _ 조금 더 정확한 데시벨 측정 및 이동평균 (새로운 마이크: 한번하고 멈춤)
#-----------------------------------------------------------------------
import os
import RPi.GPIO as GPIO

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
import time
from datetime import timezone
from zoneinfo import ZoneInfo 
from datetime import datetime, timedelta

# Firebase 설정 (test)
cred = credentials.Certificate("/home/pi/practice/google-test.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://test-a974c-default-rtdb.firebaseio.com/',
    'storageBucket': 'test-a974c.appspot.com'
})
#==============================================================================================================

# InfluxDB 접속 설정_arduino
url = "https://us-east-1-1.aws.cloud2.influxdata.com"
token = "GDQjYhX4B099737f-FbVwd-tLVAYMlFKrdoYn4Lf_4Ciflaim1j5lT-GuvvCn6GSzgTJHQYk_8gQDakx6DQ5pg=="
org = "096969adcbac8084"
bucket = "decibel"

# InfluxDB 클라이언트 생성
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

#==============================================================================================================

#led 설정
GPIO.setmode(GPIO.BCM)
GPIO.setup(17,GPIO.OUT)

# 녹음 설정
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 6 #<<------------변경필요!!----------------
influx_time = datetime.now()
timestamp = int(influx_time.timestamp() * 1e9)

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

# 로그 변환 함수
def value_to_db(value):
    return 20 * np.log10(value)

# # InfluxDB 데이터 초기화 함수
# def initialize_influxdb():
#     delete_api = client.delete_api()
#     start = "1970-01-01T00:00:00Z"
#     stop = datetime.utcnow().isoformat() + "Z"
#     delete_api.delete(start, stop, '_measurement="decibel4"', bucket=bucket, org=org)

#==============================================================================================================

# 녹음 함수
def record_audio():
    # initialize_influxdb()  # InfluxDB 데이터 초기화
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("녹음을 시작합니다...")
    frames = []
    GPIO.output(17,True)

    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK)
        frames.append(data)
        
    print("녹음이 완료되었습니다.")
    stream.stop_stream()
    stream.close()
    audio.terminate()
    GPIO.output(17,False)
    

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
    return GRAPH_OUTPUT_FILENAME, current_time

# InfluxDB에서 데이터 조회 및 데시벨 계산
def fetch_and_calculate_db():
    query = f'from(bucket: "{bucket}") |> range(start: -180s) |> filter(fn: (r) => r._measurement == "decibel4")'
    result = client.query_api().query(org=org, query=query)
    times = []
    db_values = []

    for table in result:
        for record in table.records:
            value = record.get_value()
            if value is not None:
                db_value = value_to_db(value)
                db_values.append(db_value)
                utc_time = record.get_time()
                kst_time = utc_time.astimezone(ZoneInfo("Asia/Seoul"))
                times.append(kst_time)
    return times, db_values


#==============================================================================================================

# 그래프 생성 및 저장
def create_graph(times, db_values, graph_output_filename):
    df = pd.DataFrame({
        'Time': times,
        'Decibel': db_values
    })
    df['Moving Average'] = df['Decibel'].rolling(window=10).mean()

    # 최대값 찾기
    max_value = df['Decibel'].max()
    max_time = df['Time'][df['Decibel'].idxmax()]

    # 그래프 그리기
    plt.figure(figsize=(12, 6))
    plt.plot(df['Time'], df['Decibel'], label='Original Decibel Level', alpha=0.5)
    plt.plot(df['Time'], df['Moving Average'], label='Average Decibel Level', color='red')
    plt.scatter(max_time, max_value, color='blue', zorder=5)
    plt.text(max_time, max_value, f'{max_value:.2f} dB', color='blue', fontsize=12, ha='center', va='bottom')
    plt.xlabel('Time (KST)')
    plt.ylabel('Decibel (dB)')
    plt.title('Decibel Graph (with Average)')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(graph_output_filename)
    plt.show()
    plt.close()
    print("그래프 저장이 완료되었습니다.")

    # 업로드 함수 호출
    upload_to_firebase(graph_output_filename)
    print(f"그래프 파일이 Firebase에 업로드되었습니다.")



#==============================================================================================================

# 파일을 파이어베이스 스토리지에 업로드하는 함수
def upload_to_firebase(file_path):
    bucket = storage.bucket()
    blob = bucket.blob(os.path.basename(file_path))
    blob.upload_from_filename(file_path)
    print(f"Uploaded {file_path} to Firebase Storage.")

#==============================================================================================================


# log 업데이트
def update_logs(current_time):
    # 기존 로그 값을 임시 리스트에 저장
    logs = [db.reference(f'Log/log{i}').get() for i in range(1, 10)]

    # 로그 값을 한 칸씩 뒤로 밀기
    for i in range(8, 0, -1):  # log9는 필요 없으므로 업데이트에서 제외
        if logs[i-1] is not None:  # 비어있지 않은 경우에만 업데이트
            db.reference(f'Log/log{i+1}').set(logs[i-1])

    # log1에 새로운 current_time 저장
    db.reference('Log/log1').set(current_time)




def main():
    print("녹음 시작 신호를 기다리는 중...")
    wait_for_start_signal()
    graph_output_filename, current_time = record_audio()  # 녹음 및 데이터 초기화
    db.reference('F_4ilence/record').set("0")  # 녹음 완료 후 신호 리셋
    print("6초 동안의 데시벨 데이터를 기다립니다...")
    time.sleep(6)  # 데이터 수집을 위한 대기 시간
    times, db_values = fetch_and_calculate_db()  # InfluxDB에서 데이터 조회 및 데시벨 계산
    if times and db_values:
        create_graph(times, db_values, graph_output_filename)  # 그래프 생성 및 저장
        update_logs(current_time)  # 로그 업데이트 함수 호출
    else:
        print("No data fetched from InfluxDB.")
        update_logs(current_time)  # 로그 업데이트 함수 호출

if __name__ == "__main__":
    main()
import base64
import io
import json
import os
from datetime import datetime, timedelta, timezone

import japanize_matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, render_template, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (ApiClient, Configuration, MessagingApi,
                                  PostbackAction, PushMessageRequest,
                                  ReplyMessageRequest, TextMessage)
from linebot.v3.webhooks import (FollowEvent, MessageEvent, PostbackEvent,
                                 TextMessageContent)
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split

load_dotenv()

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

###########################
## ライン
configuration = Configuration(access_token=os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

@app.route("/callback", methods=['POST'])
def callback():
	# get X-Line-Signature header value
	signature = request.headers['X-Line-Signature']

	# get request body as text
	body = request.get_data(as_text=True)
	app.logger.info("Request body: " + body)

	# handle webhook body
	try:
		handler.handle(body, signature)
	except InvalidSignatureError:
		app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
		abort(400)

	return 'OK'

# @handler.add(MessageEvent, message=TextMessageContent)
# def handle_message(event):
#   ## APIインスタンス化
# 	with ApiClient(configuration) as api_client:
# 		line_bot_api = MessagingApi(api_client)

# 	## 受信メッセージの中身を取得
# 	received_message = event.message.text
  # try:
  #   setting = float(received_message)
  #   ## 返信メッセージ編集
  #   reply = f'本日の設定温度を{received_message}度として記録しました！'
  # except ValueError:
  #   reply = '数値を入力してね！'


#   line_bot_api.reply_message(ReplyMessageRequest(
#     replyToken=event.reply_token,
#     messages=[TextMessage(text=reply)]
#   ))


###########################
@app.route("/")
def index():
    return "Welcome to BestSleeping App!"


@app.route("/weather", methods=["GET"])
def weather():
    BASE_URL = "http://api.openweathermap.org/data/2.5/forecast?"
    api_key = os.getenv("OPEN_WEATHER_API")
    url = BASE_URL+"id={cityID}&units=metric&APPID={key}".format(cityID="1857140", key=api_key)

    response = requests.get(url)
    api_data = response.json()
    res_data = []
    for entry in api_data["list"][:4]:  # 上から4件に限定
        # unix to jpt
        dt_jst = datetime.fromtimestamp(entry["dt"], tz=timezone.utc) + timedelta(hours=9)
        
        data = {
            "dt": dt_jst.strftime("%Y-%m-%d %H:%M:%S"),
            "temp": entry["main"]["temp"],
            "temp_min": entry["main"]["temp_min"],
            "temp_max": entry["main"]["temp_max"],
            "weather": entry["weather"][0]["main"]
        }
        res_data.append(data)

    print(json.dumps(res_data, indent=4))

    return jsonify({
        "message": "successfully get weather",
        "response": res_data
    })


@app.route("/aircon/set", methods=["POST"])
def aircon():
    json = request.get_json()
    print(json) #[debug]
    responses = []
    received_message = json['events'][0]['message']['text']
    isSuccess = False
    try:
      if json['events'][0]['type'] != "text":
        return "その他のイベント"
      setting = float(received_message)

      reply = f'本日の設定温度を{received_message}度として記録しました！'
      isSuccess = True
    except ValueError:
      reply = f'数値を入力してください！'

    responses.append(LineReplyMessage.make_text_response(reply))
    reply_token = json['events'][0]['replyToken']
    LineReplyMessage.send_reply(reply_token, responses)
    print(reply)
    if isSuccess:
      return f'設定温度を{setting}度に設定しました'
    else:
      return "設定温度の記録に失敗しました"

def img2html(fig):
    HTML_TMP = """
    <!doctype html>
    <html lang="ja">
    <body>
        <h1>エアコン設定温度の予測</h1>
        <p>以下は室温とエアコン設定温度の関係を示すグラフです。</p>
        <img src="data:image/png;base64,{image_bin}">
    </body>
    </html>
    """
    sio = io.BytesIO()
    fig.savefig(sio, format='png')
    image_bin = base64.b64encode(sio.getvalue())
    return HTML_TMP.format(image_bin=str(image_bin)[2:-1])

@app.route("/plot")
def plot():
    # スプシデータの読み込み
    file_path = "./data/sleepingData.csv"
    data = pd.read_csv(file_path)
    data.columns = ["date", "time", "outside_temp", "room_temp", "ac_setting_temp"]

    # 睡眠開始時刻を分に変換
    data["sleep_start_minutes"] = data["time"].apply(
    lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])
    )

    # 室温を目標範囲（22~24℃）に正規化
    target_temp = 23
    data["temp_deviation"] = data["room_temp"] - target_temp

    # 特徴量と目的変数
    X = data[["outside_temp", "sleep_start_minutes"]].values  # 特徴量: 外気温と睡眠開始時刻
    y = data["ac_setting_temp"].values  # 目的変数: エアコン設定温度

    # データを訓練セットとテストセットに分割
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 線形回帰モデルの訓練
    model = LinearRegression()
    model.fit(X_train, y_train)

    # 回帰係数と切片を取得
    coef_outside_temp, coef_sleep_start = model.coef_
    intercept = model.intercept_

    # 回帰式を表示
    print(f"エアコン設定温度 (°C) = {coef_outside_temp:.2f} * 外気温 (°C) + {coef_sleep_start:.2f} * 睡眠開始時刻 (分) + {intercept:.2f}")

    # 室温が目標範囲（22～24℃）に収まるかチェック
    def calculate_optimal_ac_temp(outside_temp, sleep_start_minutes):
        # エアコン設定温度を計算
        ac_temp = coef_outside_temp * outside_temp + coef_sleep_start * sleep_start_minutes + intercept
        return round(ac_temp, 2)

    # テストデータで予測
    predicted_ac_temp = model.predict(X_test)
    mse = mean_squared_error(y_test, predicted_ac_temp)
    print(f"平均二乗誤差 (MSE): {mse:.2f}")

    # 最適なエアコン設定温度を計算
    for i in range(5):  # テスト用: 5つのデータを例示
        outside_temp = X_test[i, 0]
        sleep_start_minutes = X_test[i, 1]
        ac_temp = calculate_optimal_ac_temp(outside_temp, sleep_start_minutes)
        print(f"外気温: {outside_temp}℃, 睡眠開始: {sleep_start_minutes}分 → エアコン設定温度: {ac_temp}℃")

    # 可視化: 室温 vs エアコン設定温度
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(data["room_temp"], data["ac_setting_temp"], color="blue", label="データポイント")
    ax.axvline(x=23, color="red", linestyle="--", label="目標")
    ax.set_xlabel("室温 (°C)")
    ax.set_ylabel("エアコン設定温度 (°C)")
    ax.set_title("室温とエアコン設定温度の関係")
    ax.legend()
    ax.grid(True)

    # デモデータ
    demo = coef_outside_temp * 9.31 + coef_sleep_start * 1410 + intercept
    print(f"[demo]推奨エアコン設定温度 (°C) = {demo:.1f}")
    
    html = img2html(fig)
    plt.close(fig)  # メモリ解放
    return Response(html, mimetype="text/html")

def line():
  for event in body['events']:
        responses = []

        replyToken = event['replyToken']
        type = event['type']
        
        if type == 'message':
            message = event['message']
            
            if message['type'] == 'text':
                # そのままオウム返し
                responses.append(LineReplyMessage.make_text_response(message['text']))
            else:
                # テキスト以外のメッセージにはてへぺろしておく
                responses.append(LineReplyMessage.make_text_response('てへぺろ'))

        # 返信する
        LineReplyMessage.send_reply(replyToken, responses)


@app.route("/aircon", methods=["GET"])
def calculate():
    # スプシデータの読み込み
    url = "https://script.google.com/macros/s/AKfycbx9w61Lk_vBTnsGXTGXUE97Pg2Jl5kdAr1xhledu914VZpMO8LfSG5UoqNBQPZtybzTxg/exec"
    response = requests.get(url)
    # 最新データ
    now_time = response.json()['time']
    now_outside = response.json()['outside']
    # 分計算
    now_minute = int(now_time.split(":")[0]) * 60 + int(now_time.split(":")[1])

    sheet_data = response.json()['data']
    columns = sheet_data[0]  # カラム名
    data_values = sheet_data[1:]
    # DataFrame に変換
    data = pd.DataFrame(data_values, columns=columns)

    # 睡眠開始時刻を分に変換
    data["sleep_start_minutes"] = data["time"].apply(
        lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])
    )

    # 室温を目標範囲（22~24℃）に正規化
    target_temp = 23
    data["temp_deviation"] = data["room_temp"] - target_temp

    # 特徴量と目的変数
    X = data[["outside_temp", "sleep_start_minutes"]].values  # 特徴量: 外気温と睡眠開始時刻
    y = data["ac_setting_temp"].values  # 目的変数: エアコン設定温度

    # データを訓練セットとテストセットに分割
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 線形回帰モデルの訓練
    model = LinearRegression()
    model.fit(X_train, y_train)

    # 回帰係数と切片を取得
    coef_outside_temp, coef_sleep_start = model.coef_
    intercept = model.intercept_

    # 回帰式を表示
    print(f"エアコン設定温度 (°C) = {coef_outside_temp:.2f} * 外気温 (°C) + {coef_sleep_start:.2f} * 睡眠開始時刻 (分) + {intercept:.2f}")

    # 室温が目標範囲（22～24℃）に収まるかチェック
    def calculate_optimal_ac_temp(outside_temp, sleep_start_minutes):
        # エアコン設定温度を計算
        ac_temp = coef_outside_temp * outside_temp + coef_sleep_start * sleep_start_minutes + intercept
        return round(ac_temp, 2)

    # テストデータで予測
    predicted_ac_temp = model.predict(X_test)
    mse = mean_squared_error(y_test, predicted_ac_temp)
    print(f"平均二乗誤差 (MSE): {mse:.2f}")

    # 最適なエアコン設定温度を計算
    for i in range(5):  # テスト用: 5つのデータを例示
        outside_temp = X_test[i, 0]
        sleep_start_minutes = X_test[i, 1]
        ac_temp = calculate_optimal_ac_temp(outside_temp, sleep_start_minutes)
        print(f"外気温: {outside_temp}℃, 睡眠開始: {sleep_start_minutes}分 → エアコン設定温度: {ac_temp}℃")


    # デモデータ
    demo = coef_outside_temp * 9.31 + coef_sleep_start * 1410 + intercept
    print(f"[demo]推奨エアコン設定温度 (°C) = {demo:.1f}")

    result = coef_outside_temp * float(now_outside) + coef_sleep_start * now_minute + intercept
    print(f"推奨エアコン設定温度 (°C) = {coef_outside_temp:.2f} * 外気温 {now_outside:.2f}(°C) + {coef_sleep_start:.2f} * 睡眠開始時刻 {now_minute:.2f}(分) + {intercept:.2f}")
    print(f"推奨エアコン設定温度 (°C) = {result:.1f}")

    res = f"{result:.1f}"
    return jsonify({
        "message": "successfully get aircon setting temprature",
        "response": res
    })

if __name__ == "__main__":
    app.run(debug=True)

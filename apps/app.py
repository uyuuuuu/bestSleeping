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

GAS_URL = os.getenv("GAS_URL")

###########################
# ライン
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


def send_line(message):
    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {os.getenv("CHANNEL_ACCESS_TOKEN")}'  # チャネルアクセストークンを設定
    }
    body = {
        "to": os.getenv("USER_ID"),
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    response = requests.post(url, headers=headers, json=body)
    print(response.text)
    if response.status_code == 200:
        return jsonify({"status": "success", "message": "Message sended successfully!"}), 200
    else:
        return jsonify({"status": "error", "message": response.text}), response.status_code


def send_reply(reply_token, message):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {os.getenv("CHANNEL_ACCESS_TOKEN")}'  # チャネルアクセストークンを設定
    }
    body = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    response = requests.post(url, headers=headers, json=body)
    if response.status_code == 200:
        return jsonify({"status": "success", "message": "Message replied successfully!"}), 200
    else:
        return jsonify({"status": "error", "message": response.text}), response.status_code

###########################


@app.route("/")
def index():
    return "Welcome to BestSleeping App!"


@app.route("/weather", methods=["GET"])
def weather():
    BASE_URL = "http://api.openweathermap.org/data/2.5/forecast?"
    api_key = os.getenv("OPEN_WEATHER_API")
    url = BASE_URL + "id={cityID}&units=metric&APPID={key}".format(cityID="1857140", key=api_key)

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
    print(json)  # [debug]
    received_message = json['events'][0]['message']['text']
    isSuccess = False
    try:
        if json['events'][0]['type'] != "message":
            return "その他のイベント"
        elif json['events'][0]['message']['type'] != "text":
            raise ValueError()
        setting = float(received_message)
        print(setting)
        # POSTリクエストを送る
        body = {
            "set": setting  # setting変数を送る
        }
        response = requests.post(GAS_URL, json=body)
        print(response.status_code)
        if response.status_code != 200:
            raise ValueError()

        reply = f'本日の設定温度を{received_message}度として記録しました！'
        isSuccess = True
    except ValueError:
        print("error!!!!!")
        reply = f'数値を入力してください！'

    reply_token = json['events'][0]['replyToken']
    # line送信
    res = send_reply(reply_token, reply)
    print(reply)
    if isSuccess and res[1] == 200:
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
    file_path = "./data/sleepingData.csv"
    data = pd.read_csv(file_path)
    data.columns = ["date", "time", "outside_temp", "room_temp", "ac_setting_temp"]

    data["sleep_start_minutes"] = data["time"].apply(
        lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])
    )

    X = data[["outside_temp", "room_temp", "sleep_start_minutes"]].values
    y = data["ac_setting_temp"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = LinearRegression()
    model.fit(X_train, y_train)

    coef_outside_temp, coef_room_temp, coef_sleep_start = model.coef_
    intercept = model.intercept_

    predicted_ac_temp = model.predict(X_test)
    mse = mean_squared_error(y_test, predicted_ac_temp)
    print(f"平均二乗誤差 (MSE): {mse:.2f}")

    # 外気温レンジ全体で「目標室温23℃を達成するためのAC設定温度」を計算
    target_room_temp = 23.0
    median_sleep_start = data["sleep_start_minutes"].median()
    outside_range = np.linspace(data["outside_temp"].min(), data["outside_temp"].max(), 100)
    predicted_line = (
        coef_outside_temp * outside_range
        + coef_room_temp * target_room_temp
        + coef_sleep_start * median_sleep_start
        + intercept
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(data["outside_temp"], data["ac_setting_temp"], color="blue", alpha=0.6, label="実績データ")
    ax.plot(outside_range, predicted_line, color="red", linewidth=2, label=f"推奨AC設定（目標室温 {target_room_temp}℃）")
    ax.set_xlabel("外気温 (°C)")
    ax.set_ylabel("エアコン設定温度 (°C)")
    ax.set_title("外気温と最適エアコン設定温度の関係\n（部屋の特性から導出）")
    ax.legend()
    ax.grid(True)

    html = img2html(fig)
    plt.close(fig)
    return Response(html, mimetype="text/html")


@app.route("/aircon", methods=["GET"])
def calculate():
    # スプシデータの読み込み
    response = requests.get(GAS_URL)
    # 最新データ
    now_time = response.json()['time']
    now_outside = float(response.json()['outside'])
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

    # 特徴量と目的変数
    X = data[["outside_temp", "room_temp", "sleep_start_minutes"]].astype(float).values
    y = data["ac_setting_temp"].astype(float).values
    # データを訓練セットとテストセットに分割
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    # 線形回帰モデルの訓練
    model = LinearRegression()
    model.fit(X_train, y_train)
    # 回帰係数と切片を取得
    coef_outside_temp, coef_room_temp, coef_sleep_start = model.coef_
    intercept = model.intercept_
    print(f"エアコン設定温度 (°C) = {coef_outside_temp:.2f} * 外気温 (°C) + {coef_room_temp:.2f} * 室温 (°C) + {coef_sleep_start:.2f} * 睡眠開始時刻 (分) + {intercept:.2f}")

    predicted_ac_temp = model.predict(X_test)
    mse = mean_squared_error(y_test, predicted_ac_temp)
    print(f"平均二乗誤差 (MSE): {mse:.2f}")

    # 目標室温23℃を達成するためのAC設定温度を計算
    target_room_temp = 23.0
    result = (
        coef_outside_temp * now_outside
        + coef_room_temp * target_room_temp
        + coef_sleep_start * now_minute
        + intercept
    )
    print(f"推奨エアコン設定温度 (°C) = {coef_outside_temp:.2f} * 外気温 {now_outside:.2f}(°C) + {coef_room_temp:.2f} * 目標室温 {target_room_temp}(°C) + {coef_sleep_start:.2f} * 睡眠開始時刻 {now_minute}(分) + {intercept:.2f}")
    print(f"推奨エアコン設定温度 (°C) = {result:.1f}")

    line_res = send_line(f'本日の推奨設定温度は{result:.1f}度です！')
    res = f"{result:.1f}"
    if line_res[1] == 200:
        return jsonify({
            "message": "successfully get aircon setting temprature",
            "response": res
        })
    else:
        return jsonify({
            "message": "failed get aircon setting temprature in line",
            "response": res
        })


if __name__ == "__main__":
    app.run(debug=True)

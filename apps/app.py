import json
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

app = Flask(__name__)

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


@app.route("/aircon")
def aircon():
    return "12/18の設定温度は20度です"

if __name__ == "__main__":
    app.run(debug=True)

from flask import Flask, request
import requests
import os

app = Flask(__name__)

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

@app.route("/")
def home():
    return "OK"

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()

    print("BODY =", body)

    for event in body.get("events", []):
        reply_token = event.get("replyToken")

        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": "收到訊息了"
                }
            ]
        }

        r = requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=data
        )

        print("LINE API:", r.status_code, r.text)

    return "OK", 200

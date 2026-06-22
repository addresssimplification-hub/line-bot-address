from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


def clean(addr):
    for city in ["台北市", "新北市", "桃園市"]:
        if addr.startswith(city):
            return addr.replace(city, "", 1)
    return addr


def parse(text):
    pickup = ""
    dropoff = ""
    pax = 1
    remark = ""

    for line in text.split("\n"):
        if "上車地址" in line:
            pickup = line.split("：")[1].strip()
        if "下車地址" in line:
            dropoff = line.split("：")[1].strip()
        if "乘坐人數" in line:
            try:
                pax = int(line.split("：")[1].strip())
            except:
                pax = 1
        if "其他備註" in line:
            remark = line.split("：")[1].strip()

    fee = 0
    if pax > 4:
        fee = (pax - 4) * 100

    result = f"⬆️{clean(pickup)}\n下車地址：{clean(dropoff)}\n({pax})"
    if fee > 0:
        result += f"➕{fee}"
    if remark:
        result += f"✅{remark}"

    return result


@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data(as_text=True)
    events = handler.parse(body, request.headers.get('X-Line-Signature'))

    for event in events:
        if isinstance(event, MessageEvent):
            msg = parse(event.message.text)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=msg)
            )

    return "OK"


if __name__ == "__main__":
    app.run()

from flask import Flask, request, abort
import os

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextSendMessage

app = Flask(__name__)

# ===== LINE KEY =====
TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(TOKEN)
handler = WebhookHandler(SECRET)


# ===== 地址簡化 =====
def clean(addr):
    if not addr:
        return ""
    for city in ["台北市", "新北市", "桃園市"]:
        if addr.startswith(city):
            return addr.replace(city, "", 1)
    return addr


# ===== 解析 =====
def parse(text):
    pickup = ""
    dropoff = ""
    pax = 1
    remark = ""

    for line in text.split("\n"):
        if "上車地址" in line:
            pickup = line.split("：")[-1].strip()

        elif "下車地址" in line:
            dropoff = line.split("：")[-1].strip()

        elif "乘坐人數" in line:
            try:
                pax = int(line.split("：")[-1].strip())
            except:
                pax = 1

        elif "其他備註" in line:
            remark = line.split("：")[-1].strip()

    fee = (pax - 4) * 100 if pax > 4 else 0

    result = f"⬆️{clean(pickup)}\n下車地址：{clean(dropoff)}\n({pax})"

    if fee > 0:
        result += f"➕{fee}"

    if remark:
        result += f"✅{remark}"

    return result


# ===== webhook =====
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        events = handler.handle(body, signature)
    except InvalidSignatureError:
        return "OK", 200

    if not events:
        return "OK", 200

    for event in events:
        if isinstance(event, MessageEvent):
            msg = parse(event.message.text)

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=msg)
            )

    return "OK", 200


if __name__ == "__main__":
    app.run()

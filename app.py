from flask import Flask, request, abort
import os

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ===== LINE 金鑰（Render 環境變數）=====
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


# ===== 地址簡化 =====
def clean(addr):
    for city in ["台北市", "新北市", "桃園市"]:
        if addr.startswith(city):
            return addr.replace(city, "", 1)
    return addr


# ===== 解析內容 =====
def parse(text):
    pickup = ""
    dropoff = ""
    pax = 1
    remark = ""

    for line in text.split("\n"):
        if "上車地址" in line:
            try:
                pickup = line.split("：")[1].strip()
            except:
                pass

        if "下車地址" in line:
            try:
                dropoff = line.split("：")[1].strip()
            except:
                pass

        if "乘坐人數" in line:
            try:
                pax = int(line.split("：")[1].strip())
            except:
                pax = 1

        if "其他備註" in line:
            try:
                remark = line.split("：")[1].strip()
            except:
                pass

    # ===== 加價規則 =====
    fee = (pax - 4) * 100 if pax > 4 else 0

    # ===== 組輸出 =====
    result = f"⬆️{clean(pickup)}\n下車地址：{clean(dropoff)}\n({pax})"

    if fee > 0:
        result += f"➕{fee}"

    if remark:
        result += f"✅{remark}"

    return result


# ===== LINE webhook =====
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        events = handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

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

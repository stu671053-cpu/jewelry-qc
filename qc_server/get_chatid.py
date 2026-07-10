#!/usr/bin/env python3
"""
获取企业微信智能机器人所在群的 chat_id

用法:
    python get_chatid.py

原理:
    启动 WebSocket 长连接，在群里 @机器人 发一条消息，
    脚本会从回调中提取 chatid 并保存到 config.json
"""

import json
import time
from pathlib import Path
from wecom_ws import WeComWebSocket

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

# 加载配置
config = json.loads(CONFIG_PATH.read_text("utf-8"))
wc = config.get("notification", {}).get("wecom_bot", {})
bot_id = wc.get("bot_id", "")
secret = wc.get("secret", "")

if not bot_id or not secret:
    print("❌ 请先配置 bot_id 和 secret")
    exit(1)

# 重写 _on_message 来捕获 chat_id
class ChatIdGrabber(WeComWebSocket):
    def __init__(self, bot_id, secret):
        super().__init__(bot_id, secret, "")

    def _on_message(self, ws, message):
        data = json.loads(message)
        cmd = data.get("cmd", "")
        errcode = data.get("errcode", -1)

        if cmd == "aibot_subscribe":
            if errcode == 0:
                print("✅ 鉴权成功！请在群里 @机器人 发一条消息...")
                self.connected = True
            else:
                print(f"❌ 鉴权失败: {data}")
                exit(1)
            return

        # 收到消息事件
        if cmd == "aibot_message":
            body = data.get("body", {})
            chatid = body.get("chatid", "")
            chat_type = body.get("chat_type", "")
            msg_content = body.get("text", {}).get("content", "")

            if chatid:
                print(f"\n🎯 捕获到 chat_id!")
                print(f"   chat_id: {chatid}")
                print(f"   chat_type: {'群聊' if chat_type == 2 else '单聊'}")
                print(f"   消息内容: {msg_content}")

                # 保存到 config
                config["notification"]["wecom_bot"]["chat_id"] = chatid
                CONFIG_PATH.write_text(
                    json.dumps(config, ensure_ascii=False, indent=2),
                    "utf-8",
                )
                print(f"\n✅ chat_id 已保存到 config.json")
                print("现在可以启动 qc_server 了: python app.py")
                exit(0)


grabber = ChatIdGrabber(bot_id, secret)
grabber.start()

print("=" * 50)
print("等待 WebSocket 连接...")
print("连接成功后，请在群里 @机器人 发一条消息")
print("脚本将自动捕获 chat_id 并保存")
print("=" * 50)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n已取消")

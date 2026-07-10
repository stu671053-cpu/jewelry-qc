"""
企业微信智能机器人 WebSocket 长连接通知模块

基于官方文档: https://developer.work.weixin.qq.com/document/path/101463
- 建立 wss 长连接
- aibot_subscribe 鉴权 (Bot ID + Secret)
- aibot_send_msg 主动推送消息到指定 chatid

用法:
    ws = WeComWebSocket(bot_id, secret, chat_id)
    ws.start()                    # 后台启动连接
    ws.send_markdown("**告警**")  # 发送消息
"""

import json
import threading
import time
import uuid
import ssl

try:
    from websocket import (
        WebSocketApp,
        enableTrace,
        WebSocketConnectionClosedException,
    )
except ImportError:
    raise ImportError("请安装 websocket-client: pip install websocket-client")


class WeComWebSocket:
    """企业微信智能机器人 WebSocket 通知器"""

    WSS_URL = "wss://openws.work.weixin.qq.com"

    def __init__(self, bot_id: str, secret: str, chat_id: str):
        self.bot_id = bot_id
        self.secret = secret
        self.chat_id = chat_id
        self.ws = None
        self.thread = None
        self.connected = False
        self._pending_messages = []  # 未连接时缓存的消息
        self._lock = threading.Lock()

    def start(self):
        """启动 WebSocket 连接（后台线程）"""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        """WebSocket 主循环"""
        while True:
            try:
                self.ws = WebSocketApp(
                    self.WSS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(
                    sslopt={"cert_reqs": ssl.CERT_NONE},
                    ping_interval=30,
                    ping_timeout=10,
                )
            except Exception as e:
                print(f"[企微WS] 连接异常: {e}")

            print("[企微WS] 5秒后重连...")
            time.sleep(5)

    def _on_open(self, ws):
        """连接建立后发送订阅"""
        print("[企微WS] 连接已建立，发送鉴权...")
        sub = {
            "cmd": "aibot_subscribe",
            "headers": {"req_id": str(uuid.uuid4())},
            "body": {
                "bot_id": self.bot_id,
                "secret": self.secret,
            },
        }
        ws.send(json.dumps(sub, ensure_ascii=False))

    def _on_message(self, ws, message):
        """接收消息"""
        data = json.loads(message)
        cmd = data.get("cmd", "")
        errcode = data.get("errcode", -1)

        if cmd == "aibot_subscribe":
            if errcode == 0:
                print("[企微WS] 鉴权成功，连接就绪")
                self.connected = True
                self._flush_pending()
            else:
                print(f"[企微WS] 鉴权失败: {data}")
                self.connected = False
        elif cmd == "aibot_send_msg":
            if errcode == 0:
                print("[企微WS] 消息发送成功")
            else:
                print(f"[企微WS] 消息发送失败: {data}")
        else:
            # 其他事件（如用户发消息），忽略
            pass

    def _on_error(self, ws, error):
        print(f"[企微WS] 错误: {error}")
        self.connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        print(f"[企微WS] 连接关闭: {close_status_code} {close_msg}")
        self.connected = False

    def _flush_pending(self):
        """发送缓存的消息"""
        with self._lock:
            pending = list(self._pending_messages)
            self._pending_messages = []
        for msg in pending:
            self._do_send(msg)

    def _do_send(self, payload: dict):
        """底层发送"""
        if self.ws and self.connected:
            try:
                self.ws.send(json.dumps(payload, ensure_ascii=False))
                return True
            except Exception as e:
                print(f"[企微WS] 发送异常: {e}")
                self.connected = False
        return False

    def send_markdown(self, content: str) -> bool:
        """发送 Markdown 消息"""
        if not self.chat_id:
            print("[企微WS] chat_id 为空，无法发送")
            return False

        payload = {
            "cmd": "aibot_send_msg",
            "headers": {"req_id": str(uuid.uuid4())},
            "body": {
                "chatid": self.chat_id,
                "chat_type": 2,
                "msgtype": "markdown",
                "markdown": {"content": content},
            },
        }

        if self.connected:
            return self._do_send(payload)
        else:
            with self._lock:
                self._pending_messages.append(payload)
            print("[企微WS] 连接未就绪，消息已缓存，将在连接建立后发送")
            return False

    def send_text(self, content: str) -> bool:
        """发送文本消息（通过 markdown 格式）"""
        return self.send_markdown(content)

"""
通知模块
- 企业微信智能机器人 WebSocket 长连接 (Bot ID + Secret)
- 企业微信群机器人 Webhook

用法:
    # 方式1: 智能机器人长连接 (推荐用于频繁通知)
    n = Notifier(config)
    n.start()  # 启动长连接
    n.send_anomaly_alert("消息内容")

    # 方式2: 群机器人 Webhook (简单场景)
    配置 wechat_work.webhook_url 即可
"""

import json
import requests

from wecom_ws import WeComWebSocket


class Notifier:
    """消息通知器"""

    def __init__(self, config: dict):
        self.enabled = config.get("notification", {}).get("enabled", False)
        self.notif_config = config.get("notification", {})
        self._ws = None

    def start(self):
        """启动企业微信长连接（如果配置了智能机器人）"""
        if not self.enabled:
            return

        ntype = self.notif_config.get("type", "")
        if ntype != "wecom_bot":
            return

        wc = self.notif_config.get("wecom_bot", {})
        bot_id = wc.get("bot_id", "")
        secret = wc.get("secret", "")
        chat_id = wc.get("chat_id", "")

        if bot_id and secret and chat_id:
            self._ws = WeComWebSocket(bot_id, secret, chat_id)
            self._ws.start()
            print("[通知] 企业微信长连接已启动")
        else:
            print("[通知] 配置不完整，长连接未启动")
            print("[通知] 需要: bot_id, secret, chat_id")

    def send_anomaly_alert(self, message: str) -> bool:
        """发送异常告警"""
        if not self.enabled:
            print("[通知] 通知未启用，跳过")
            return False

        ntype = self.notif_config.get("type", "wecom_bot")
        if ntype == "wecom_bot":
            return self._send_wecom_bot(message)
        elif ntype == "wechat_work":
            return self._send_wechat_webhook(message)
        else:
            print(f"[通知] 不支持的通知类型: {ntype}")
            return False

    def _send_wecom_bot(self, message: str) -> bool:
        """通过智能机器人长连接发送消息"""
        if not self._ws:
            print("[通知] 长连接未启动，跳过")
            return False

        # 企业微信 markdown 不支持 ## 和 > 语法，转为纯文本格式
        plain = message.replace("## ", "").replace("**", "").replace("> ", "  ")
        return self._ws.send_markdown(plain)

    def _send_wechat_webhook(self, message: str) -> bool:
        """通过群机器人 Webhook 发送消息"""
        webhook_url = (
            self.notif_config
            .get("wechat_work", {})
            .get("webhook_url", "")
        )

        if "YOUR_KEY_HERE" in webhook_url:
            print("[通知] 企业微信 Webhook 未配置，跳过")
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": message},
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            result = resp.json()
            if result.get("errcode") == 0:
                print("[通知] Webhook 发送成功")
                return True
            else:
                print(f"[通知] Webhook 发送失败: {result}")
                return False
        except Exception as e:
            print(f"[通知] 发送异常: {e}")
            return False

    def send_batch_alert(self, anomaly_list: list) -> bool:
        """批量发送异常告警"""
        if not anomaly_list:
            return True

        lines = [f"⚠️ 质检异常批量提醒"]
        lines.append(f"共检测到 {len(anomaly_list)} 条异常")
        lines.append("")

        for i, item in enumerate(anomaly_list[:15]):
            order_code = item.get("order_code", "")
            anomalies = item.get("anomalies", [])
            order = item.get("order", {})
            lines.append(f"{i + 1}. 订单 {order_code}")
            lines.append(f"   商品: {order.get('商品名称', '')}")
            for a in anomalies:
                lines.append(f"   - {a['rule_name']}: {a['value']}")
            lines.append("")

        if len(anomaly_list) > 15:
            lines.append(f"... 还有 {len(anomaly_list) - 15} 条异常")

        return self.send_anomaly_alert("\n".join(lines))

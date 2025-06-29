# arb_trading/utils/notifications.py
import asyncio
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict
import json


class NotificationManager:
    """알림 관리 클래스"""

    def __init__(self, slack_webhook: str = "", telegram_token: str = "",
                 telegram_chat_id: str = "", email_config: Optional[Dict] = None):
        self.slack_webhook = slack_webhook
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.email_config = email_config or {}

    async def send_slack_notification(self, message: str, level: str = "INFO"):
        """슬랙 알림 발송"""
        if not self.slack_webhook:
            return

        try:
            color_map = {
                "INFO": "#36a64f",  # 녹색
                "WARNING": "#ff9500",  # 주황색
                "ERROR": "#ff0000",  # 빨간색
                "CRITICAL": "#8b0000"  # 진한 빨간색
            }

            payload = {
                "attachments": [{
                    "color": color_map.get(level, "#36a64f"),
                    "fields": [{
                        "title": f"차익거래 시스템 - {level}",
                        "value": message,
                        "short": False
                    }],
                    "ts": asyncio.get_event_loop().time()
                }]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.slack_webhook, json=payload) as response:
                    if response.status != 200:
                        print(f"슬랙 알림 발송 실패: {response.status}")

        except Exception as e:
            print(f"슬랙 알림 발송 중 오류: {e}")

    async def send_telegram_notification(self, message: str):
        """텔레그램 알림 발송"""
        if not self.telegram_token or not self.telegram_chat_id:
            return

        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": f"🤖 차익거래 시스템\n\n{message}",
                "parse_mode": "Markdown"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        print(f"텔레그램 알림 발송 실패: {response.status}")

        except Exception as e:
            print(f"텔레그램 알림 발송 중 오류: {e}")

    def send_email_notification(self, subject: str, message: str):
        """이메일 알림 발송 (동기)"""
        if not self.email_config.get('smtp_server'):
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['user']
            msg['To'] = self.email_config.get('to_email', self.email_config['user'])
            msg['Subject'] = f"차익거래 시스템 - {subject}"

            body = f"""
            차익거래 시스템에서 알림이 발생했습니다.

            {message}

            시간: {asyncio.get_event_loop().time()}
            """

            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            server = smtplib.SMTP(self.email_config['smtp_server'],
                                  self.email_config.get('smtp_port', 587))
            server.starttls()
            server.login(self.email_config['user'], self.email_config['password'])

            text = msg.as_string()
            server.sendmail(self.email_config['user'],
                            self.email_config.get('to_email', self.email_config['user']),
                            text)
            server.quit()

        except Exception as e:
            print(f"이메일 알림 발송 중 오류: {e}")

    async def notify_all(self, message: str, level: str = "INFO", include_email: bool = False):
        """모든 채널로 알림 발송"""
        tasks = []

        if self.slack_webhook:
            tasks.append(self.send_slack_notification(message, level))

        if self.telegram_token and self.telegram_chat_id:
            tasks.append(self.send_telegram_notification(message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if include_email and self.email_config.get('smtp_server'):
            # 이메일은 별도 스레드에서 실행
            import threading
            threading.Thread(
                target=self.send_email_notification,
                args=(level, message),
                daemon=True
            ).start()

"""
Session and authentication module for Chaoxing MCP.
Handles login, session cookie management, and HTTP requests.
"""

import binascii
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pyDes import des, PAD_PKCS5

# ── constants ──────────────────────────────────────────────────────────
DES_KEY = "u2oh6Vu^"
LOGIN_URL = "https://passport2.chaoxing.com/fanyalogin"
BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; SM-G975F) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


@dataclass
class Session:
    """Maintains a logged-in Chaoxing session."""

    client: httpx.Client = field(default_factory=lambda: httpx.Client(
        headers=BASE_HEADERS,
        follow_redirects=True,
        timeout=30,
        verify=False,
    ))
    phone: str = ""
    logged_in: bool = False

    def login(self, phone: str, password: str) -> dict[str, Any]:
        """DES-encrypt password and POST to fanyalogin.  Returns login result."""
        self.phone = phone

        # DES encrypt
        des_obj = des(DES_KEY, DES_KEY, pad=None, padmode=PAD_PKCS5)
        encrypted = des_obj.encrypt(password, padmode=PAD_PKCS5)
        pwd_hex = binascii.b2a_hex(encrypted).decode()

        payload = {
            "fid": "-1",
            "uname": phone,
            "password": pwd_hex,
            "refer": "https://i.chaoxing.com",
            "t": "true",
            "forbidotherlogin": "0",
            "validate": "",
            "doubleFactorLogin": "0",
            "independentId": "0",
        }

        # Get initial cookies first
        self.client.get("https://passport2.chaoxing.com/login?newversion=true", follow_redirects=True)

        resp = self.client.post(LOGIN_URL, data=payload)

        result = {"success": False, "message": "未知错误"}

        if resp.status_code == 200:
            # Try to parse JSON
            try:
                data = resp.json()
                if data.get("status"):
                    self.logged_in = True
                    result = {"success": True, "message": "登录成功", "data": data}
                else:
                    result = {"success": False, "message": data.get("msg2", "登录失败")}
            except json.JSONDecodeError:
                text = resp.text
                if "登录成功" in text or "/space/index" in text:
                    self.logged_in = True
                    result = {"success": True, "message": "登录成功"}
                elif "密码错误" in text:
                    result = {"success": False, "message": "密码错误"}
                elif "验证码" in text:
                    result = {"success": False, "message": "需要验证码，请稍后重试"}
                elif "账号不存在" in text:
                    result = {"success": False, "message": "账号不存在"}

        return result

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.client.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.client.post(url, **kwargs)

    def close(self):
        self.client.close()

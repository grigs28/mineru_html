# Copyright (c) Opendatalab. All rights reserved.

"""yz-login 统一登录接入（方式一：ticket 回调）

只保护 UI 页面（GET /），所有 API 端点放行（不影响外部调用方）。
会话为 HMAC 签名 Cookie（标准库实现，无新增第三方依赖）。
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

from loguru import logger

# yz-login 平台地址与本应用在其管理后台注册的 ID
YZ_LOGIN_URL = os.environ.get("YZ_LOGIN_URL", "http://192.168.0.8")
YZ_APP_ID = os.environ.get("YZ_APP_ID", "15")

# 会话签名密钥：生产用 compose 环境变量固定；未设置时随机生成（重启后会话失效）
SESSION_SECRET = os.environ.get("SESSION_SECRET") or base64.urlsafe_b64encode(os.urandom(32)).decode()
_SESSION_RANDOM = "SESSION_SECRET" not in os.environ

SESSION_COOKIE = "mineru_session"
SESSION_TTL = 12 * 3600  # 12 小时


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_session_cookie(user: dict) -> str:
    """签发签名会话 Cookie：payload(b64).signature"""
    payload = _b64e(json.dumps({
        "u": user.get("username"),
        "d": user.get("display_name"),
        "admin": user.get("is_admin", 0),
        "exp": int(time.time()) + SESSION_TTL,
    }, ensure_ascii=False).encode())
    sig = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session_cookie(value: str) -> Optional[dict]:
    """校验会话 Cookie，有效则返回用户信息，否则 None"""
    try:
        payload, sig = value.split(".", 1)
        expect = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        data = json.loads(_b64d(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


def login_redirect_url() -> str:
    """yz-login 登录页地址（按应用 ID 引用，URL 变更自动跟随）"""
    return f"{YZ_LOGIN_URL}/login?from=id:{YZ_APP_ID}"


def logout_redirect_url() -> str:
    return f"{YZ_LOGIN_URL}/logout?from=id:{YZ_APP_ID}"


def _verify_ticket_sync(ticket: str) -> Optional[dict]:
    """同步调 yz-login 验票（ticket 一次性，5 分钟有效）"""
    url = f"{YZ_LOGIN_URL}/api/ticket/verify?ticket={urllib.parse.quote(ticket)}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                return data
            logger.warning(f"ticket 验票被拒绝: {data.get('msg')}")
    except Exception as e:
        logger.error(f"ticket 验票请求失败: {e}")
    return None


async def verify_ticket(ticket: str) -> Optional[dict]:
    """异步包装，避免阻塞事件循环"""
    return await asyncio.to_thread(_verify_ticket_sync, ticket)

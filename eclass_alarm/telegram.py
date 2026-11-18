"""텔레그램 Bot API 최소 래퍼."""
from __future__ import annotations

import json

import requests


class Telegram:
    def __init__(self, token: str, chat_id: str, timeout: int = 20):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id)
        self.timeout = timeout

    def _call(self, method: str, **params):
        r = requests.post(f"{self.base}/{method}", json=params, timeout=self.timeout + 30)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram {method} 실패: {data.get('description')}")
        return data["result"]

    def send(self, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> int:
        params = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if buttons:
            params["reply_markup"] = {
                "inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]
            }
        return self._call("sendMessage", **params)["message_id"]

    def delete(self, message_id: int) -> None:
        try:
            self._call("deleteMessage", chat_id=self.chat_id, message_id=message_id)
        except Exception:
            pass

    def edit(self, message_id: int, text: str) -> None:
        try:
            self._call("editMessageText", chat_id=self.chat_id, message_id=message_id,
                       text=text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)
        except Exception:
            pass

    def updates(self, offset: int | None, wait: int = 0) -> list[dict]:
        params = {"timeout": wait, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", **params)

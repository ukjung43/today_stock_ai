"""Minimal client for the official Threads API (graph.threads.net)."""

import time

import requests

BASE = "https://graph.threads.net/v1.0"


class ThreadsError(RuntimeError):
    pass


class ThreadsClient:
    def __init__(self, access_token: str):
        if not access_token:
            raise ThreadsError("THREADS_ACCESS_TOKEN 이 비어 있어요")
        self.token = access_token

    def _call(self, method: str, path: str, **params) -> dict:
        resp = requests.request(method, f"{BASE}/{path}", params=params | {"access_token": self.token}, timeout=60)
        if not resp.ok:
            # The token is a query parameter, so never echo the request URL.
            raise ThreadsError(f"{method} {path} 실패 ({resp.status_code}): {resp.text[:500]}")
        return resp.json()

    def me(self) -> dict:
        return self._call("GET", "me", fields="id,username")

    def _wait_until_ready(self, container_id: str, timeout_s: int = 180) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            info = self._call("GET", container_id, fields="status,error_message")
            if info.get("status") == "FINISHED":
                return
            if info.get("status") in ("ERROR", "EXPIRED"):
                raise ThreadsError(f"컨테이너 {container_id} 처리 실패: {info}")
            time.sleep(5)
        raise ThreadsError(f"컨테이너 {container_id} 가 {timeout_s}초 안에 준비되지 않았어요")

    def _publish(self, user_id: str, container_id: str, min_wait_s: int) -> str:
        time.sleep(min_wait_s)  # Meta recommends ~30s between creating and publishing media containers
        self._wait_until_ready(container_id)
        return self._call("POST", f"{user_id}/threads_publish", creation_id=container_id)["id"]

    def post_image(self, user_id: str, text: str, image_url: str) -> str:
        container = self._call("POST", f"{user_id}/threads", media_type="IMAGE", image_url=image_url, text=text)
        return self._publish(user_id, container["id"], min_wait_s=30)

    def reply_text(self, user_id: str, reply_to_id: str, text: str) -> str:
        container = self._call("POST", f"{user_id}/threads", media_type="TEXT", text=text, reply_to_id=reply_to_id)
        return self._publish(user_id, container["id"], min_wait_s=5)

    def permalink(self, media_id: str) -> str:
        return self._call("GET", media_id, fields="permalink").get("permalink", "")


def exchange_for_long_lived_token(short_token: str, app_secret: str) -> dict:
    """Short-lived (1 hour) token -> long-lived (60 days). Returns {'access_token', 'token_type', 'expires_in'}."""
    resp = requests.get(
        "https://graph.threads.net/access_token",
        params={"grant_type": "th_exchange_token", "client_secret": app_secret, "access_token": short_token},
        timeout=30,
    )
    if not resp.ok:
        raise ThreadsError(f"장기 토큰 교환 실패 ({resp.status_code}): {resp.text[:500]}")
    return resp.json()


def refresh_long_lived_token(access_token: str) -> dict:
    """Returns {'access_token', 'token_type', 'expires_in'}; the token must be at least 24h old."""
    resp = requests.get(
        "https://graph.threads.net/refresh_access_token",
        params={"grant_type": "th_refresh_token", "access_token": access_token},
        timeout=30,
    )
    if not resp.ok:
        raise ThreadsError(f"토큰 갱신 실패 ({resp.status_code}): {resp.text[:500]}")
    return resp.json()

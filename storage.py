"""저장소 계층: Supabase(설정 시) 또는 로컬 SQLite.

두 저장소 모두 같은 형태의 dict를 돌려준다.
  id, day, title, learned, executed, result, status,
  tags(쉼표 구분 문자열), minutes, created_at, updated_at(표시용 문자열)
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
FIELDS = ("day", "title", "learned", "executed", "result", "status", "tags", "minutes")


class StoreError(Exception):
    """저장소(특히 Supabase) 통신 실패."""


# ---------------------------------------------------------------- SQLite
class SQLiteStore:
    name = "SQLite"

    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.executescript((BASE_DIR / "schema.sql").read_text())

    @contextmanager
    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def list(self, q: str = "", tag: str = "", status: str = "") -> list[dict]:
        sql, args = "SELECT * FROM entries WHERE 1=1", []
        if q:
            sql += " AND (title LIKE ? OR learned LIKE ? OR executed LIKE ? OR result LIKE ?)"
            args += [f"%{q}%"] * 4
        if tag:
            sql += " AND (',' || tags || ',') LIKE ?"
            args.append(f"%,{tag},%")
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY day DESC, id DESC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def get(self, entry_id: int) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return dict(r) if r else None

    def create(self, data: dict) -> int:
        with self._conn() as c:
            cur = c.execute(
                f"INSERT INTO entries ({', '.join(FIELDS)}) "
                f"VALUES ({', '.join(':' + f for f in FIELDS)})", data)
            return cur.lastrowid

    def update(self, entry_id: int, data: dict) -> None:
        with self._conn() as c:
            c.execute(
                f"UPDATE entries SET {', '.join(f'{f}=:{f}' for f in FIELDS)}, "
                "updated_at=datetime('now','localtime') WHERE id=:id", {**data, "id": entry_id})

    def delete(self, entry_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM entries WHERE id = ?", (entry_id,))


# -------------------------------------------------------------- Supabase
def normalize_supabase_url(url: str) -> str:
    """대시보드 주소(supabase.com/dashboard/project/<ref>)도 API 주소로 바꿔준다."""
    url = url.strip().rstrip("/")
    m = re.search(r"supabase\.com/dashboard/project/([a-z0-9]+)", url)
    if m:
        return f"https://{m.group(1)}.supabase.co"
    if re.fullmatch(r"[a-z0-9]{20}", url):  # 프로젝트 ref만 넣은 경우
        return f"https://{url}.supabase.co"
    return url


def _pg_quote(value: str) -> str:
    """PostgREST 필터 값 따옴표 처리 (쉼표·괄호가 들어가도 안전하게)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _local_time(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


class SupabaseStore:
    name = "Supabase"
    TABLE = "entries"

    def __init__(self, url: str, key: str, session: requests.Session | None = None):
        self.base = f"{normalize_supabase_url(url)}/rest/v1/{self.TABLE}"
        self.http = session or requests.Session()
        # 새 형식 키(sb_secret_...)는 apikey 헤더로만 보낸다.
        self.http.headers.update({"apikey": key, "Content-Type": "application/json"})

    # -- 내부 도우미
    def _req(self, method: str, params: dict | None = None, json=None,
             prefer: str | None = None) -> list[dict]:
        headers = {"Prefer": prefer} if prefer else {}
        try:
            r = self.http.request(method, self.base, params=params, json=json,
                                  headers=headers, timeout=10)
        except requests.RequestException as e:
            raise StoreError(f"Supabase에 연결할 수 없습니다: {e}") from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("message") or r.text
            except ValueError:
                detail = r.text
            if r.status_code == 404 or "does not exist" in detail or "schema cache" in detail:
                detail += " — Supabase SQL Editor에서 supabase/schema.sql을 실행했는지 확인하세요."
            elif r.status_code in (401, 403):
                detail += " — .env의 SUPABASE_SECRET_KEY를 확인하세요."
            raise StoreError(f"Supabase 오류 ({r.status_code}): {detail}")
        return r.json() if r.content else []

    @staticmethod
    def _to_row(r: dict) -> dict:
        return {
            **r,
            "tags": ",".join(r.get("tags") or []),
            "created_at": _local_time(r.get("created_at")),
            "updated_at": _local_time(r.get("updated_at")),
        }

    @staticmethod
    def _to_payload(data: dict) -> dict:
        payload = {f: data[f] for f in FIELDS if f in data}
        if "tags" in payload:
            payload["tags"] = [t for t in payload["tags"].split(",") if t]
        return payload

    # -- 공개 API
    def list(self, q: str = "", tag: str = "", status: str = "") -> list[dict]:
        params = {"select": "*", "order": "day.desc,id.desc"}
        if q:
            pat = _pg_quote(f"*{q}*")
            params["or"] = "(" + ",".join(
                f"{c}.ilike.{pat}" for c in ("title", "learned", "executed", "result")) + ")"
        if tag:
            params["tags"] = "cs.{" + _pg_quote(tag) + "}"
        if status:
            params["status"] = f"eq.{status}"
        return [self._to_row(r) for r in self._req("GET", params)]

    def get(self, entry_id: int) -> dict | None:
        rows = self._req("GET", {"select": "*", "id": f"eq.{entry_id}"})
        return self._to_row(rows[0]) if rows else None

    def create(self, data: dict, extra: dict | None = None) -> int:
        rows = self._req("POST", json={**self._to_payload(data), **(extra or {})},
                         prefer="return=representation")
        return rows[0]["id"]

    def update(self, entry_id: int, data: dict) -> None:
        payload = {**self._to_payload(data),
                   "updated_at": datetime.now(timezone.utc).isoformat()}
        self._req("PATCH", {"id": f"eq.{entry_id}"}, json=payload)

    def delete(self, entry_id: int) -> None:
        self._req("DELETE", {"id": f"eq.{entry_id}"})


def make_store(config: dict):
    url, key = config.get("SUPABASE_URL"), config.get("SUPABASE_SECRET_KEY")
    if url and key:
        return SupabaseStore(url, key)
    return SQLiteStore(config["DATABASE"])

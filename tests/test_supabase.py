"""Supabase 저장소 테스트 — 실제 네트워크 대신 PostgREST를 흉내 내는 가짜 세션 사용."""
import json as jsonlib
import re
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app  # noqa: E402
from storage import StoreError, SupabaseStore, normalize_supabase_url  # noqa: E402

KEY = "sb_secret_test"


class FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self.content = b"" if body is None else jsonlib.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        return jsonlib.loads(self.content)


class FakePostgREST(requests.Session):
    """entries 테이블 하나를 메모리에 두고 PostgREST 문법 일부를 해석한다."""

    def __init__(self):
        super().__init__()
        self.rows, self.next_id, self.calls = [], 1, []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append((method, url, params, json, {**self.headers, **(headers or {})}))
        assert url == "https://abcdefghijklmnopqrst.supabase.co/rest/v1/entries"
        assert self.headers["apikey"] == KEY and "Authorization" not in self.headers
        assert timeout
        params = params or {}
        if method == "POST":
            row = {"id": self.next_id, "learned": "", "executed": "", "result": "",
                   "status": "success", "tags": [], "minutes": 0,
                   "created_at": "2026-11-05T01:02:03+00:00",
                   "updated_at": "2026-11-05T01:02:03+00:00", **json}
            assert isinstance(row["tags"], list)
            self.next_id += 1
            self.rows.append(row)
            return FakeResp(201, [row])
        rows = [r for r in self.rows if self._match(r, params)]
        if method == "GET":
            rows.sort(key=lambda r: (r["day"], r["id"]), reverse=True)
            return FakeResp(200, rows)
        if method == "PATCH":
            for r in rows:
                r.update(json)
            return FakeResp(204, None)
        if method == "DELETE":
            self.rows = [r for r in self.rows if r not in rows]
            return FakeResp(204, None)
        raise AssertionError(method)

    @staticmethod
    def _match(r, params):
        if "id" in params and r["id"] != int(params["id"].removeprefix("eq.")):
            return False
        if "status" in params and r["status"] != params["status"].removeprefix("eq."):
            return False
        if "tags" in params:
            tag = re.fullmatch(r'cs\.\{"(.*)"\}', params["tags"]).group(1)
            if tag not in r["tags"]:
                return False
        if "or" in params:
            q = re.search(r'ilike\."\*(.*?)\*"', params["or"]).group(1)
            if not any(q.lower() in str(r[c]).lower()
                       for c in ("title", "learned", "executed", "result")):
                return False
        return True


@pytest.fixture
def fake():
    return FakePostgREST()


@pytest.fixture
def client(fake):
    store = SupabaseStore("https://supabase.com/dashboard/project/abcdefghijklmnopqrst", KEY, fake)
    return create_app({"TESTING": True, "STORE": store}).test_client()


def add(client, **kw):
    data = {"day": date.today().isoformat(), "title": "RAG 실험", "learned": "청크",
            "executed": "python rag.py", "result": "recall 0.78", "status": "success",
            "tags": "rag, LLM", "minutes": "30", **kw}
    return client.post("/entries/new", data=data)


def test_url_normalize():
    ref = "abcdefghijklmnopqrst"
    want = f"https://{ref}.supabase.co"
    assert normalize_supabase_url(f"https://supabase.com/dashboard/project/{ref}") == want
    assert normalize_supabase_url(f"https://supabase.com/dashboard/project/{ref}/settings") == want
    assert normalize_supabase_url(ref) == want
    assert normalize_supabase_url(want + "/") == want


def test_crud_flow(client, fake):
    r = add(client)
    assert r.status_code == 302
    assert fake.rows[0]["tags"] == ["rag", "llm"]          # text[] 로 저장
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "RAG 실험" in page and "#llm" in page and "저장소: Supabase" in page

    client.post("/entries/1/edit", data={"day": "2026-01-02", "title": "수정됨", "status": "fail"})
    assert fake.rows[0]["title"] == "수정됨" and fake.rows[0]["tags"] == []
    assert "updated_at" in fake.calls[-1][3]

    client.post("/entries/1/delete")
    assert fake.rows == [] and client.get("/entries/1").status_code == 404


def test_filters_and_stats(client, fake):
    add(client, title="A", tags="vision", status="fail")
    add(client, title="B, (괄호)", tags="nlp")
    html = client.get("/?tag=vision").get_data(as_text=True)
    assert ">A<" in html and "괄호" not in html
    assert "<b>2</b><span>전체 기록" in html                # 통계는 전체 기준
    html = client.get("/?q=(괄호)").get_data(as_text=True)    # 쉼표·괄호 안전
    assert "괄호" in html and ">A<" not in html
    assert '"*(괄호)*"' in fake.calls[-2][2]["or"]
    html = client.get("/?status=fail").get_data(as_text=True)
    assert ">A<" in html and "괄호" not in html


def test_export(client):
    add(client)
    md = client.get("/export.md").get_data(as_text=True)
    assert "### RAG 실험" in md and "#rag #llm" in md


def test_error_page(fake):
    class Down(FakePostgREST):
        def request(self, *a, **k):
            raise requests.ConnectionError("offline")
    store = SupabaseStore("abcdefghijklmnopqrst", KEY, Down())
    c = create_app({"TESTING": True, "STORE": store}).test_client()
    r = c.get("/")
    assert r.status_code == 503 and "연결할 수 없습니다" in r.get_data(as_text=True)


def test_missing_table_hint(fake):
    class NoTable(FakePostgREST):
        def request(self, *a, **k):
            return FakeResp(404, {"message": "relation \"public.entries\" does not exist"})
    store = SupabaseStore("abcdefghijklmnopqrst", KEY, NoTable())
    with pytest.raises(StoreError, match="schema.sql"):
        store.list()

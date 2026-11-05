import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, normalize_tags  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "t.db")})
    return app.test_client()


def add(client, **kw):
    data = {"day": date.today().isoformat(), "title": "LoRA 실습", "learned": "rank 개념",
            "executed": "python train.py", "result": "loss 1.2", "status": "success",
            "tags": "LLM, #lora, llm", "minutes": "40", **kw}
    return client.post("/entries/new", data=data)


def test_create_and_detail(client):
    r = add(client)
    assert r.status_code == 302
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "LoRA 실습" in page and "python train.py" in page and "#lora" in page


def test_validation(client):
    assert add(client, title="").status_code == 400
    assert add(client, day="2026-13-01").status_code == 400
    assert add(client, minutes="abc").status_code == 400
    assert add(client, status="hack").status_code == 400


def test_edit_and_delete(client):
    loc = add(client).headers["Location"]
    eid = loc.rsplit("/", 1)[1]
    client.post(f"/entries/{eid}/edit", data={"day": "2026-01-01", "title": "수정됨", "status": "fail"})
    assert "수정됨" in client.get(loc).get_data(as_text=True)
    client.post(f"/entries/{eid}/delete")
    assert client.get(loc).status_code == 404


def test_filters(client):
    add(client, title="A", tags="vision", status="fail")
    add(client, title="B", tags="nlp")
    html = client.get("/?tag=vision").get_data(as_text=True)
    assert ">A<" in html and ">B<" not in html
    html = client.get("/?status=fail").get_data(as_text=True)
    assert ">A<" in html and ">B<" not in html
    html = client.get("/?q=B").get_data(as_text=True)
    assert ">B<" in html and ">A<" not in html


def test_streak(client):
    today = date.today()
    for i in (1, 2, 3, 5):  # 오늘 없음, 어제~3일 전 연속
        add(client, day=(today - timedelta(days=i)).isoformat())
    assert "<b>3일</b><span>연속 기록" in client.get("/").get_data(as_text=True)


def test_export(client):
    add(client)
    md = client.get("/export.md").get_data(as_text=True)
    assert "### LoRA 실습" in md and "```\npython train.py\n```" in md and "#llm #lora" in md


def test_normalize_tags():
    assert normalize_tags(" #LLM, llm,, Vision ") == "llm,vision"

"""AI 학습 일지 — 매일의 AI 학습과 실행 결과를 기록하는 작은 Flask 앱."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, url_for)

BASE_DIR = Path(__file__).resolve().parent
STATUSES = {"success": "성공", "partial": "부분 성공", "fail": "실패"}


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("AILOG_DB", str(BASE_DIR / "ailog.db")),
    )
    if test_config:
        app.config.update(test_config)

    # ---------- DB ----------
    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        get_db().executescript((BASE_DIR / "schema.sql").read_text())

    # ---------- helpers ----------
    def parse_form() -> tuple[dict, list[str]]:
        f = request.form
        data = {
            "day": f.get("day", "").strip() or date.today().isoformat(),
            "title": f.get("title", "").strip(),
            "learned": f.get("learned", "").strip(),
            "executed": f.get("executed", "").strip(),
            "result": f.get("result", "").strip(),
            "status": f.get("status", "success"),
            "tags": normalize_tags(f.get("tags", "")),
            "minutes": f.get("minutes", "0").strip() or "0",
        }
        errors = []
        if not data["title"]:
            errors.append("제목을 입력하세요.")
        try:
            date.fromisoformat(data["day"])
        except ValueError:
            errors.append("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")
        if data["status"] not in STATUSES:
            errors.append("상태 값이 올바르지 않습니다.")
        try:
            data["minutes"] = max(0, int(data["minutes"]))
        except ValueError:
            errors.append("학습 시간은 숫자(분)로 입력하세요.")
        return data, errors

    def get_entry(entry_id: int) -> sqlite3.Row:
        row = get_db().execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            abort(404)
        return row

    def query_entries(q: str = "", tag: str = "", status: str = "") -> list[sqlite3.Row]:
        sql, args = "SELECT * FROM entries WHERE 1=1", []
        if q:
            sql += " AND (title LIKE ? OR learned LIKE ? OR executed LIKE ? OR result LIKE ?)"
            args += [f"%{q}%"] * 4
        if tag:
            sql += " AND (',' || tags || ',') LIKE ?"
            args.append(f"%,{tag},%")
        if status in STATUSES:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY day DESC, id DESC"
        return get_db().execute(sql, args).fetchall()

    def stats() -> dict:
        db = get_db()
        days = {r["day"]: r["n"] for r in db.execute(
            "SELECT day, COUNT(*) AS n FROM entries GROUP BY day")}
        today = date.today()
        # 연속 기록일 (오늘 기록이 없으면 어제부터 계산)
        streak, cur = 0, today if today.isoformat() in days else today - timedelta(days=1)
        while cur.isoformat() in days:
            streak += 1
            cur -= timedelta(days=1)
        # 최근 12주 히트맵 (월요일 시작 주 단위)
        start = today - timedelta(days=today.weekday() + 7 * 11)
        weeks = []
        for w in range(12):
            week = []
            for d in range(7):
                day = start + timedelta(days=w * 7 + d)
                week.append({"day": day.isoformat(), "n": days.get(day.isoformat(), 0),
                             "future": day > today})
            weeks.append(week)
        totals = db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(minutes),0) AS m, "
            "SUM(status='success') AS ok FROM entries").fetchone()
        tag_counts: dict[str, int] = {}
        for r in db.execute("SELECT tags FROM entries WHERE tags != ''"):
            for t in r["tags"].split(","):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        return {
            "streak": streak, "weeks": weeks, "total": totals["n"],
            "hours": round(totals["m"] / 60, 1), "days": len(days),
            "success_rate": round(100 * (totals["ok"] or 0) / totals["n"]) if totals["n"] else 0,
            "tags": sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:20],
        }

    @app.template_filter("taglist")
    def taglist(s: str) -> list[str]:
        return [t for t in s.split(",") if t]

    @app.context_processor
    def inject():
        return {"STATUSES": STATUSES}

    # ---------- routes ----------
    @app.get("/")
    def index():
        q = request.args.get("q", "").strip()
        tag = request.args.get("tag", "").strip()
        status = request.args.get("status", "")
        return render_template("index.html", entries=query_entries(q, tag, status),
                               stats=stats(), q=q, tag=tag, status=status)

    @app.route("/entries/new", methods=["GET", "POST"])
    def new_entry():
        if request.method == "POST":
            data, errors = parse_form()
            if not errors:
                cur = get_db().execute(
                    "INSERT INTO entries (day, title, learned, executed, result, status, tags, minutes) "
                    "VALUES (:day, :title, :learned, :executed, :result, :status, :tags, :minutes)", data)
                get_db().commit()
                flash("기록을 저장했습니다.")
                return redirect(url_for("detail", entry_id=cur.lastrowid))
            for e in errors:
                flash(e, "error")
            return render_template("form.html", entry=data, mode="new"), 400
        return render_template("form.html", mode="new",
                               entry={"day": date.today().isoformat(), "status": "success"})

    @app.get("/entries/<int:entry_id>")
    def detail(entry_id: int):
        return render_template("detail.html", entry=get_entry(entry_id))

    @app.route("/entries/<int:entry_id>/edit", methods=["GET", "POST"])
    def edit(entry_id: int):
        entry = get_entry(entry_id)
        if request.method == "POST":
            data, errors = parse_form()
            if not errors:
                get_db().execute(
                    "UPDATE entries SET day=:day, title=:title, learned=:learned, executed=:executed, "
                    "result=:result, status=:status, tags=:tags, minutes=:minutes, "
                    "updated_at=datetime('now','localtime') WHERE id=:id", {**data, "id": entry_id})
                get_db().commit()
                flash("수정했습니다.")
                return redirect(url_for("detail", entry_id=entry_id))
            for e in errors:
                flash(e, "error")
            return render_template("form.html", entry={**data, "id": entry_id}, mode="edit"), 400
        return render_template("form.html", entry=entry, mode="edit")

    @app.post("/entries/<int:entry_id>/delete")
    def delete(entry_id: int):
        get_entry(entry_id)
        get_db().execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        get_db().commit()
        flash("삭제했습니다.")
        return redirect(url_for("index"))

    @app.get("/export.md")
    def export_md():
        """전체 기록을 날짜별 마크다운으로 내보내기 (블로그/노션 붙여넣기용)."""
        lines = ["# AI 학습 일지", ""]
        current = None
        for e in reversed(query_entries()):
            if e["day"] != current:
                current = e["day"]
                lines += [f"## {current}", ""]
            lines.append(f"### {e['title']}  `{STATUSES[e['status']]}`"
                         + (f" · {e['minutes']}분" if e["minutes"] else ""))
            if e["tags"]:
                lines.append(" ".join(f"#{t}" for t in e["tags"].split(",")))
            for label, key, code in (("배운 것", "learned", False),
                                     ("실행", "executed", True), ("결과", "result", False)):
                if e[key]:
                    lines += ["", f"**{label}**", ""]
                    lines += ["```", e[key], "```"] if code else [e[key]]
            lines.append("")
        return Response("\n".join(lines), mimetype="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=ai-log.md"})

    return app


def normalize_tags(raw: str) -> str:
    seen: list[str] = []
    for t in raw.replace("#", "").split(","):
        t = t.strip().lower()
        if t and t not in seen:
            seen.append(t)
    return ",".join(seen)


if __name__ == "__main__":
    create_app().run(debug=True, port=int(os.environ.get("PORT", 5000)))

"""AI 학습 일지 — 매일의 AI 학습과 실행 결과를 기록하는 작은 Flask 앱."""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, url_for)

from storage import StoreError, make_store

BASE_DIR = Path(__file__).resolve().parent
STATUSES = {"success": "성공", "partial": "부분 성공", "fail": "실패"}


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("AILOG_DB", str(BASE_DIR / "ailog.db")),
        SUPABASE_URL=os.environ.get("SUPABASE_URL", ""),
        SUPABASE_SECRET_KEY=os.environ.get("SUPABASE_SECRET_KEY", ""),
    )
    if test_config:
        app.config.update(test_config)
    store = app.config.get("STORE") or make_store(app.config)
    app.extensions["store"] = store

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

    def get_entry(entry_id: int) -> dict:
        row = store.get(entry_id)
        if row is None:
            abort(404)
        return row

    def stats(rows: list[dict]) -> dict:
        days: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        minutes = ok = 0
        for r in rows:
            days[r["day"]] = days.get(r["day"], 0) + 1
            minutes += r["minutes"] or 0
            ok += r["status"] == "success"
            for t in taglist(r["tags"]):
                tag_counts[t] = tag_counts.get(t, 0) + 1
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
        return {
            "streak": streak, "weeks": weeks, "total": len(rows),
            "hours": round(minutes / 60, 1), "days": len(days),
            "success_rate": round(100 * ok / len(rows)) if rows else 0,
            "tags": sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:20],
        }

    @app.template_filter("taglist")
    def taglist(s: str) -> list[str]:
        return [t for t in (s or "").split(",") if t]

    @app.context_processor
    def inject():
        return {"STATUSES": STATUSES, "STORE_NAME": store.name}

    @app.errorhandler(StoreError)
    def store_error(e: StoreError):
        return render_template("error.html", message=str(e)), 503

    # ---------- routes ----------
    @app.get("/")
    def index():
        q = request.args.get("q", "").strip()
        tag = request.args.get("tag", "").strip()
        status = request.args.get("status", "")
        status = status if status in STATUSES else ""
        filtered = store.list(q, tag, status)
        all_rows = filtered if not (q or tag or status) else store.list()
        return render_template("index.html", entries=filtered, stats=stats(all_rows),
                               q=q, tag=tag, status=status)

    @app.route("/entries/new", methods=["GET", "POST"])
    def new_entry():
        if request.method == "POST":
            data, errors = parse_form()
            if not errors:
                entry_id = store.create(data)
                flash("기록을 저장했습니다.")
                return redirect(url_for("detail", entry_id=entry_id))
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
                store.update(entry_id, data)
                flash("수정했습니다.")
                return redirect(url_for("detail", entry_id=entry_id))
            for e in errors:
                flash(e, "error")
            return render_template("form.html", entry={**data, "id": entry_id}, mode="edit"), 400
        return render_template("form.html", entry=entry, mode="edit")

    @app.post("/entries/<int:entry_id>/delete")
    def delete(entry_id: int):
        get_entry(entry_id)
        store.delete(entry_id)
        flash("삭제했습니다.")
        return redirect(url_for("index"))

    @app.get("/export.md")
    def export_md():
        """전체 기록을 날짜별 마크다운으로 내보내기 (블로그/노션 붙여넣기용)."""
        lines = ["# AI 학습 일지", ""]
        current = None
        for e in reversed(store.list()):
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
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
    application = create_app()
    print(f" * 저장소: {application.extensions['store'].name}")
    application.run(debug=True, port=int(os.environ.get("PORT", 5000)))

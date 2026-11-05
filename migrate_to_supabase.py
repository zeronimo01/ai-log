"""로컬 ailog.db(SQLite)의 기록을 Supabase로 옮긴다.

사용법:  python migrate_to_supabase.py
  (.env에 SUPABASE_URL, SUPABASE_SECRET_KEY가 있어야 함)
Supabase에 이미 기록이 있으면 중복을 막기 위해 멈춘다. 그래도 진행하려면 --force.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from storage import FIELDS, SQLiteStore, StoreError, SupabaseStore

BASE_DIR = Path(__file__).resolve().parent


def to_utc_iso(local: str) -> str:
    return datetime.strptime(local, "%Y-%m-%d %H:%M:%S").astimezone().isoformat()


def main() -> int:
    load_dotenv(BASE_DIR / ".env")
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SECRET_KEY")
    db = os.environ.get("AILOG_DB", str(BASE_DIR / "ailog.db"))
    if not (url and key):
        print("[오류] .env에 SUPABASE_URL과 SUPABASE_SECRET_KEY를 먼저 넣으세요.")
        return 1
    if not Path(db).exists():
        print(f"[안내] 옮길 로컬 기록이 없습니다 ({db} 없음).")
        return 0

    rows = SQLiteStore(db).list()
    target = SupabaseStore(url, key)
    try:
        existing = target.list()
        if existing and "--force" not in sys.argv:
            print(f"[중단] Supabase에 이미 기록 {len(existing)}개가 있습니다. "
                  "중복이 생길 수 있어 멈췄습니다. 그래도 옮기려면 --force 를 붙이세요.")
            return 1
        for i, r in enumerate(reversed(rows), 1):  # 오래된 것부터
            target.create({f: r[f] for f in FIELDS},
                          extra={"created_at": to_utc_iso(r["created_at"]),
                                 "updated_at": to_utc_iso(r["updated_at"])})
            print(f"  {i}/{len(rows)}  {r['day']}  {r['title']}")
    except StoreError as e:
        print(f"[오류] {e}")
        return 1
    print(f"완료: {len(rows)}개를 Supabase로 옮겼습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT    NOT NULL,              -- YYYY-MM-DD
    title       TEXT    NOT NULL,
    learned     TEXT    NOT NULL DEFAULT '',   -- 오늘 배운 것
    executed    TEXT    NOT NULL DEFAULT '',   -- 실행한 코드/명령/프롬프트
    result      TEXT    NOT NULL DEFAULT '',   -- 실행 결과
    status      TEXT    NOT NULL DEFAULT 'success'
                CHECK (status IN ('success', 'partial', 'fail')),
    tags        TEXT    NOT NULL DEFAULT '',   -- 쉼표 구분
    minutes     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_entries_day ON entries(day);

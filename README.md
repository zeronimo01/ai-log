# AI 학습 일지

매일의 AI 학습 내용과 실행 결과(코드·명령·프롬프트 → 결과)를 기록하고 돌아보는 1인용 웹 서비스.

## 스택
- **Python 3.11+ / Flask** — 서버 렌더링, 빌드 단계 없음
- **Supabase(Postgres)** — `.env`에 키를 넣으면 클라우드에 저장 (어느 PC에서든 같은 기록)
- **SQLite** — `.env`가 없으면 이 폴더의 `ailog.db`에 저장
- **Jinja 템플릿 + 순수 CSS** — JS 프레임워크 없음, 다크 모드 지원

## 기능
- 기록: 날짜 · 제목 · 배운 것 · 실행한 것 · 결과 · 상태(성공/부분/실패) · 태그 · 학습 시간
- 대시보드: 연속 기록일, 누적 시간, 실행 성공률, 최근 12주 히트맵
- 검색 / 태그 · 상태 필터
- 전체 기록을 마크다운으로 내보내기 (`/export.md`) — 블로그·노션에 붙여넣기용

## Supabase 연결
1. **테이블 만들기:** Supabase 대시보드 → **SQL Editor** → New query에 `supabase/schema.sql` 내용을 전부 붙여넣고 **Run**.
2. **키 넣기:** `.env.example`을 복사해 이름을 `.env`로 바꾸고 `SUPABASE_URL`, `SUPABASE_SECRET_KEY`를 채웁니다.
   - Windows PowerShell: `copy .env.example .env` → `notepad .env`
   - 키 위치: 대시보드 → Project Settings → **API Keys** → Secret keys (`sb_secret_...`)
3. 앱을 다시 실행하면 화면 맨 아래에 **저장소: Supabase**가 표시됩니다.
4. (선택) 기존 로컬 기록 옮기기: `python migrate_to_supabase.py` (Windows: `.venv\Scripts\python migrate_to_supabase.py`)

secret 키는 서버(내 PC의 Flask)에서만 쓰이고 브라우저로는 보내지 않습니다. `.env`는 `.gitignore`에 들어 있어 GitHub에 올라가지 않습니다.
테이블은 RLS가 켜져 있고 정책이 없어서, 공개(publishable) 키로는 접근할 수 없습니다.

## Windows에서 실행 (가장 쉬운 방법)
1. [Python](https://www.python.org/downloads/)을 설치합니다. 설치 첫 화면에서 **"Add python.exe to PATH"를 꼭 체크**하세요.
2. 이 저장소를 받습니다. `git clone`을 쓰거나, GitHub의 **Code → Download ZIP** 후 압축을 풉니다.
3. 폴더 안의 **`run.bat`을 더블클릭**합니다.
   - 처음 한 번은 가상환경 생성과 패키지 설치를 자동으로 합니다(1~2분).
   - 서버가 뜨면 브라우저가 자동으로 http://localhost:5000 을 엽니다.
   - 검은 창을 닫으면 앱이 종료됩니다. 쓰는 동안은 열어두세요.
   - 이미 실행 중일 때 다시 더블클릭하면 브라우저만 열립니다.

ZIP으로 받은 경우 "Windows의 PC 보호" 창이 뜰 수 있습니다. 그때는 **추가 정보 → 실행**을 누르세요.

## 실행 (Mac / Linux / 터미널)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py          # http://localhost:5000
.venv/bin/pytest -q              # 테스트
```
환경변수(`.env`에 써도 됨): `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `AILOG_DB`(SQLite 경로), `PORT`, `SECRET_KEY`(배포 시 반드시 설정).

## 구조
```
app.py          라우트 · 통계
storage.py      저장소 (Supabase / SQLite)
supabase/       Supabase 테이블 SQL
migrate_to_supabase.py  로컬 기록 → Supabase 이전
run.bat         Windows 더블클릭 실행
schema.sql      테이블 정의
templates/      base / index / form / detail
static/style.css
tests/          pytest
```

# AI 학습 일지

매일의 AI 학습 내용과 실행 결과(코드·명령·프롬프트 → 결과)를 기록하고 돌아보는 1인용 웹 서비스.

## 스택
- **Python 3.11+ / Flask** — 서버 렌더링, 빌드 단계 없음
- **SQLite** — 파일 하나(`ailog.db`)로 끝나는 저장소, 백업은 파일 복사
- **Jinja 템플릿 + 순수 CSS** — JS 프레임워크 없음, 다크 모드 지원

## 기능
- 기록: 날짜 · 제목 · 배운 것 · 실행한 것 · 결과 · 상태(성공/부분/실패) · 태그 · 학습 시간
- 대시보드: 연속 기록일, 누적 시간, 실행 성공률, 최근 12주 히트맵
- 검색 / 태그 · 상태 필터
- 전체 기록을 마크다운으로 내보내기 (`/export.md`) — 블로그·노션에 붙여넣기용

## 실행
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py          # http://localhost:5000
.venv/bin/pytest -q              # 테스트
```
환경변수: `AILOG_DB`(DB 경로), `PORT`, `SECRET_KEY`(배포 시 반드시 설정).

## 구조
```
app.py          라우트 · DB · 통계
schema.sql      테이블 정의
templates/      base / index / form / detail
static/style.css
tests/          pytest
```

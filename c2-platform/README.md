# C2 Platform

Lattice OS 스타일의 **Command & Control** 플랫폼입니다. 웹 인터페이스와 REST API를 통해 서브시스템에 명령을 내릴 수 있습니다.

## 기능

1. **Web 인터페이스**  
   - 대시보드에서 서브시스템 목록 확인  
   - 대상(단일/전체), 액션, 파라미터를 입력해 명령 전송  
   - 최근 명령 이력 표시  

2. **REST API**  
   - `GET /api/subsystems` — 서브시스템 목록  
   - `POST /api/commands` — 명령 전송  
   - `GET /api/commands` — 최근 명령 조회  

## 요구 사항

- Python 3.9+

## 설치 및 실행

```bash
cd c2-platform
uv sync
uv run python src/main.py --config var/config.yml
```

또는 포트/호스트 지정:

```bash
uv run python src/main.py --host 0.0.0.0 --port 8080 --config var/config.yml
```

실행 후 브라우저에서 **http://localhost:8080** 으로 접속합니다.

- **기본 포트**: 8080 (다른 앱과 충돌 시 `--port 8000` 등으로 변경)
- **호스트**: 기본값 `0.0.0.0` — 같은 PC는 `http://127.0.0.1:8080`, 다른 기기는 `http://<이 PC IP>:8080`으로 접속
- **접속이 안 될 때**: Windows 방화벽에서 해당 포트(TCP) 인바운드 허용 후 재시도

## 설정 (var/config.yml)

서브시스템을 YAML로 정의합니다. 각 항목에 `endpoint`를 넣으면 해당 URL로 HTTP POST가 전송됩니다.

```yaml
subsystems:
  - id: nav
    name: Navigation
    description: Course and waypoint commands
    enabled: true
    endpoint: http://localhost:9001/command   # 선택 사항

  - id: propulsion
    name: Propulsion
    enabled: true
```

명령 페이로드 형식 (서브시스템 endpoint로 전송되는 body):

```json
{
  "action": "set_course",
  "params": { "heading": 90, "speed_knots": 10 }
}
```

## API 예시

```bash
# 서브시스템 목록
curl http://localhost:8000/api/subsystems

# 명령 전송 (단일 대상)
curl -X POST http://localhost:8000/api/commands \
  -H "Content-Type: application/json" \
  -d '{"target":"nav","action":"set_course","params":{"heading":90}}'

# Broadcast (전체)
curl -X POST http://localhost:8000/api/commands \
  -H "Content-Type: application/json" \
  -d '{"target":"broadcast","action":"ping","params":{}}'

# 최근 명령 조회
curl http://localhost:8000/api/commands
```

## 프로젝트 구조

```
c2-platform/
├── pyproject.toml
├── README.md
├── var/
│   └── config.yml       # 서브시스템 설정
└── src/
    ├── main.py          # 진입점
    └── c2/
        ├── __init__.py
        ├── api.py       # FastAPI 앱, 라우트
        ├── config.py    # 설정 로드
        ├── dispatcher.py # 서브시스템으로 명령 전달
        ├── models.py    # Pydantic 모델
        └── templates/
            └── index.html  # 웹 UI
```

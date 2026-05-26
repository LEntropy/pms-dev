# PMS 테스트 가이드 — Ubuntu 서버 + Windows 클라이언트

## 전체 구성도

```
[Windows PC] ─── (브라우저/curl/에이전트) ───► [Ubuntu 서버]
                                                     │
                                              Docker Compose
                                           ┌──────────────────┐
                                           │ Nginx :80/:443   │
                                           │ FastAPI :8000    │
                                           │ PostgreSQL :5432 │
                                           │ Redis :6379      │
                                           │ MinIO :9000/9001 │
                                           │ Celery worker    │
                                           │ Celery beat      │
                                           └──────────────────┘
```

---

## 1단계 — GitHub에서 코드 받기

### GitHub 저장소 먼저 생성 (한 번만)

1. [github.com/new](https://github.com/new) 접속
2. Repository name: `pms-dev`
3. **Private** 선택 (소스 비공개)
4. **"Add a README file" 체크 해제** (빈 저장소로 생성)
5. **Create repository** 클릭

### Windows에서 Push

PowerShell 또는 Git Bash에서:

```bash
cd C:\Users\mello\Desktop\PMS_dev

# Personal Access Token(PAT) 방식으로 push
# GitHub → Settings → Developer settings → Personal access tokens → Tokens(classic) → Generate new token
# 권한: repo 전체 체크
git push -u origin main
# Username: LEntropy
# Password: (PAT 토큰 붙여넣기)
```

### Ubuntu 서버에서 클론

```bash
git clone https://github.com/LEntropy/pms-dev.git
cd pms-dev
```

---

## 2단계 — Ubuntu 서버 환경 준비

### 2-1. 필수 패키지 설치

```bash
# Docker 설치 (Ubuntu 22.04 기준)
sudo apt update
sudo apt install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# docker를 sudo 없이 실행
sudo usermod -aG docker $USER
newgrp docker

# 확인
docker --version
docker compose version
```

### 2-2. 방화벽 설정

```bash
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS (나중에 TLS 설정 후)
sudo ufw allow 8000  # FastAPI 직접 테스트용 (테스트 후 닫아도 됨)
sudo ufw allow 9001  # MinIO 콘솔 (선택)
sudo ufw enable
```

---

## 3단계 — 서버 기동

### 3-1. 환경변수 파일 작성

```bash
cd ~/pms-dev/infra

cp .env.production .env

# 아래 값들을 실제 강력한 패스워드로 교체
nano .env
```

**최소 필수 수정 항목:**

```env
POSTGRES_PASSWORD=강력한_DB_패스워드_입력
REDIS_PASSWORD=강력한_Redis_패스워드
MINIO_ROOT_PASSWORD=강력한_MinIO_패스워드
SECRET_KEY=$(openssl rand -hex 32)   # 터미널에서 직접 생성
```

> `SECRET_KEY`는 터미널에서 `openssl rand -hex 32` 실행 후 출력값 복사

### 3-2. 개발 모드로 빠르게 실행 (권장 — 첫 테스트)

```bash
cd ~/pms-dev/infra

# 환경변수 없이 기본값으로 바로 실행 (내부망 테스트용)
docker compose up -d

# 로그 확인
docker compose logs -f pms-server
```

**서비스별 접속 확인:**

| 서비스 | URL | 비고 |
|-------|-----|------|
| API Docs | `http://서버IP:8000/api/docs` | Swagger UI |
| API Health | `http://서버IP:8000/api/health` | 상태 확인 |
| MinIO 콘솔 | `http://서버IP:9001` | ID: pms_minio / PW: minio_secret |
| Nginx | `http://서버IP:80` | 대시보드 진입점 |

### 3-3. 초기 관리자 계정 생성

```bash
docker exec pms-server python seed.py
```

출력 예시:
```
Created admin user: admin@pms.local / admin1234!
Enrollment token: xxxx-yyyy-zzzz
```

> **이 토큰을 반드시 메모하세요** — 에이전트 등록에 필요합니다

---

## 4단계 — Windows에서 API 테스트

### 4-1. curl로 기본 동작 확인

PowerShell에서 (서버IP를 실제 IP로 교체):

```powershell
$SERVER = "http://192.168.x.x:8000"

# 헬스체크
Invoke-RestMethod "$SERVER/api/health"

# 로그인
$body = @{ username="admin@pms.local"; password="admin1234!" } | ConvertTo-Json
$resp = Invoke-RestMethod "$SERVER/api/v1/auth/login" -Method POST -Body $body -ContentType "application/json"
$TOKEN = $resp.access_token
Write-Host "Token: $TOKEN"

# 엔드포인트 목록 (빈 상태)
Invoke-RestMethod "$SERVER/api/v1/endpoints/" -Headers @{ Authorization="Bearer $TOKEN" }
```

### 4-2. 에이전트 등록 테스트

```powershell
$ENROLLMENT_TOKEN = "seed.py에서 출력된 토큰"

$enrollBody = @{
    enrollment_token = $ENROLLMENT_TOKEN
    hostname         = $env:COMPUTERNAME
    platform         = "windows"
    ip_address       = "192.168.x.x"
    mac_address      = "AA:BB:CC:DD:EE:FF"
    os_version       = "Windows 10 22H2"
    agent_version    = "1.0.0"
} | ConvertTo-Json

$enrollResp = Invoke-RestMethod "$SERVER/api/v1/agent/enroll" `
    -Method POST -Body $enrollBody -ContentType "application/json"

$AGENT_TOKEN = $enrollResp.agent_token
Write-Host "Agent token: $AGENT_TOKEN"
```

### 4-3. Heartbeat 전송

```powershell
$hbBody = @{
    status        = "online"
    cpu_usage     = 15.5
    memory_usage  = 62.3
    disk_usage    = 45.0
    agent_version = "1.0.0"
} | ConvertTo-Json

Invoke-RestMethod "$SERVER/api/v1/agent/heartbeat" `
    -Method POST -Body $hbBody -ContentType "application/json" `
    -Headers @{ Authorization="Bearer $AGENT_TOKEN" }
```

### 4-4. 소프트웨어 인벤토리 전송

```powershell
$invBody = @{
    software = @(
        @{ raw_name="Google Chrome"; version="124.0.6367.82"; vendor="Google LLC" }
        @{ raw_name="7-Zip 23.01"; version="23.01"; vendor="Igor Pavlov" }
        @{ raw_name="Python 3.11.9"; version="3.11.9"; vendor="Python Software Foundation" }
    )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod "$SERVER/api/v1/agent/inventory" `
    -Method POST -Body $invBody -ContentType "application/json" `
    -Headers @{ Authorization="Bearer $AGENT_TOKEN" }
```

### 4-5. 작업 폴링

```powershell
# 대기 중인 작업 확인
Invoke-RestMethod "$SERVER/api/v1/agent/tasks" `
    -Headers @{ Authorization="Bearer $AGENT_TOKEN" }
```

---

## 5단계 — Swagger UI로 전체 흐름 테스트

브라우저에서 `http://서버IP:8000/api/docs` 접속

### 순서대로 실행:

1. **POST /api/v1/auth/login** → `access_token` 복사
2. 우측 상단 **Authorize** 버튼 → `Bearer {토큰}` 입력
3. **GET /api/v1/endpoints/** → 등록된 에이전트 확인
4. **POST /api/v1/patches/** → 패치 업로드 (파일 필요)
5. **POST /api/v1/policies/** → 정책 생성
6. **POST /api/v1/deployments/** → 배포 생성
7. **GET /api/v1/deployments/{id}** → 배포 상태 확인

---

## 6단계 — MinIO 파일 업로드 확인

브라우저에서 `http://서버IP:9001` 접속
- ID: `pms_minio` / PW: `minio_secret`
- `patches` 버킷에 패치 파일이 업로드되는지 확인

---

## 7단계 — 실제 에이전트 실행 (선택)

### Ubuntu에서 에이전트 직접 실행 (Python)

```bash
cd ~/pms-dev/pms-agent

pip install -r requirements.txt

# 환경변수 설정
export PMS_SERVER_URL="http://localhost:8000"
export PMS_ENROLLMENT_TOKEN="seed.py에서_출력된_토큰"
export PMS_AGENT_VERSION="1.0.0"

python -m agent.main
```

---

## 테스트 체크리스트

### 인프라 기동 확인

- [ ] `docker compose ps` 모든 서비스 `healthy` 상태
- [ ] `docker compose logs pms-server` 에러 없음
- [ ] `http://서버IP:8000/api/health` → `{"status":"ok"}` 반환
- [ ] `http://서버IP:9001` MinIO 콘솔 접속 성공

### 인증 API

- [ ] `POST /api/v1/auth/login` 올바른 자격증명 → 200 + `access_token` 반환
- [ ] `POST /api/v1/auth/login` 잘못된 자격증명 → 401 반환
- [ ] `GET /api/v1/endpoints/` 토큰 없이 → 401 반환
- [ ] `GET /api/v1/endpoints/` 유효한 토큰 → 200 반환

### 에이전트 통신

- [ ] `POST /api/v1/agent/enroll` 유효한 토큰 → `agent_token` + `server_public_key` 반환
- [ ] `POST /api/v1/agent/enroll` 잘못된 토큰 → 401 반환
- [ ] `POST /api/v1/agent/heartbeat` → 200 반환 + Redis에 온라인 상태 기록
- [ ] `POST /api/v1/agent/inventory` → 200 반환 + DB에 소프트웨어 저장
- [ ] `GET /api/v1/agent/tasks` → 200 반환 (빈 배열 또는 작업 목록)

### 관리자 API

- [ ] `GET /api/v1/endpoints/{id}` → 등록한 에이전트 정보 반환
- [ ] `GET /api/v1/endpoints/{id}/compliance` → 컴플라이언스 결과 반환
- [ ] `POST /api/v1/patches/` 파일 업로드 → 201 + MinIO 저장 확인
- [ ] `GET /api/v1/patches/` → 업로드된 패치 목록 반환
- [ ] `POST /api/v1/policies/` → 정책 생성 성공
- [ ] `POST /api/v1/deployments/` → 배포 생성 + Celery 작업 실행 확인

### Celery 작업

- [ ] `docker compose logs celery-worker` 배포 작업 수행 로그 확인
- [ ] `GET /api/v1/deployments/{id}` 상태가 진행 중 → 완료로 변경

### 보안

- [ ] 만료된 토큰으로 요청 → 401 반환
- [ ] Viewer 계정으로 DELETE 요청 → 403 반환
- [ ] 연속 12회 로그인 시도 → 429 Rate Limit 반환

### MinIO 파일 저장

- [ ] 패치 업로드 후 MinIO 콘솔 `patches` 버킷에서 파일 확인
- [ ] `GET /api/v1/agent/patches/{id}/download-url` → 서명된 URL 반환
- [ ] 반환된 URL로 직접 파일 다운로드 가능

### WebSocket (선택)

```javascript
// 브라우저 콘솔에서 실행
const token = "Bearer {access_token}";
const ws = new WebSocket("ws://서버IP:8000/ws/endpoints/status");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```
- [ ] WebSocket 연결 성공
- [ ] Heartbeat 전송 시 실시간 업데이트 수신

---

## 트러블슈팅

### 컨테이너가 시작 안 됨

```bash
docker compose logs postgres    # DB 연결 문제
docker compose logs pms-server  # 앱 에러 확인
docker compose logs redis       # Redis 연결 문제
```

### 마이그레이션 실패

```bash
docker exec pms-server alembic upgrade head
docker exec pms-server alembic current
```

### 포트 충돌

```bash
sudo lsof -i :5432   # PostgreSQL
sudo lsof -i :6379   # Redis
sudo lsof -i :8000   # FastAPI
sudo lsof -i :9000   # MinIO
```

### 서비스 재시작

```bash
docker compose restart pms-server
docker compose down && docker compose up -d   # 전체 재시작
docker compose down -v                         # 데이터 포함 전체 삭제 (주의!)
```

---

## 서버 IP 확인 방법

```bash
# Ubuntu에서
ip addr show | grep "inet " | grep -v 127.0.0.1
# 또는
hostname -I | awk '{print $1}'
```

# MoveWise 배포 가이드

백엔드(FastAPI)와 프론트엔드(Expo 앱)을 **실제로 팀이 쓸 수 있게** 배포하는 옵션 정리.

---

## 📦 1. 백엔드 배포 옵션

### 옵션 A. Azure App Service (MSAI09 목표 구조)

```bash
# 1) 리소스 그룹 + App Service Plan + Web App 생성
az group create --name movewise-rg --location koreacentral
az appservice plan create --name movewise-plan --resource-group movewise-rg --sku B1 --is-linux
az webapp create --resource-group movewise-rg --plan movewise-plan \
  --name movewise-api --runtime "PYTHON|3.12"

# 2) 환경변수 (Configuration → Application settings)
az webapp config appsettings set --resource-group movewise-rg --name movewise-api \
  --settings AZURE_OPENAI_ENDPOINT=... AZURE_OPENAI_API_KEY=... AZURE_SEARCH_ENDPOINT=... \
             AZURE_SEARCH_API_KEY=... LAW_OC=... DATA_GO_KR_SERVICE_KEY=...

# 3) Startup command
az webapp config set --resource-group movewise-rg --name movewise-api \
  --startup-file "uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"

# 4) Zip deploy
cd 2차프로젝트
zip -r deploy.zip backend -x "*.venv/*" "*__pycache__*" "*/samples/*"
az webapp deploy --resource-group movewise-rg --name movewise-api --src-path deploy.zip --type zip
```

→ `https://movewise-api.azurewebsites.net`

### 옵션 B. Docker + Render.com (무료 티어, 5분 완료)

1. **Render 가입** — render.com (GitHub 연동 권장)
2. New → **Web Service** → GitHub 레포 연결
3. 설정:
   - Environment: **Docker**
   - Dockerfile Path: `backend/Dockerfile`
   - Root Directory: *(비우기)*
   - Instance Type: **Free**
4. Environment Variables 탭에 `.env` 값 입력
5. Deploy

→ `https://movewise.onrender.com`

### 옵션 C. Docker + Fly.io

```bash
brew install flyctl
cd 2차프로젝트
fly launch --dockerfile backend/Dockerfile --name movewise-api
fly secrets set AZURE_OPENAI_API_KEY=... AZURE_SEARCH_API_KEY=... ...
fly deploy
```

→ `https://movewise-api.fly.dev`

### 옵션 D. 로컬 Docker 테스트

```bash
cd 2차프로젝트
docker compose up --build
curl http://127.0.0.1:8765/health
```

### 옵션 E. Cloudflare Quick Tunnel (임시, 발표 직전용)

```bash
# 백엔드 로컬 실행
python3 -m uvicorn backend.app.main:app --port 8765

# 별도 터미널에서
cloudflared tunnel --url http://127.0.0.1:8765
```

→ 나오는 `https://<random>.trycloudflare.com` 공유. Mac 켜져 있는 동안만 유효.

---

## 📱 2. 프론트엔드 배포 옵션

### 옵션 A. Expo 웹 정적 호스팅 (Vercel / Netlify / Cloudflare Pages)

```bash
cd frontend/movewise-app
npx expo export --platform web
# 생성된 dist/ 폴더를 Vercel / Netlify에 업로드
```

Vercel 예시:
```bash
npm install -g vercel
cd frontend/movewise-app
vercel  # dist/ 배포 선택
vercel env add EXPO_PUBLIC_API_URL  # 백엔드 URL 입력
```

### 옵션 B. Expo EAS Build (iOS/Android 네이티브)

```bash
cd frontend/movewise-app
npm install -g eas-cli
eas login
eas build:configure

# 프리뷰 빌드 (TestFlight / APK)
eas build --platform ios --profile preview
eas build --platform android --profile preview
```

### 옵션 C. Expo Go (가장 빠름, 개발 공유용)

```bash
cd frontend/movewise-app
npx expo start --tunnel
```

QR 코드를 팀원이 Expo Go 앱으로 스캔 → 바로 실행.

---

## 🔐 3. Secrets 관리

### 로컬 개발
`backend/.env` (git 제외) 사용.

### Azure App Service
App Service Configuration → Application settings (자동 환경변수 주입).

### Render
Service → Environment → 각 키 추가.

### Fly.io
```bash
fly secrets set AZURE_OPENAI_API_KEY=...
```

### Docker Compose
`.env` 파일을 compose와 같은 디렉토리에 두면 `${VAR}` 참조 자동 읽음.

---

## 🌐 4. 도메인 + HTTPS (옵션)

### Azure App Service
기본으로 `*.azurewebsites.net` 제공. 커스텀 도메인 연결 시:
1. Azure Portal → App Service → Custom domains
2. CNAME 설정 (Cloudflare 등)
3. Managed Certificate 발급 (무료)

### Cloudflare 고정 터널 (도메인 필수)
```bash
cloudflared tunnel create movewise
cloudflared tunnel route dns movewise api.your-domain.com
cloudflared tunnel run movewise
```

---

## ⚠️ 5. 배포 체크리스트

- [ ] `.env` git 제외 확인 (`.gitignore` 검증)
- [ ] `allow_origins=["*"]` 프로덕션에서는 특정 도메인만 허용하도록 좁히기
- [ ] FastAPI `/docs` 프로덕션에서는 비활성화 고려 (`docs_url=None`)
- [ ] Azure OpenAI 배포명(`AZURE_OPENAI_DEPLOYMENT_NAME`) 확인
- [ ] AI Search 인덱스 생성 완료 (`upload_to_search.py --create-indexes`)
- [ ] 임베딩 업로드 완료 (`upload_to_search.py`)
- [ ] 헬스체크 엔드포인트 응답 확인 (`/health`)
- [ ] 프론트엔드 `EXPO_PUBLIC_API_URL`이 배포 백엔드 가리키는지 확인
- [ ] CORS preflight 테스트 (OPTIONS 요청)
- [ ] 로깅 설정 (프로덕션 레벨)

---

## 🧪 6. 배포 후 스모크 테스트

```bash
# 백엔드
BACKEND=https://movewise.onrender.com
curl "$BACKEND/health"
curl "$BACKEND/"

curl -X POST "$BACKEND/checklist" \
  -H "Content-Type: application/json" \
  -d '{
    "household":"자취",
    "contract":"월세",
    "region":"경기도 성남시 분당구",
    "move_date":"2026-05-01",
    "has_pet":true,
    "has_car":false,
    "has_children":false
  }'

# 프론트엔드
FRONT=https://movewise.vercel.app
curl -sI "$FRONT/" | head -5
```

---

## 📊 7. 권장 구성 (팀 발표용)

```
┌─────────────────────────────────────────────────────────┐
│ 팀원/시연자 (브라우저·모바일)                             │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Expo 웹 (Vercel / Cloudflare Pages)                     │
│ https://movewise.vercel.app                             │
└────────────────────┬────────────────────────────────────┘
                     │ EXPO_PUBLIC_API_URL=...
                     ▼
┌─────────────────────────────────────────────────────────┐
│ FastAPI (Azure App Service 또는 Render)                 │
│ https://movewise-api.azurewebsites.net                  │
└──────────────────┬──────────────────────────────────────┘
                   │
          ┌────────┴─────────┐
          ▼                  ▼
   Azure OpenAI        Azure AI Search
   Document Intel      (Index A + B)
   Blob Storage
```

---

## 🏁 8. 5분 퀵 런처

가장 빠르게 "앱 링크" 만들기 (발표 직전용):

```bash
# T1: 백엔드
cd 2차프로젝트
python3 -m uvicorn backend.app.main:app --port 8765 &

# T2: 백엔드 터널
cloudflared tunnel --url http://127.0.0.1:8765
#  → https://xxx.trycloudflare.com 복사

# T3: 프론트엔드
cd frontend/movewise-app
EXPO_PUBLIC_API_URL=https://xxx.trycloudflare.com \
  npx expo start --web --port 19006 &

# T4: 프론트엔드 터널
cloudflared tunnel --url http://127.0.0.1:19006
#  → 이 URL을 팀원에게 공유
```

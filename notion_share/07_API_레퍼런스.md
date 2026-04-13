# 07. API 레퍼런스

**Base URL (로컬)** `http://127.0.0.1:8765`
**Base URL (공유)** `https://habitat-surrounded-websites-accessible.trycloudflare.com` *(임시)*
**Swagger UI** `/docs`

---

## `GET /`

서비스 상태 및 Azure 연결 여부 확인.

**응답**
```json
{
  "service": "MoveWise",
  "version": "0.1.0",
  "azure_ready": false,
  "endpoints": ["/checklist", "/safecontract"]
}
```

---

## `GET /health`

헬스체크 엔드포인트 (App Service 배포용).

**응답**
```json
{ "status": "ok" }
```

---

## `POST /checklist`

사용자 조건에 맞춘 개인화 이사 체크리스트 생성.

### 요청

```json
{
  "household": "자취",
  "contract": "월세",
  "region": "경기도 성남시 분당구",
  "move_date": "2026-05-01",
  "has_pet": true,
  "has_car": false,
  "car_count": 1,
  "has_children": false,
  "children_count": 0,
  "children_school_level": null,
  "is_foreigner": false,
  "deposit_krw": null,
  "monthly_rent_krw": null,
  "special_concerns": []
}
```

### 요청 필드

| 필드 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `household` | `"자취"` \| `"신혼"` \| `"가족"` | 필수 | 세대 유형 |
| `contract` | `"전세"` \| `"월세"` \| `"자가"` | 필수 | 계약 유형 |
| `region` | string | 필수 | 시/도 · 시/군/구 (예: "경기도 성남시 분당구") |
| `move_date` | string `YYYY-MM-DD` | 필수 | 이사 예정일 |
| `has_pet` | bool | false | 반려동물 보유 |
| `has_car` | bool | false | 자동차 보유 |
| `car_count` | int | 1 | 자동차 대수 |
| `has_children` | bool | false | 자녀 여부 |
| `children_count` | int | 0 | 자녀 수 |
| `children_school_level` | `"초등"` \| `"중등"` \| `"고등"` \| null | null | 자녀 학교급 |
| `is_foreigner` | bool | false | 외국인 여부 |
| `deposit_krw` | int? | null | 보증금(원) |
| `monthly_rent_krw` | int? | null | 월세(원) — 전월세신고제 트리거 |
| `special_concerns` | string[] | [] | "보증금 반환 우려", "월세 인상", "하자" 등 |

### 응답

```json
{
  "request": { /* 원본 요청 echo */ },
  "generated_at": "2026-04-13",
  "total_items": 9,
  "used_queries": [
    "전입신고 방법",
    "확정일자 월세",
    "전기 명의변환",
    "수도 명의변환 경기도 성남시 분당구",
    "도시가스 명의변환 경기도 성남시 분당구",
    "인터넷 이전 설치",
    "우편물 주소이전",
    "반려동물 등록 주소변경"
  ],
  "warning": "Azure 자격 증명이 설정되지 않아 rule-based fallback 결과입니다.",
  "items": [
    {
      "category": "전입신고",
      "title": "전입신고",
      "description": "이사한 날부터 14일 이내에 정부24 또는 주민센터에서 전입신고를 해야 합니다.",
      "d_day_offset": 1,
      "start_date": "2026-05-04",
      "has_legal_deadline": true,
      "deadline_date": "2026-05-15",
      "deadline_days": 14,
      "penalty": "5만원 이하 과태료",
      "method": "정부24 온라인 또는 주민센터 방문",
      "contact": null,
      "region_hint": null,
      "citations": [
        { "law_name": "주민등록법", "article": "제16조", "source_url": null }
      ]
    }
  ]
}
```

### 응답 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `request` | object | 원본 요청 echo |
| `generated_at` | date | 생성 일자 |
| `total_items` | int | 체크리스트 항목 수 |
| `used_queries` | string[] | LLM이 생성한 AI Search 쿼리 (재현성 확인용) |
| `items[]` | object | 체크리스트 항목 배열 |
| `items[].d_day_offset` | int | 이사일 기준 시작일 (정수, 음수=이사 전) |
| `items[].start_date` | date | 공휴일 밀림 반영된 실제 시작일 |
| `items[].has_legal_deadline` | bool | 법정 기한 여부 |
| `items[].deadline_date` | date? | 법정 기한 마감일 |
| `items[].citations[]` | object | 법 조항 인용 |
| `warning` | string? | 폴백 모드 알림 등 |

---

## `POST /safecontract`

등기부등본 텍스트를 분석하여 위험 요소와 기존 서비스 안내를 생성.

### 요청

```json
{
  "text": "[갑구]\n1. 2020.05.12 소유권이전 김철수\n2. 2024.11.02 임의경매개시결정\n\n[을구]\n1. 2021.03.05 근저당권설정 채권최고액 금 2억4천만원 주식회사 하나은행\n2. 2023.08.10 가압류 금 5천만원 홍길동",
  "deposit_krw": 100000000,
  "expected_market_price_krw": 300000000
}
```

### 응답

```json
{
  "extraction": {
    "owner_change_within_2_years": 0,
    "mortgage_total_krw": 166033200,
    "mortgage_claim_amount_krw": 200040000,
    "seizure_count": 1,
    "seizure_total_krw": 0,
    "trust_registration": false,
    "auction_in_progress": true,
    "raw_notes": []
  },
  "jeontse_ratio": 0.887,
  "summary": "🟡 부채비율 주의",
  "risks": [
    {
      "severity": "yellow",
      "label": "부채비율 89%",
      "explanation_plain": "안전 범위를 약간 벗어났습니다. HUG 보증보험 가입 여부를 확인해보세요.",
      "related_laws": []
    },
    {
      "severity": "red",
      "label": "가압류 1건",
      "explanation_plain": "가압류는 채권자가 집주인 재산을 묶어둔 것입니다. ...",
      "related_laws": []
    },
    {
      "severity": "red",
      "label": "임의경매 진행 중",
      "explanation_plain": "이 주택은 경매가 개시되었습니다. 계약하면 안 됩니다.",
      "related_laws": []
    }
  ],
  "referrals": [
    {
      "icon": "🏛️",
      "name": "HUG 안심전세 앱",
      "url": "https://www.khug.or.kr",
      "description": "보증보험 가입 가능 여부 확인"
    },
    {
      "icon": "📋",
      "name": "인터넷등기소",
      "url": "https://www.iros.go.kr",
      "description": "등기부등본 원본 직접 열람 (700원)"
    },
    {
      "icon": "💰",
      "name": "국토교통부 실거래가",
      "url": "https://rt.molit.go.kr",
      "description": "주변 시세 비교"
    }
  ],
  "disclaimer": "이 서비스는 법률 자문이 아닌 참고용 사전 검토 도구입니다. 정확한 판단을 위해 전문가 상담을 권합니다."
}
```

### 응답 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `extraction` | object | 등기부에서 추출된 수치 |
| `jeontse_ratio` | float | (근저당 실부채 + 보증금) / 시세 |
| `summary` | string | 한 줄 요약 (이모지 + 상태) |
| `risks[]` | object | 위험 항목 배열 |
| `risks[].severity` | `"green"` \| `"yellow"` \| `"red"` | 위험도 |
| `risks[].explanation_plain` | string | 쉬운 말 설명 |
| `risks[].related_laws[]` | Citation[] | 관련 법 조항 |
| `referrals[]` | object | "다음에 확인하세요" 안내 카드 |
| `disclaimer` | string | 면책 고지 (항상 포함) |

---

## 📡 에러 응답

```json
{
  "detail": "text is required (PDF 업로드는 /safecontract/upload 참고)"
}
```

HTTP 상태 코드:
- `400` — 입력 검증 실패
- `500` — 서버 오류

---

## 🔧 cURL 예시

```bash
# Health
curl http://127.0.0.1:8765/

# Checklist
curl -X POST http://127.0.0.1:8765/checklist \
  -H "Content-Type: application/json" \
  -d '{
    "household": "자취",
    "contract": "월세",
    "region": "경기도 성남시 분당구",
    "move_date": "2026-05-01",
    "has_pet": true,
    "has_car": false,
    "has_children": false
  }'

# SafeContract
curl -X POST http://127.0.0.1:8765/safecontract \
  -H "Content-Type: application/json" \
  -d '{
    "text": "[을구] 근저당권설정 금 2억4천만원",
    "deposit_krw": 100000000,
    "expected_market_price_krw": 300000000
  }'
```

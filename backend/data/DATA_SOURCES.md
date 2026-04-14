# 이사이상무 데이터 출처 카탈로그

> 2026-04-14 기준 · 총 108 파일 (JSON) + jsonl 인덱스 3종

---

## 📌 한눈에 보기

| 카테고리 | 개수 | 주요 출처 |
|---|---|---|
| Golden Query 평가 시나리오 | 1 | 이사이상무 팀 |
| HUG 안심전세 / 임대인 공개 | 2 | 주택도시보증공사 (HUG) |
| 계약 해지·갱신 통지 템플릿 | 1 | 법무부 주택임대차 표준 양식 기반 |
| 공휴일 | 1 | 한국천문연구원 |
| 국민건강보험공단 | 1 | 국민건강보험공단 |
| 국민연금공단 | 1 | 국민연금공단 |
| 국세청 홈택스 주소변경 | 1 | 국세청 |
| 금융결제원 내계좌한눈에 | 1 | 금융결제원 (KFTC) |
| 대법원 인터넷등기소 | 1 | 대법원 / 법원행정처 |
| 대한법률구조공단 132 | 1 | 법무부 산하 공공기관 |
| 대형폐기물 배출 전국 | 1 | 환경부 · 각 시·군·구청 · 한국전자제품자원순환공제조합 |
| 도시가스 지역별 공급사 | 1 | 한국도시가스협회 |
| 반려동물 등록 주소변경 | 1 | 농림축산검역본부 · 동물보호관리시스템 |
| 법률 원본 | 10 | 법제처 |
| 법무부 표준 임대차계약서 | 1 | 법무부 / 국토교통부 |
| 병무청 주소변경 | 1 | 병무청 |
| 보증금 반환 분쟁 5단계 가이드 | 1 | 법무부 · 주택임대차분쟁조정위원회 · 대한법률구조공단 참고 |
| 서울시 전월세 정보몽땅 | 1 | 서울특별시 |
| 외국인 주소변경 | 1 | 법무부 출입국·외국인청 |
| 우편물 주소이전 서비스 | 1 | 우정사업본부 |
| 원상회복 기준 | 1 | 공정거래위원회 · 대법원 판례 · 한국소비자원 |
| 유튜브 자막 원본 | 12 | 각 채널 귀속 |
| 인터넷·TV 통신 3사 | 1 | KT, SK브로드밴드, LG U+ |
| 자녀 전학 | 1 | 교육부 · 시·도 교육청 |
| 자동차 변경등록 | 1 | 국토교통부 · 시·도청 |
| 장기수선충당금·관리비예치금 반환 | 1 | 국토교통부 |
| 전국 수도사업소 | 1 | 각 지자체 상수도사업본부 |
| 전기 (한전) | 1 | 한국전력공사 (KEPCO) |
| 전세피해지원센터 | 1 | 국토교통부 |
| 정부24 주요 민원 | 1 | 행정안전부 |
| 주택임대차분쟁조정위원회 | 1 | 법무부 / 대한법률구조공단 |
| 퇴거 타임라인 체크리스트 | 1 | 이사이상무 팀 편집본 |
| 품질 평가 결과 | 1 | 이사이상무 팀 (evaluate_checklist.py 실행) |
| 행정 절차 원본 스크랩 | 54 | 법제처 (찾기쉬운 생활법령정보) |

---

## 📦 RAG 인덱스 (JSONL, 별도 관리)

| 파일 | 카테고리 | 개수 | 출처 |
|---|---|---|---|
| `indexes/index_a_chunks.jsonl` | 법률 청크 | 1,950 | 국가법령정보 Open API |
| `indexes/index_b_chunks_curated.jsonl` | 행정 절차 청크 | 200 | 찾기쉬운 생활법령정보 |
| `indexes/index_c_youtube_chunks.jsonl` | 유튜브 자막 청크 | 147 | YouTube (12 영상) |

---

## 📄 파일별 상세

### 📁 `backend/data/indexes/`

**`indexes/evaluation_report.json`**

- **카테고리**: 품질 평가 결과
- **담당 기관**: 이사이상무 팀 (evaluate_checklist.py 실행)
- **출처 URL**: N/A
- **라이선스**: 프로젝트 소유
- **갱신 주기**: 자동 (평가 재실행 시)
- **수집 방법**: evaluate_checklist.py

**`indexes/golden_queries.json`**

- **카테고리**: Golden Query 평가 시나리오
- **담당 기관**: 이사이상무 팀
- **출처 URL**: 팀 자체 작성
- **라이선스**: 프로젝트 소유
- **갱신 주기**: 수동
- **수집 방법**: 팀 작성 30건


### 📁 `backend/data/laws/`

**`laws/공동주택관리법.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/동물보호법.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/민법.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/부동산등기법.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/주민등록법 시행령.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/주민등록법.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/주민등록법시행령.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/주택임대차보호법 시행령.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/주택임대차보호법.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)

**`laws/주택임대차보호법시행령.json`**

- **카테고리**: 법률 원본
- **담당 기관**: 법제처
- **출처 URL**: https://www.law.go.kr/DRF/lawService.do
- **API**: 국가법령정보 Open API (DRF)
- **라이선스**: 공공누리 제1유형 (출처 표시)
- **갱신 주기**: 시행일 기준 즉시 반영
- **수집 방법**: backend/scripts/ingest_laws.py (LAW_OC 인증키)


### 📁 `backend/data/mapping/`

**`mapping/animal_registration.json`**

- **카테고리**: 반려동물 등록 주소변경
- **담당 기관**: 농림축산검역본부 · 동물보호관리시스템
- **출처 URL**: https://www.animal.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services.py

**`mapping/car_registration.json`**

- **카테고리**: 자동차 변경등록
- **담당 기관**: 국토교통부 · 시·도청
- **출처 URL**: https://www.gov.kr, 각 시·도청
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services.py

**`mapping/foreigner_registration.json`**

- **카테고리**: 외국인 주소변경
- **담당 기관**: 법무부 출입국·외국인청
- **출처 URL**: https://www.hikorea.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services.py

**`mapping/gas_region_company.json`**

- **카테고리**: 도시가스 지역별 공급사
- **담당 기관**: 한국도시가스협회
- **출처 URL**: http://www.citygas.or.kr/company/situation.jsp
- **라이선스**: 공개 페이지 기반 재가공
- **갱신 주기**: 연 1회
- **수집 방법**: ingest_citygas.py (34 회사 · 전국)

**`mapping/gov24_services.json`**

- **카테고리**: 정부24 주요 민원
- **담당 기관**: 행정안전부
- **출처 URL**: https://www.gov.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services.py

**`mapping/hometax_nts.json`**

- **카테고리**: 국세청 홈택스 주소변경
- **담당 기관**: 국세청
- **출처 URL**: https://hometax.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/hug_ansim_jeonse.json`**

- **카테고리**: HUG 안심전세 / 임대인 공개
- **담당 기관**: 주택도시보증공사 (HUG)
- **출처 URL**: https://www.khug.or.kr, https://jeonse.khug.or.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/hug_default_list.json`**

- **카테고리**: HUG 안심전세 / 임대인 공개
- **담당 기관**: 주택도시보증공사 (HUG)
- **출처 URL**: https://www.khug.or.kr, https://jeonse.khug.or.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/iros_registry.json`**

- **카테고리**: 대법원 인터넷등기소
- **담당 기관**: 대법원 / 법원행정처
- **출처 URL**: https://www.iros.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/jeonse_victim_support.json`**

- **카테고리**: 전세피해지원센터
- **담당 기관**: 국토교통부
- **출처 URL**: https://jeonse119.molit.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/kepco_electricity.json`**

- **카테고리**: 전기 (한전)
- **담당 기관**: 한국전력공사 (KEPCO)
- **출처 URL**: https://www.kepco.co.kr, https://cyber.kepco.co.kr
- **라이선스**: 공개 페이지
- **갱신 주기**: 수동
- **수집 방법**: ingest_services.py (123 + 13 지역본부)

**`mapping/kftc_accounts.json`**

- **카테고리**: 금융결제원 내계좌한눈에
- **담당 기관**: 금융결제원 (KFTC)
- **출처 URL**: https://www.payinfo.or.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/lease_dispute_committee.json`**

- **카테고리**: 주택임대차분쟁조정위원회
- **담당 기관**: 법무부 / 대한법률구조공단
- **출처 URL**: https://www.hldcc.or.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/legal_aid_132.json`**

- **카테고리**: 대한법률구조공단 132
- **담당 기관**: 법무부 산하 공공기관
- **출처 URL**: https://www.klac.or.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/mma_military.json`**

- **카테고리**: 병무청 주소변경
- **담당 기관**: 병무청
- **출처 URL**: https://www.mma.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/moj_standard_contract.json`**

- **카테고리**: 법무부 표준 임대차계약서
- **담당 기관**: 법무부 / 국토교통부
- **출처 URL**: https://www.moj.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/moveout_deposit_return.json`**

- **카테고리**: 보증금 반환 분쟁 5단계 가이드
- **담당 기관**: 법무부 · 주택임대차분쟁조정위원회 · 대한법률구조공단 참고
- **출처 URL**: https://www.hldcc.or.kr, https://www.klac.or.kr
- **라이선스**: 원본 법률은 공공누리, 편집본은 프로젝트 소유
- **갱신 주기**: 수동
- **수집 방법**: ingest_moveout.py
- **참고 법령**: 주택임대차보호법 제3조의2/3, 제4조, 제14조

**`mapping/moveout_management_refund.json`**

- **카테고리**: 장기수선충당금·관리비예치금 반환
- **담당 기관**: 국토교통부
- **출처 URL**: 공동주택관리법 (국가법령정보)
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_moveout.py
- **참고 법령**: 공동주택관리법 제24조, 제30조

**`mapping/moveout_restoration.json`**

- **카테고리**: 원상회복 기준
- **담당 기관**: 공정거래위원회 · 대법원 판례 · 한국소비자원
- **출처 URL**: 공정위 소비자분쟁해결기준
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_moveout.py
- **참고 법령**: 민법 제615조, 제623조, 공정위 소비자분쟁해결기준 주거생활

**`mapping/moveout_termination_notice.json`**

- **카테고리**: 계약 해지·갱신 통지 템플릿
- **담당 기관**: 법무부 주택임대차 표준 양식 기반
- **출처 URL**: https://www.moj.go.kr
- **라이선스**: 표준 양식 재배포 가능
- **갱신 주기**: 수동
- **수집 방법**: ingest_moveout.py
- **참고 법령**: 주택임대차보호법 제6조, 제6조의2, 제6조의3

**`mapping/moveout_timeline.json`**

- **카테고리**: 퇴거 타임라인 체크리스트
- **담당 기관**: 이사이상무 팀 편집본
- **출처 URL**: 기반: 주택임대차보호법 + 공정위 분쟁해결기준 + 실무 사례
- **라이선스**: 원본 법률·가이드는 공공누리, 편집본은 프로젝트 소유
- **갱신 주기**: 수동
- **수집 방법**: ingest_moveout.py (D-60~D+7)
- **참고 법령**: 주택임대차보호법 제3조의2/3, 제4조, 제6조~제6조의3, 공정거래위원회 소비자분쟁해결기준 2025 (주거생활), 한국소비자원 주거 가이드

**`mapping/moveout_waste_disposal.json`**

- **카테고리**: 대형폐기물 배출 전국
- **담당 기관**: 환경부 · 각 시·군·구청 · 한국전자제품자원순환공제조합
- **출처 URL**: 각 지자체 폐기물 시스템 + https://15990903.or.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_moveout.py

**`mapping/nhis_health_insurance.json`**

- **카테고리**: 국민건강보험공단
- **담당 기관**: 국민건강보험공단
- **출처 URL**: https://www.nhis.or.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/nps_national_pension.json`**

- **카테고리**: 국민연금공단
- **담당 기관**: 국민연금공단
- **출처 URL**: https://www.nps.or.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/post_office_mail_forwarding.json`**

- **카테고리**: 우편물 주소이전 서비스
- **담당 기관**: 우정사업본부
- **출처 URL**: https://service.epost.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services.py

**`mapping/school_transfer.json`**

- **카테고리**: 자녀 전학
- **담당 기관**: 교육부 · 시·도 교육청
- **출처 URL**: https://www.moe.go.kr + 각 교육청
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services.py (17 교육청)

**`mapping/seoul_realty_check.json`**

- **카테고리**: 서울시 전월세 정보몽땅
- **담당 기관**: 서울특별시
- **출처 URL**: https://rent.seoul.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_services_v2.py

**`mapping/telecom_internet.json`**

- **카테고리**: 인터넷·TV 통신 3사
- **담당 기관**: KT, SK브로드밴드, LG U+
- **출처 URL**: 각 사 공식 홈페이지
- **라이선스**: 공개 페이지
- **갱신 주기**: 수동
- **수집 방법**: ingest_services.py

**`mapping/water_region_office.json`**

- **카테고리**: 전국 수도사업소
- **담당 기관**: 각 지자체 상수도사업본부
- **출처 URL**: 각 지자체 공식 홈페이지
- **라이선스**: 공공누리 제1유형 (공개 정보)
- **갱신 주기**: 수동 (6개월~1년)
- **수집 방법**: ingest_water.py (17 광역 · 63 산하 사업소)


### 📁 `backend/data/procedures/`

**`procedures/easylaw/_summary.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-1-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-1-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-2-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-2-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-2-2-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-2-2-3.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-2-2-4.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-2-2-5.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-2-3-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-2-3-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-3-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-3-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-1-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-2-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-3-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-3-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-3-3.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-3-4.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-4-4-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-2-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-2-3.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-2-4.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-2-5.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-2-6.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-3-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-3-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-629-5-3-3.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-1-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-1-1-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-1-1-3.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-1-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-1-3-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-1-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-1-3.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-2-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-2-3.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-2-4.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-2-5.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-3-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-2-3-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-3-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-3-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-3-2-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-3-3-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-3-3-2.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-4-1-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)

**`procedures/easylaw/easylaw-666-4-2-1.json`**

- **카테고리**: 행정 절차 원본 스크랩
- **담당 기관**: 법제처 (찾기쉬운 생활법령정보)
- **출처 URL**: https://easylaw.go.kr
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 수동
- **수집 방법**: ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)


### 📁 `backend/data/raw/`

**`raw/youtube_transcripts/4i-e1OmEGCQ.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/BtbnY7enQMQ.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/Ej8MDFj37zg.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/Gpf8slBLVe4.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/MIEObuovrSc.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/OCtjQJqtYyc.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/PamLLxiCPqo.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/aw-cvULahyA.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/dFCz_ONk86o.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/gkeglF2m_WA.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/holidays_2026.json`**

- **카테고리**: 공휴일
- **담당 기관**: 한국천문연구원
- **출처 URL**: http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService
- **API**: 특일정보 API
- **라이선스**: 공공누리 제1유형
- **갱신 주기**: 연 1회 (연말)
- **수집 방법**: ingest_holidays.py (2026년 22건)

**`raw/youtube_transcripts/iY3d1JAQsKY.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py

**`raw/youtube_transcripts/oYt9Xv3d2Wo.json`**

- **카테고리**: 유튜브 자막 원본
- **담당 기관**: 각 채널 귀속
- **출처 URL**: https://www.youtube.com
- **API**: youtube-transcript-api (무료)
- **라이선스**: 영상별 채널 저작권. 프로젝트 내부용 가공만 허용
- **갱신 주기**: 수동
- **수집 방법**: ingest_youtube.py


---

## ⚖️ 라이선스 정리

- **공공누리 제1유형** — 출처 표시 조건으로 자유 이용, 재배포, 상업적 이용 가능
  - 법률, 행정 절차, 공휴일, 지자체 정보, 정부 산하 기관
- **영상별 채널 귀속** — 유튜브 자막 원본
  - 프로젝트 내부용 가공·분석만 허용
  - 발표 시 요약·캡처만 인용, 원본 영상 재배포 금지
- **프로젝트 소유** — 팀 자체 작성물
  - Golden Query, 평가 리포트, 퇴거 타임라인 편집본

---

## 🔄 갱신 방법

각 데이터는 `backend/scripts/ingest_*.py` 를 재실행해서 갱신:

```bash
# 법률 (LAW_OC 필요)
python3 backend/scripts/ingest_laws.py

# 행정 절차 (법제처)
python3 backend/scripts/ingest_easylaw.py
python3 backend/scripts/chunk_easylaw.py
python3 backend/scripts/curate_chunks.py

# 매핑 (수도·전기·통신·정부24·HUG·퇴거 등)
python3 backend/scripts/ingest_water.py
python3 backend/scripts/ingest_services.py
python3 backend/scripts/ingest_services_v2.py
python3 backend/scripts/ingest_moveout.py

# 공휴일 · 유튜브 · 도시가스
python3 backend/scripts/ingest_holidays.py
python3 backend/scripts/ingest_youtube.py
python3 backend/scripts/ingest_citygas.py

# 메타데이터 재주입 (이 문서 포함)
python3 backend/scripts/annotate_sources.py
```

---

## 📞 문의

출처 확인·라이선스 검토·갱신 제안은 팀 채널로 연락.

*생성일: 2026-04-14*

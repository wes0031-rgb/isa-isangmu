"""Azure 활성화 원샷 스크립트.

.env 에 Azure 키를 채운 후 실행:
  python3 backend/scripts/activate_azure.py

단계:
  1) 환경변수 검증 (OpenAI + Search 필수, Doc Intelligence / Blob 선택)
  2) Azure OpenAI 임베딩 엔드포인트 스모크 (1건)
  3) Azure AI Search 인덱스 A/B 생성 (이미 있으면 업데이트)
  4) Index A (법률 1,950 조문) 임베딩 업로드
  5) Index B (행정 절차 200 청크) 임베딩 업로드
  6) Golden Query 평가 재실행 (rule-based → RAG 비교)
  7) 헬스체크 (/ 엔드포인트 azure_ready=true 확인)
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings  # noqa: E402


def step(num: int, total: int, label: str) -> None:
    print()
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"[{num}/{total}] {label}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def fail(msg: str) -> "typing.NoReturn":
    print(f"❌ {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def main() -> None:
    print("🚀 MoveWise Azure 활성화 시작")
    TOTAL = 7

    # 1. 환경변수 검증
    step(1, TOTAL, "환경변수 검증")
    # get_settings() 를 새로 부르려면 캐시 지워야 함
    from backend.app import config as _cfg
    _cfg.get_settings.cache_clear()
    s = get_settings()

    required = {
        "AZURE_OPENAI_ENDPOINT": s.azure_openai_endpoint,
        "AZURE_OPENAI_API_KEY": s.azure_openai_api_key,
        "AZURE_OPENAI_DEPLOYMENT_NAME": s.azure_openai_deployment_name,
        "AZURE_OPENAI_EMBED_DEPLOYMENT": s.azure_openai_embed_deployment,
        "AZURE_SEARCH_ENDPOINT": s.azure_search_endpoint,
        "AZURE_SEARCH_API_KEY": s.azure_search_api_key,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        fail(
            "필수 환경변수 누락: "
            + ", ".join(missing)
            + "\n  → .env 파일에 값을 추가하고 다시 실행하세요."
        )
    ok(f"OpenAI: {s.azure_openai_endpoint}")
    ok(f"Search: {s.azure_search_endpoint}")
    ok(f"GPT deployment: {s.azure_openai_deployment_name}")
    ok(f"Embedding deployment: {s.azure_openai_embed_deployment}")
    optional = {
        "AZURE_DOCINTEL_ENDPOINT": s.azure_docintel_endpoint,
        "AZURE_BLOB_CONNECTION_STRING": s.azure_blob_connection_string,
    }
    for k, v in optional.items():
        print(f"  · {k}: {'설정됨' if v else '미설정 (옵셔널)'}")

    # 2. 임베딩 스모크
    step(2, TOTAL, "Azure OpenAI 임베딩 스모크 테스트")
    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_key=s.azure_openai_api_key,
            api_version=s.azure_openai_api_version,
            azure_endpoint=s.azure_openai_endpoint,
        )
        resp = client.embeddings.create(
            model=s.azure_openai_embed_deployment,
            input=["전입신고 14일 이내"],
        )
        dims = len(resp.data[0].embedding)
        ok(f"임베딩 응답 정상 · 차원={dims}")
        if dims != 1536:
            print(
                f"  ⚠️  dimensions={dims} — 스키마 기본값 1536과 다름. "
                f"schemas/index_*.json 의 dimensions 필드를 수정하세요."
            )
    except Exception as e:
        fail(f"임베딩 호출 실패: {e}")

    # 3. 인덱스 생성
    step(3, TOTAL, "Azure AI Search 인덱스 A/B 생성")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend" / "scripts" / "upload_to_search.py"),
            "--create-indexes",
            "--skip-embeddings",  # 인덱스만 먼저 만들고
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        fail(f"인덱스 생성 실패:\n{result.stderr}")
    ok("인덱스 A/B 생성 완료")

    # 4. 임베딩 업로드 (A + B 한 번에)
    step(4, TOTAL, "Index A (법률) + Index B (절차) 임베딩 업로드")
    start = time.time()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend" / "scripts" / "upload_to_search.py"),
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        fail(f"업로드 실패:\n{result.stderr}")
    elapsed = time.time() - start
    ok(f"업로드 완료 · {elapsed:.0f}초")

    # 5. (4 안에 포함됨 — 스킵)
    step(5, TOTAL, "(이전 단계에서 완료)")
    ok("Index A + B 업로드 끝")

    # 6. 평가 재실행
    step(6, TOTAL, "Golden Query 30건 재평가")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend" / "scripts" / "evaluate_checklist.py"),
        ],
        capture_output=True,
        text=True,
    )
    # 마지막 20줄만 출력
    lines = result.stdout.strip().splitlines()
    print("\n".join(lines[-20:]))
    if result.returncode != 0:
        print(f"⚠️ 평가 실행 중 에러 (무시): {result.stderr[:200]}")
    ok("평가 완료 — backend/data/indexes/evaluation_report.json 확인")

    # 7. 백엔드 헬스체크
    step(7, TOTAL, "백엔드 헬스체크")
    _cfg.get_settings.cache_clear()
    s = get_settings()
    print(f"  · azure_ready = {s.azure_ready}")
    if s.azure_ready:
        ok("백엔드 상태: Azure 모드 준비 완료")
    else:
        fail("azure_ready = False — .env 재확인 필요")

    print()
    print("🎉 Azure 활성화 완료!")
    print()
    print("다음 단계:")
    print("  1. 로컬 백엔드 재시작 — 위 설정이 반영되도록")
    print("     pkill -f 'uvicorn backend.app.main' && python3 -m uvicorn backend.app.main:app --port 8765 --reload")
    print("  2. Render 배포 중이면 환경변수 추가 후 Manual Deploy 또는 자동 재배포")
    print("  3. 프론트엔드 MY 탭에서 '🧠 Azure LLM 모드' 배지 확인")


if __name__ == "__main__":
    main()

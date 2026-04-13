"""Pytest 공통 설정 — backend 모듈 import 가능하도록 PYTHONPATH 추가."""
from __future__ import annotations

import sys
from pathlib import Path

# backend/ 를 sys.path 에 추가하여 `from app...` 대신
# 프로젝트 루트에서 `from backend.app...` 형태로 import 가능하게 만든다.
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

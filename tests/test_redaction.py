"""수집기 3종의 서비스키 마스킹 검증.

공개 준비(2026-08-16)에서 세 러너의 마스킹이 서로 다르게 잘못돼 있던 것을 고쳤다.
`docs/PROVENANCE.md` 참조. 같은 결함이 다시 들어오는 것을 막기 위한 회귀 테스트다.

정규식 마스킹은 조용히 실패한다. 이스케이프가 한 단계 어긋나면 치환 결과가
리터럴 `\\1***` 이 되고 키 뒷부분이 그대로 남는데, 눈으로 읽어서는 통과한다.
그래서 읽지 않고 실행해서 확인한다.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SECRET = "AbC123secretKEYvalue999xyz"
COLLECTORS = {
    "kma_crop_detail": "src/kma_crop_detail/collect.py",
    "rda_basic_daily": "src/rda_basic_daily/collect.py",
    "rda_crop_daily": "src/rda_crop_daily/collect.py",
}


def _load(name: str, relpath: str):
    """네트워크 의존 모듈을 스텁으로 대체하고 수집기를 import 한다."""
    for mod_name, attrs in (
        ("dotenv", {"load_dotenv": lambda *a, **k: None}),
        ("requests", {"get": None, "exceptions": types.SimpleNamespace()}),
    ):
        sys.modules.setdefault(mod_name, types.ModuleType(mod_name))
        for key, value in attrs.items():
            setattr(sys.modules[mod_name], key, value)

    spec = importlib.util.spec_from_file_location(f"_collector_{name}", ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=sorted(COLLECTORS), ids=sorted(COLLECTORS))
def collector(request):
    return _load(request.param, COLLECTORS[request.param])


def test_sanitize_error_masks_key_in_url(collector):
    message = f"HTTPError: https://apis.data.go.kr/x?serviceKey={SECRET}&pageNo=1"

    masked = collector.sanitize_error(message)

    assert SECRET not in masked
    assert "AbC123" not in masked
    assert "serviceKey=***" in masked
    # 리터럴 백슬래시가 남으면 치환이 그룹 참조로 동작하지 않은 것이다.
    assert "\\1" not in masked


def test_sanitize_error_is_case_insensitive(collector):
    for variant in ("serviceKey", "ServiceKey", "SERVICEKEY", "servicekey"):
        masked = collector.sanitize_error(f"url?{variant}={SECRET}&page=1")
        assert SECRET not in masked, variant


def test_sanitize_error_keeps_following_params(collector):
    masked = collector.sanitize_error(f"url?serviceKey={SECRET}&pageNo=7&rows=40")

    assert "pageNo=7" in masked
    assert "rows=40" in masked


def test_sanitize_error_passes_through_empty(collector):
    assert collector.sanitize_error("") == ""
    assert collector.sanitize_error("no key here") == "no key here"


def test_sanitize_params_masks_key_field(collector):
    params = {"serviceKey": SECRET, "Page_No": 1, "Page_Size": 40}

    safe = collector.sanitize_params(params)

    assert safe["serviceKey"] == "***"
    assert safe["Page_No"] == 1
    assert safe["Page_Size"] == 40
    assert SECRET not in str(safe)


def test_sanitize_params_does_not_mutate_input(collector):
    params = {"serviceKey": SECRET}

    collector.sanitize_params(params)

    assert params["serviceKey"] == SECRET

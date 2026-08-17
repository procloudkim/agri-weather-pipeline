#!/usr/bin/env python3
"""공개 트리 스캐너. 저장소에 나가면 안 되는 것이 남아 있는지 검사한다.

CI 에서 매 커밋 실행된다. 발행 시점에 한 번 훑는 것으로는 부족하고,
나중에 추가되는 파일도 같은 기준을 통과해야 하기 때문이다.

## 왜 어떤 규칙은 해시로 되어 있나

초기 판에는 팀원 실명, 계정 버킷명, 종료된 도메인이 정규식 리터럴로 들어 있었다.
그 상태로 발행하면 **스캐너 자신이 유출 경로가 된다.** 검사기를 자기 제외 처리해
검사를 통과시켰을 뿐, 파일을 열면 그 문자열이 그대로 보인다.

그래서 민감 리터럴은 SHA-256 앞 16자리로만 보관하고, 검사할 때 문서에서 뽑은
토큰을 해시해 대조한다. 스캐너는 무엇을 찾는지 알지만 그것이 무엇인지 말하지
않는다.

사용:
    python scripts/check_public_tree.py [경로]
종료 코드:
    0 통과, 1 위반 발견
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules"}
SKIP_SUFFIXES = {
    ".parquet", ".png", ".jpg", ".jpeg", ".gif", ".pdf",
    ".zip", ".xlsx", ".pptx", ".docx", ".db", ".sqlite3",
}

# 리터럴로 적어도 무해한 규칙. 형식만 기술하며 실제 값을 담지 않는다.
CONTENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws-access-key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("service-key-in-url", re.compile(r"(?i)servicekey=[A-Za-z0-9%+/=]{16,}")),
    ("windows-user-path", re.compile(r"[A-Za-z]:\\\\?Users\\\\?")),
    ("korean-resident-number", re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")),
    ("mobile-number", re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b")),
    # 수집한 제3자 데이터가 문서로 새는 경로를 막는다.
    #
    # 데이터 파일을 전부 제외했는데도 내부 작업 문서 한 건에 댓글 원문과
    # 작성자 핸들이 표 형태로 박혀 있었다. 데이터 계층만 막으면 놓친다.
    ("youtube-author-handle", re.compile(r"@(?:user-[a-z0-9]{6,}|[가-힣][가-힣0-9]{2,})")),
    ("youtube-comment-id", re.compile(r"\bUg[A-Za-z0-9_-]{20,}\b")),
    ("comment-dump-row", re.compile(r"^[A-Za-z0-9_-]{11},[^\n]{5,},Ug[A-Za-z0-9_-]{10,}", re.MULTILINE)),
]

# 민감 리터럴의 SHA-256 앞 16자리.
#
# 값 자체를 담지 않는다. 길이는 토큰 후보를 좁히는 데만 쓴다.
HASHED_RULES: dict[str, set[str]] = {
    # 팀원 실명 3자
    "teammate-real-name": {
        "2ab56950adafcb0e",
        "3da7ffe335dd4bdf",
        "0da6f7ae0f54eb50",
        "649ccc1d38b3eefc",
    },
    # 계정 식별자와 종료된 도메인
    "account-or-dead-host": {
        "e6b360889b37ffaa",
        "614246b4a3eed780",
        "99682fcc57f7edcf",
    },
}

# 해시 대조 대상 토큰의 길이. 이 길이만 잘라서 해시한다.
HANGUL_TOKEN_LENGTHS = (3,)
ASCII_TOKEN_LENGTHS = (9, 16, 18)

HANGUL_RUN = re.compile(r"[가-힣]{2,}")
ASCII_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{5,}")

FORBIDDEN_SUFFIXES = {".pem", ".key", ".ppk", ".pfx", ".p12", ".jks"}
FORBIDDEN_NAMES = {".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials"}

SELF = Path(__file__).name


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _hashed_hits(text: str) -> list[tuple[str, int]]:
    """민감 리터럴을 해시로 대조한다. 찾은 규칙 이름과 위치를 돌려준다."""
    hits: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    def probe(run: str, start: int, lengths: tuple[int, ...]) -> None:
        for length in lengths:
            for offset in range(0, max(len(run) - length + 1, 0)):
                token = run[offset : offset + length]
                token_hash = _digest(token)
                for rule, digests in HASHED_RULES.items():
                    if token_hash in digests:
                        position = start + offset
                        if (rule, position) not in seen:
                            seen.add((rule, position))
                            hits.append((rule, position))

    for match in HANGUL_RUN.finditer(text):
        probe(match.group(), match.start(), HANGUL_TOKEN_LENGTHS)
    for match in ASCII_RUN.finditer(text):
        probe(match.group(), match.start(), ASCII_TOKEN_LENGTHS)

    return hits


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def scan(root: Path) -> list[str]:
    findings: list[str] = []

    for path in iter_files(root):
        rel = path.relative_to(root)

        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"{rel}: forbidden-file-type ({path.suffix})")
            continue
        if path.name in FORBIDDEN_NAMES:
            findings.append(f"{rel}: forbidden-file-name ({path.name})")
            continue

        if path.suffix.lower() in SKIP_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        # 스캐너 자신은 규칙 형식을 담으므로 정규식 검사에서만 제외한다.
        # 해시 검사는 그대로 받는다. 리터럴이 다시 들어오면 여기서 걸린다.
        if path.name != SELF:
            for name, pattern in CONTENT_RULES:
                match = pattern.search(text)
                if match:
                    line = text[: match.start()].count("\n") + 1
                    findings.append(f"{rel}:{line}: {name}")

        for rule, position in _hashed_hits(text):
            line = text[:position].count("\n") + 1
            findings.append(f"{rel}:{line}: {rule}")

    return findings


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    findings = scan(root)

    if findings:
        print(f"PUBLIC_TREE_FAIL  위반 {len(findings)}건")
        for item in findings:
            print(f"  {item}")
        return 1

    print("PUBLIC_TREE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

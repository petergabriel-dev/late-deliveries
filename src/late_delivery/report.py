"""Traceable Markdown reports from analysis JSON and assumptions (ADR-0015)."""

import json
from pathlib import Path
import re
import tomllib
from urllib.parse import unquote, urlsplit

from late_delivery import config as C
from late_delivery.diagnostics import rounded


def derived(sources: dict) -> dict:
    """Sole home for report arithmetic and exact-match list selections."""
    return {}


def load_sources(outputs_dir: Path | None = None, assumptions_path: Path | None = None) -> dict:
    outputs_dir = C.OUTPUTS_DIR if outputs_dir is None else outputs_dir
    assumptions_path = C.ASSUMPTIONS_TOML if assumptions_path is None else assumptions_path
    sources = {p.stem: json.loads(p.read_text(encoding="utf-8"))
               for p in sorted(outputs_dir.glob("*.json")) if p.stem != "report"}
    with assumptions_path.open("rb") as f:
        sources["assumptions"] = tomllib.load(f)
    sources["report"] = rounded(derived(sources))
    return sources


def one(rows: list[dict], **match) -> dict:
    matches = [row for row in rows if all(key in row and row[key] == value for key, value in match.items())]
    if len(matches) != 1:
        raise ValueError(f"one({match!r}): expected exactly one row, found {len(matches)}")
    return matches[0]


def resolve(placeholder: str, sources: dict) -> str:
    """Resolve a complete {source:dot.path[:fmt]} token, never evaluating code."""
    m = re.fullmatch(r"\{([A-Za-z_]\w*):([^{}:]+)(?::([^{}]*))?\}", placeholder)
    if m is None:
        raise ValueError(f"{placeholder}: invalid placeholder")
    source, path, spec = m.groups()
    if source not in sources:
        raise ValueError(f"{placeholder}: unknown source {source!r}")
    value = sources[source]
    for key in path.split("."):
        if not isinstance(value, dict):
            raise ValueError(f"{placeholder}: dictionary-only traversal; use one() for list values")
        if not key or key not in value:
            raise ValueError(f"{placeholder}: missing key {key!r}")
        value = value[key]
    if isinstance(value, list):
        raise ValueError(f"{placeholder}: use one() for list values")
    try:
        return format(value, spec or "")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{placeholder}: invalid format {spec!r}: {exc}") from exc


def word_count(text: str) -> int:
    return len(re.findall(r"[^\W_]+(?:[-'’][^\W_]+)*", text))


def render(text: str, sources: dict, *, template_name: str = "<template>",
           used: set | None = None, max_words: int | None = None) -> str:
    def replace(m):
        token = m.group()
        if token in ("{{", "}}"):
            return token[0]
        try:
            value = resolve(token, sources)
        except ValueError as exc:
            raise ValueError(f"{template_name}: {exc}") from exc
        if used is not None and token.startswith("{report:"):
            used.add(token[1:-1].split(":", 2)[1].split(".")[0])
        return value

    result = re.sub(r"\{\{|\}\}|\{[^{}]*\}|[{}]", replace, text)
    if max_words is not None and word_count(result) > max_words:
        raise ValueError(f"{template_name}: memo has {word_count(result)} words; maximum {max_words}")
    return result


def check_unused_derived(sources: dict, used: set, *, template_name: str = "report templates") -> None:
    unused = sources["report"].keys() - used
    if unused:
        tokens = ", ".join("{report:" + key + "}" for key in sorted(unused))
        raise ValueError(f"{template_name}: unused derived placeholders: {tokens}")


def _link_destinations(text: str):
    # Inline links/images: balance parentheses so ordinary filenames and URL paths work.
    for m in re.finditer(r"!?\[[^\]\n]*\]\(\s*", text):
        start = m.end()
        if text[start:start + 1] == "<":
            end = text.find(">", start + 1)
            if end == -1:
                raise ValueError("unterminated angle-bracket link")
            yield text[start + 1:end]
            continue
        depth = 0
        end = start
        while end < len(text):
            char = text[end]
            if (char == ")" or char.isspace()) and depth == 0:
                break
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            end += 1
        yield text[start:end]
    # Reference definitions apply to both links and images; optional titles are ignored.
    for m in re.finditer(r"^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", text, re.MULTILINE):
        yield m[1].removeprefix("<").removesuffix(">")


def check_links(text: str, target: Path, *, template_name: str = "<template>") -> None:
    try:
        for destination in _link_destinations(text):
            url = urlsplit(destination)
            if url.scheme or url.netloc or not url.path:
                continue
            if not (target.parent / unquote(url.path)).exists():
                raise ValueError(f"broken relative link/image {destination!r} from {target}")
    except ValueError as exc:
        raise ValueError(f"{template_name}: {exc}") from exc


def main() -> None:
    sources = load_sources()
    used = set()
    documents = []
    for template, target in C.REPORT_TEMPLATES:
        text = render(template.read_text(encoding="utf-8"), sources, template_name=str(template), used=used,
                      max_words=C.MEMO_MAX_WORDS if target == C.REPORT_DIR / "memo.md" else None)
        check_links(text, target, template_name=str(template))
        documents.append((target, text))
    check_unused_derived(sources, used, template_name=", ".join(str(t) for t, _ in C.REPORT_TEMPLATES)
                         or "report templates")
    # Validate the whole batch before writing report.json or any rendered document.
    C.REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    C.REPORT_JSON.write_text(json.dumps(sources["report"], indent=2) + "\n", encoding="utf-8")
    for target, text in documents:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"Wrote {target}: {word_count(text)} words")
    print(f"Wrote {C.REPORT_JSON}")


if __name__ == "__main__":
    main()

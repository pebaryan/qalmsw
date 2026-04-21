from qalmsw.llm.client import _extract_json, _parse_lenient_json


def test_raw_json_passthrough():
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_json_fence_stripped():
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_generic_fence_stripped():
    assert _extract_json('```\n{"a": 1}\n```') == '{"a": 1}'


def test_preamble_before_object():
    assert _extract_json('Sure, here you go: {"a": 1} hope that helps') == '{"a": 1}'


def test_nested_object_preserved():
    src = '```json\n{"issues": [{"message": "x"}]}\n```'
    assert _extract_json(src) == '{"issues": [{"message": "x"}]}'


def test_lenient_parses_strict_json():
    assert _parse_lenient_json('{"a": 1}') == {"a": 1}


def test_lenient_parses_latex_backslashes_in_strings():
    raw = '{"excerpt": "see \\cite{foo} and \\section{bar}"}'
    assert _parse_lenient_json(raw) == {"excerpt": "see \\cite{foo} and \\section{bar}"}


def test_lenient_parses_fenced_latex():
    raw = '```json\n{"issues": [{"excerpt": "paper \\cite{x}"}]}\n```'
    out = _parse_lenient_json(raw)
    assert out["issues"][0]["excerpt"] == "paper \\cite{x}"

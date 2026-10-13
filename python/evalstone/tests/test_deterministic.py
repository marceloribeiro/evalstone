import pytest
from pydantic import BaseModel

import evalstone as es
from evalstone import Output, Sample
from evalstone.checks import contains, exact, json_schema, length, numeric_tolerance, python, regex

S = Sample(
    id="s",
    input="q",
    expected={"answer": "Paris", "must_include": ["30 days", "receipt"], "total": 19.99},
)


# ── exact ────────────────────────────────────────────────────────────────────


def test_exact_uses_expected_path_and_is_text_aware():
    chk = exact(path="answer")
    assert chk(S, Output(value="Paris")).passed
    assert chk(S, Output(value="  paris ")).passed is False
    assert exact(path="answer", case_sensitive=False)(S, Output(value=" paris ")).passed
    assert chk(S, Output(value="Lyon")).reason == "expected 'Paris', got 'Lyon'"


def test_exact_compares_json_for_non_string_references():
    chk = exact(expected={"a": 1, "b": [1, 2]})
    assert chk(S, Output(value={"b": [1, 2], "a": 1})).passed
    assert chk(S, Output(value='{"a": 1, "b": [1, 2]}')).passed
    assert chk(S, Output(value="not json")).reason.startswith("output is not valid JSON")


def test_exact_missing_reference_is_an_error_not_a_pass():
    score = exact(path="nope")(S, Output(value="x"))
    assert score.error is not None and "no expected.nope" in score.error
    assert score.passed is False


# ── contains ─────────────────────────────────────────────────────────────────


def test_contains_defaults_to_expected_must_include_and_is_graded():
    chk = contains()
    assert chk(S, Output(value="Returns within 30 DAYS with the receipt.")).passed
    partial = chk(S, Output(value="Within 30 days."))
    assert partial.passed is False
    assert partial.value == 0.5
    assert partial.reason == "missing ['receipt']"


def test_contains_any_and_literal_needles():
    chk = contains(needles=["yes", "sure"], require_all=False)
    assert chk(S, Output(value="Sure thing")).passed
    assert chk(S, Output(value="no")).passed is False
    assert contains(needles="Exact", case_sensitive=True)(S, Output(value="exact")).passed is False


# ── regex ────────────────────────────────────────────────────────────────────


def test_regex_match_and_negative_match():
    assert regex(r"\bORD-\d{6}\b")(S, Output(value="Order ORD-123456 shipped")).passed
    neg = regex(r"as an ai", must_match=False)
    assert neg(S, Output(value="Happy to help")).passed
    assert neg(S, Output(value="As an AI, I cannot")).passed  # case-sensitive by default
    insensitive = regex(r"as an ai", flags=2, must_match=False)
    assert insensitive(S, Output(value="As an AI")).reason == "matched /as an ai/"


# ── json_schema ──────────────────────────────────────────────────────────────

SCHEMA = {
    "type": "object",
    "required": ["category", "confidence"],
    "properties": {
        "category": {"enum": ["billing", "shipping", "other"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


class Answer(BaseModel):
    category: str
    confidence: float


def test_json_schema_with_a_dict_schema():
    chk = json_schema(SCHEMA)
    assert chk(S, Output(value={"category": "billing", "confidence": 0.9})).passed
    assert chk(S, Output(value='{"category": "billing", "confidence": 0.9}')).passed
    bad = chk(S, Output(value={"category": "refund", "confidence": 0.9}))
    assert bad.passed is False and bad.reason.startswith("schema: category:")
    assert chk(S, Output(value="{oops")).reason.startswith("not valid JSON")


def test_json_schema_with_a_pydantic_model():
    chk = json_schema(Answer)
    assert chk(S, Output(value={"category": "billing", "confidence": "0.4"})).passed
    missing = chk(S, Output(value={"category": "billing"}))
    assert missing.passed is False and missing.reason.startswith("schema: confidence:")


# ── numeric_tolerance ────────────────────────────────────────────────────────


def test_numeric_tolerance_abs_rel_and_paths():
    chk = numeric_tolerance(path="total", abs_tol=0.01)
    assert chk(S, Output(value=19.985)).passed
    assert chk(S, Output(value="19.99")).passed
    assert chk(S, Output(value=20.5)).passed is False
    assert numeric_tolerance(path="total", rel_tol=0.05)(S, Output(value=20.5)).passed
    nested = numeric_tolerance(path="total", output_path="invoice.total", abs_tol=0)
    assert nested(S, Output(value={"invoice": {"total": 19.99}})).passed
    assert nested(S, Output(value={"invoice": {}})).reason == "output has no invoice.total"
    assert chk(S, Output(value="twenty")).reason == "output is not a number: 'twenty'"


# ── length ───────────────────────────────────────────────────────────────────


def test_length_limits():
    assert length(max_words=3)(S, Output(value="one two three")).passed
    assert length(max_words=3)(S, Output(value="one two three four")).reason == "4 words > max 3"
    assert length(max_chars=5)(S, Output(value="toolong")).passed is False
    assert length(min_chars=1)(S, Output(value="   ")).reason == "0 chars < min 1"


# ── python + namespace ───────────────────────────────────────────────────────


def test_python_wraps_any_function_without_registering():
    chk = python(lambda s, o: o.text.endswith("?"), "asks_back")
    with pytest.raises(ValueError, match="explicit key"):
        python(lambda s, o: True)
    import functools

    with pytest.raises(ValueError, match="explicit key"):
        python(functools.partial(lambda s, o, t: True, t=1))
    assert python(functools.partial(lambda s, o, t: True, t=1), "p").key == "p"
    assert chk.key == "asks_back"
    assert chk(S, Output(value="Anything else?")).passed
    assert "asks_back" not in es.registry
    assert es.checks.exact is exact


@pytest.mark.parametrize("factory", [exact, contains, length, numeric_tolerance])
def test_factories_accept_a_custom_key(factory):
    assert factory(key="custom").key == "custom"


@pytest.mark.parametrize("factory", [exact, contains, length, numeric_tolerance])
def test_key_is_keyword_only_so_payloads_cannot_be_mistaken_for_it(factory):
    with pytest.raises(TypeError):
        factory("custom")
    with pytest.raises(TypeError):
        regex("order_id", r"ORD-\d+")


# ── review findings on PR 2 ──────────────────────────────────────────────────


def test_exact_without_a_reference_never_passes_on_null_output():
    no_ref = Sample(id="n", input="q")
    for out in (Output.failed("timeout"), Output(value="null"), Output(value=None)):
        score = exact()(no_ref, out)
        assert score.passed is False and score.error is not None
    with_null = Sample(id="m", input="q", expected={"x": None})
    assert exact(path="x")(with_null, Output(value=None)).passed is False


def test_contains_materialises_iterators_and_passes_vacuously_on_no_needles():
    chk = contains(needles=(n for n in ["alpha", "beta"]))
    assert chk(S, Output(value="alpha beta")).passed
    assert chk(S, Output(value="zzz")).passed is False
    empty = Sample(id="e", input="q", expected={"must_include": []})
    for ra in (True, False):
        score = contains(require_all=ra)(empty, Output(value="anything"))
        assert score.passed is True and score.value == 1.0


def test_json_schema_honours_the_schema_draft_and_rejects_bad_schemas():
    draft4 = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "number",
        "maximum": 10,
        "exclusiveMaximum": True,
    }
    assert json_schema(draft4)(S, Output(value=5)).passed
    assert json_schema(draft4)(S, Output(value=10)).passed is False
    with pytest.raises(ValueError, match="invalid schema"):
        json_schema({"type": "strng"})


def test_numeric_tolerance_non_json_output_is_a_fail_not_an_error():
    score = numeric_tolerance(expected=1, output_path="total")(S, Output(value="the total is 1"))
    assert score.passed is False and score.error is None
    assert score.reason.startswith("not valid JSON")


def test_dig_only_indexes_lists_with_decimal_digits():
    from evalstone.checks.deterministic import _MISSING, _dig

    assert _dig([1, 2], "1") == 2
    assert _dig([1, 2], "²") is _MISSING

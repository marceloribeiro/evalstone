import json

import pytest

from evalstone import Dataset, Sample, Source


def test_sample_gets_a_content_derived_id_when_none_given():
    a = Sample(input={"q": "hi"}, expected="hello")
    b = Sample(input={"q": "hi"}, expected="hello")
    c = Sample(input={"q": "hi"}, expected="bye")
    assert a.id == b.id
    assert a.id != c.id
    assert len(a.id) == 16


def test_sample_keeps_an_explicit_id_and_is_frozen():
    s = Sample(id="s1", input="x", tags=["a"], source=Source.HARVESTED)
    assert s.id == "s1"
    with pytest.raises(Exception):  # noqa: B017 — pydantic frozen instance error
        s.input = "y"  # type: ignore[misc]


def test_dataset_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="duplicate sample ids"):
        Dataset("d", [Sample(id="s", input=1), Sample(id="s", input=2)])


def test_content_hash_is_order_sensitive_and_stable():
    s1, s2 = Sample(id="1", input="a"), Sample(id="2", input="b")
    assert Dataset("d", [s1, s2]).content_hash == Dataset("d", [s1, s2]).content_hash
    assert Dataset("d", [s1, s2]).content_hash != Dataset("d", [s2, s1]).content_hash
    assert Dataset("d", [s1, s2]).content_hash != Dataset("x", [s1]).content_hash


def test_content_hash_ignores_metadata_but_not_tags():
    base = Sample(id="1", input="a")
    with_meta = Sample(id="1", input="a", metadata={"note": "x"})
    with_tag = Sample(id="1", input="a", tags=["t"])
    assert Dataset("d", [base]).content_hash == Dataset("d", [with_meta]).content_hash
    assert Dataset("d", [base]).content_hash != Dataset("d", [with_tag]).content_hash


def test_jsonl_round_trip(tmp_path):
    path = tmp_path / "golden.jsonl"
    path.write_text(
        json.dumps(
            {
                "input": {"q": "Can I return a sale item?"},
                "expected": {"must": ["30 days"]},
                "tags": ["refund"],
            }
        )
        + "\n\n"
        + json.dumps({"id": "two", "input": "second"})
        + "\n",
        encoding="utf-8",
    )
    ds = Dataset.from_jsonl(path)
    assert ds.name == "golden"
    assert len(ds) == 2
    assert ds["two"].input == "second"
    assert ds.samples[0].tags == ["refund"]

    out = tmp_path / "copy.jsonl"
    ds.to_jsonl(out)
    again = Dataset.from_jsonl(out, name="golden")
    assert again.content_hash == ds.content_hash


def test_jsonl_reports_the_bad_line(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"input": 1}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.jsonl:2"):
        Dataset.from_jsonl(path)


def test_filter_requires_all_tags_and_predicate():
    ds = Dataset.from_records(
        "d",
        [
            {"id": "a", "input": 1, "tags": ["x", "y"]},
            {"id": "b", "input": 2, "tags": ["x"]},
            {"id": "c", "input": 3, "tags": ["y"]},
        ],
    )
    assert [s.id for s in ds.filter(tags=["x"])] == ["a", "b"]
    assert [s.id for s in ds.filter(tags=["x", "y"])] == ["a"]
    assert [s.id for s in ds.filter(predicate=lambda s: s.input > 1)] == ["b", "c"]


def test_sample_and_split_are_deterministic():
    ds = Dataset.from_records("d", [{"id": str(i), "input": i} for i in range(20)])
    assert [s.id for s in ds.sample(5, seed=1)] == [s.id for s in ds.sample(5, seed=1)]
    assert [s.id for s in ds.sample(5, seed=1)] != [s.id for s in ds.sample(5, seed=2)]
    iterate, held = ds.split(0.25, seed=3)
    assert len(iterate) == 15 and len(held) == 5
    assert {s.id for s in iterate}.isdisjoint({s.id for s in held})
    assert [s.id for s in ds.split(0.25, seed=3)[1]] == [s.id for s in held]
    with pytest.raises(ValueError):
        ds.split(1.5)


# ── review findings on PR 1 ──────────────────────────────────────────────────


def test_content_hash_is_reproducible_for_sets_tuples_dates_and_models():
    import datetime as dt

    from pydantic import BaseModel

    class Inp(BaseModel):
        q: str

    sample = Sample(
        id="x",
        input={"terms": {"gamma", "alpha", "beta"}, "pair": (1, 2), "when": dt.date(2026, 1, 2)},
        expected=Inp(q="hi"),
    )
    same = Sample(
        id="x",
        input={"terms": {"beta", "alpha", "gamma"}, "pair": (1, 2), "when": dt.date(2026, 1, 2)},
        expected=Inp(q="hi"),
    )
    assert same.content() == sample.content()
    h = Dataset("d", [sample]).content_hash
    assert h == Dataset("d", [sample]).content_hash and len(h) == 64


def test_unhashable_values_raise_instead_of_stringifying():
    class Opaque:
        pass

    with pytest.raises(TypeError, match="not JSON-serialisable"):
        Sample(input=Opaque())
    with pytest.raises(TypeError, match="dict keys must be strings"):
        Sample(input={1: "a", "b": 2})


def test_filter_accepts_a_single_tag_string():
    ds = Dataset.from_records(
        "d",
        [
            {"id": "a", "input": 1, "tags": ["rag"]},
            {"id": "b", "input": 2, "tags": ["r", "a", "g"]},
        ],
    )
    assert [s.id for s in ds.filter(tags="rag")] == ["a"]


def test_duplicate_derived_ids_explain_themselves_and_detection_is_fast():
    with pytest.raises(ValueError, match="derived from input\\+expected"):
        Dataset.from_records(
            "d", [{"input": "q", "tags": ["easy"]}, {"input": "q", "tags": ["hard"]}]
        )
    with pytest.raises(ValueError) as exc:
        Dataset("d", [Sample(id="s", input=1), Sample(id="s", input=2)])
    assert "derived" not in str(exc.value)
    import time

    started = time.perf_counter()
    Dataset.from_records("big", [{"id": str(i), "input": i} for i in range(20_000)])
    assert time.perf_counter() - started < 1.0


def test_content_hash_is_cached():
    ds = Dataset.from_records("d", [{"id": "a", "input": 1}])
    assert ds.content_hash is ds.content_hash

"""Synthetic checks only: no credentials, downloads or review release needed."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from src import cleaning as c


@pytest.fixture
def reviews():
    return pd.DataFrame(
        {
            "rating": [1, 5, 3],
            "title": ["Reaction", None, "Okay"],
            "text": [
                "&#34;no irritation&#34;<br />[[VIDEOID:abc]]",
                "",
                "cafe\u0301\u00a0\u2003  works\twell",
            ],
            "parent_asin": ["A", "B", "C"],
            "asin": ["variant-a", "variant-b", "variant-c"],
            "user_id": ["person1", "person2", "person3"],
            "timestamp": [1609459200000, 1609545600000, 1609632000000],
            "helpful_vote": [0, 2, 100],
        }
    )


def prepared(reviews):
    return c.flag_missing(c.normalise_text(c.decode_html(c.validate_schema(reviews))))


def test_schema_checks_and_failure_counts(reviews):
    assert c.validate_schema(reviews)["rating"].tolist() == [1, 5, 3]
    with pytest.raises(ValueError, match="Missing required columns"):
        c.validate_schema(reviews.drop(columns="rating"))
    reviews.loc[0, "rating"] = 6
    reviews.loc[1, "timestamp"] = np.nan
    with pytest.raises(ValueError, match=r"'rating': 1, 'timestamp': 1"):
        c.validate_schema(reviews)


def test_decode_preserves_negation(reviews):
    df = c.decode_html(reviews)
    assert df.loc[0, "text"] == '"no irritation"  '
    assert "VIDEOID" not in df.loc[0, "text"]
    assert df["html_changed"].tolist() == [True, False, False]


def test_unicode_and_whitespace_keep_case_and_punctuation(reviews):
    df = c.normalise_text(c.decode_html(reviews))
    assert df.loc[2, "text"] == "café works well"
    assert df.loc[0, "text"] == '"no irritation"'
    assert df.loc[0, "title"] == "Reaction"


def test_missing_flags_never_drop_rows(reviews):
    df = prepared(reviews)
    assert len(df) == 3
    assert df["is_empty"].tolist() == [False, True, False]
    assert df["is_short"].tolist() == [True, True, False]
    assert df.loc[1, "missing_title"]
    assert df.loc[1, "title"] == ""


def test_duplicates_and_conflicting_review_keys(reviews):
    df = prepared(reviews)
    duplicate = df.iloc[[0]].copy()
    cross = duplicate.assign(parent_asin="D", asin="variant-d")
    conflict = duplicate.assign(text="Different content for this key")
    df = c.remove_duplicates(
        pd.concat([df, duplicate, cross, conflict], ignore_index=True)
    )
    assert len(df) == 5
    assert df["dup_cross_product"].sum() == 2
    assert df["repeated_review_key"].sum() == 2


def test_duplicate_identity_keeps_independent_reviewers(reviews):
    first = prepared(reviews).iloc[[0]]
    other = first.assign(user_id="independent-reviewer")
    copy = first.assign(timestamp=first["timestamp"] + 1000)
    out = c.remove_duplicates(pd.concat([first, other, copy], ignore_index=True))
    assert out["user_id"].tolist() == ["person1", "independent-reviewer"]
    assert out["dup_same_text_other_reviewer"].all()


def test_numeric_scaling_and_reusable_parameters():
    df = pd.DataFrame(
        {"helpful_vote": [0, 1, 3, 7, 1000], "word_count": [0, 2, 4, 6, 8]}
    )
    out = c.normalise_numeric(df)
    for source, name in (("helpful_vote", "helpful"), ("word_count", "word_count")):
        values = np.log1p(df[source])
        assert out[f"{name}_log1p"].tolist() == pytest.approx(values.tolist())
        assert out[f"{name}_robust"].median() == pytest.approx(0)
        assert out[f"{name}_robust"].quantile(0.75) - out[f"{name}_robust"].quantile(
            0.25
        ) == pytest.approx(1)
    parameters = {name: {"median": 2, "scale": 3} for name in ("helpful", "word_count")}
    reused = c.normalise_numeric(df.iloc[[0]], parameters)
    assert reused["helpful_robust"].item() == pytest.approx(-2 / 3)
    constant = c.normalise_numeric(
        pd.DataFrame({"helpful_vote": [0, 0], "word_count": [3, 3]})
    )
    assert constant[["helpful_robust", "word_count_robust"]].eq(0).all().all()
    parameters["helpful"]["scale"] = 0
    with pytest.raises(ValueError, match="Invalid numeric scaling"):
        c.normalise_numeric(df, parameters)


def test_language_sampling_is_stratified_seeded_and_weighted(monkeypatch):
    # Unequal class sizes ensure the overall recall uses population weights.
    frame = pd.DataFrame(
        {
            "text": ["english example words"] * 18000
            + ["foreign example words"] * 3000
            + ["ambiguous example words"] * 1000
            + ["too short"],
            "language": ["likely_en"] * 18000
            + ["likely_non_en"] * 3000
            + ["unknown"] * 1001,
            "word_count": [3] * 22000 + [2],
        }
    )
    monkeypatch.setattr(
        c, "detect", lambda text: "en" if text.startswith("english") else "es"
    )
    results = []
    for chunksize in [100, len(frame)]:
        samples, populations = {}, {}
        rng = np.random.default_rng(42)
        for start in range(0, len(frame), chunksize):
            c._sample_language(
                frame.iloc[start : start + chunksize], samples, populations, rng
            )
        agreement, result = c.validate_language(samples, populations, 42)
        assert agreement["sample_size"].sum() == 20000
        assert (
            agreement.set_index("heuristic_class").loc["likely_non_en", "sample_size"]
            >= 2000
        )
        assert (
            agreement.set_index("heuristic_class").loc["unknown", "sample_size"] == 1000
        )
        assert result["precision"] == 1
        assert result["recall"] == pytest.approx(0.75)
        assert result["poor_agreement"]
        results.append(agreement)
    pd.testing.assert_frame_equal(*results)
    agreement, result = c.validate_language({}, {}, 42)
    assert agreement.empty and result["sample_size"] == 0
    assert result["precision"] is None and result["recall"] is None


def test_language_reference_failure_and_threshold_adjustment(monkeypatch):
    frame = pd.DataFrame(
        {
            "text": ["This is a sentence", "el producto is muy bueno", "123 456 789"],
            "word_count": 3,
        }
    )
    initial = c.identify_language(frame)
    adjusted = c.identify_language(frame, c.ADJUSTED_LANGUAGE_THRESHOLDS)
    assert initial.loc[1, "language"] == "likely_non_en"
    assert adjusted.loc[0, "language"] == "likely_en"

    def detector(text):
        if text.startswith("123"):
            raise c.LangDetectException(0, "No language features")
        return "en"

    monkeypatch.setattr(c, "detect", detector)
    samples, populations = {}, {}
    c._sample_language(initial, samples, populations, np.random.default_rng(42))
    _, result = c.validate_language(samples, populations, 42)
    assert result["undetected"] == 1
    assert result["poor_agreement"]


def test_outlier_rules_retain_extremes(reviews):
    df = prepared(reviews)
    df.loc[0, "timestamp"] = 0
    df = pd.concat([df, *[df.iloc[[2]]] * 10], ignore_index=True)
    limits = {"length_lower": 0, "length_upper": 1, "helpful_upper": 99}
    out = c.flag_outliers(df, limits)
    assert len(out) == len(df)
    assert out.loc[0, "timestamp_outside_window"]
    assert out["helpful_outlier"].sum() == 11
    assert out["reviewer_burst"].sum() == 11
    assert out.loc[2, "helpful_log1p"] == np.log1p(100)


def test_language_is_a_flag_not_a_filter():
    df = pd.DataFrame(
        {
            "text": [
                "This is good for my skin",
                "这是非常好的产品",
                "el producto es muy bueno para la piel",
                "",
                "ZXQ 123",
            ]
        }
    )
    out = c.identify_language(df)
    assert out["language"].tolist() == [
        "likely_en",
        "likely_non_en",
        "likely_non_en",
        "unknown",
        "unknown",
    ]
    assert len(out) == 5


def test_dates_use_utc(reviews):
    out = c.derive_dates(reviews)
    assert out.loc[0, "utc_date"] == "2021-01-01"
    assert out.loc[0, "quarter"] == "2021Q1"
    assert str(out["timestamp_utc"].dt.tz) == "UTC"


def test_catalogue_join_missing_fields_units_and_shade(reviews):
    catalogue = c.normalise_catalogue(
        pd.DataFrame(
            {
                "parent_asin": ["A", "B"],
                "title": ["Lotion 2\u00a0fl oz Shade: Beige", "Cream 50 g"],
            }
        )
    )
    out = c.join_catalogue(reviews, catalogue)
    assert len(out) == 3
    assert out.loc[0, "quantity_ml"] == pytest.approx(59.147059125)
    assert out.loc[1, "quantity_g"] == 50
    assert out.loc[0, "shade"] == "beige"
    assert out["catalogue_unmatched"].tolist() == [False, False, True]
    assert out["catalogue_missing_fields"].all()
    with pytest.raises(ValueError, match="unique"):
        c.normalise_catalogue(pd.DataFrame({"parent_asin": ["A", "A"]}))


def test_pseudonyms_require_secret_and_change_with_salt(reviews, monkeypatch):
    monkeypatch.delenv("CLEANING_SALT", raising=False)
    with pytest.raises(ValueError, match="CLEANING_SALT"):
        c.pseudonymise(reviews)
    monkeypatch.setenv("CLEANING_SALT", "synthetic-test-secret-123456789012")
    first = c.pseudonymise(reviews)
    assert "user_id" not in first
    assert first["user_hash"].equals(c.pseudonymise(reviews)["user_hash"])
    monkeypatch.setenv("CLEANING_SALT", "another-synthetic-secret-12345678")
    assert not first["user_hash"].equals(c.pseudonymise(reviews)["user_hash"])


def test_domain_flags_preserve_context():
    df = pd.DataFrame(
        {
            "title": [""] * 4,
            "text": [
                "I recall using this without irritation",
                "The return window expired yesterday",
                "The product expired and caused a rash",
                "It didn't burn, never stung, not once",
            ],
        }
    )
    out = c.flag_domain(df)
    assert out["has_negation"].tolist() == [True, False, False, True]
    assert out["recall_false_friend"].tolist() == [True, False, False, False]
    assert out["expired_return_window"].tolist() == [False, True, False, False]
    assert out["text"].equals(df["text"])


def test_histogram_quantiles_match_numpy():
    values = np.array([0, 0, 1, 2, 2, 2, 100])
    histogram = dict(zip(*np.unique(values, return_counts=True)))
    for q in (0.25, 0.75, 0.999):
        assert c._quantile(histogram, q) == pytest.approx(np.quantile(values, q))
        assert c._quantile(histogram, q, np.log1p) == pytest.approx(
            np.quantile(np.log1p(values), q)
        )


@pytest.mark.parametrize("parquet", [True, False])
@pytest.mark.parametrize("adjusted", [False, True])
def test_stream_is_independent_of_chunk_boundaries(
    tmp_path, reviews, monkeypatch, parquet, adjusted
):
    monkeypatch.setenv("CLEANING_SALT", "synthetic-test-secret-123456789012")
    monkeypatch.setattr(c, "detect", lambda text: "es" if adjusted else "en")
    real_find = c.importlib.util.find_spec
    if not parquet:
        monkeypatch.setattr(
            c.importlib.util,
            "find_spec",
            lambda name: None if name == "pyarrow" else real_find(name),
        )
    raw = pd.concat(
        [
            reviews,
            reviews.iloc[[0]],
            reviews.iloc[[0]].assign(parent_asin="B", user_id="different"),
            reviews.iloc[[0]].assign(user_id="independent"),
            reviews.iloc[[0]].assign(
                text="Conflicting review content for the same key"
            ),
        ],
        ignore_index=True,
    )
    path = tmp_path / "reviews.jsonl.gz"
    raw.to_json(path, orient="records", lines=True, compression="gzip")
    with gzip.open(tmp_path / "meta_reviews.jsonl.gz", "wt") as handle:
        for parent in ["A", "B", "C"]:
            handle.write(
                json.dumps(
                    {
                        "parent_asin": parent,
                        "title": "Lotion 100 ml",
                        "store": "Store",
                        "main_category": "Beauty",
                    }
                )
                + "\n"
            )
    outputs = []
    for chunksize in [1, 2, 100]:
        directory = tmp_path / str(chunksize)
        log = c.run(path, directory, chunksize)
        assert log["step"].tolist() == c.STEPS
        assert log.loc[log["step"].eq("duplicates"), "rows_out"].item() == 6
        files = sorted((directory / "cleaned").iterdir())
        output = pd.concat(
            [
                pd.read_parquet(f) if parquet else pd.read_csv(f, keep_default_na=False)
                for f in files
            ],
            ignore_index=True,
        )
        outputs.append(output)
        assert "user_id" not in output
        assert output["dup_cross_product"].sum() == 3
        assert output["dup_same_text_other_reviewer"].sum() == 2
        assert output["repeated_review_key"].sum() == 2
        metrics = json.loads((directory / "cleaning_metrics.json").read_text())
        assert metrics["review_key_audit"]["groups_with_different_content"] == 1
        assert metrics["removed_exact_duplicates"] == 1
        assert metrics["deduplication_audit"]["old_rule_removed_rows"] == 2
        assert metrics["deduplication_audit"]["old_rule_other_reviewer_rows"] == 1
        assert metrics["deduplication_audit"]["independent_reviews_preserved"] == 1
        for source, name in (("helpful_vote", "helpful"), ("word_count", "word_count")):
            scaling = metrics["numeric_scaling"][name]
            assert scaling["median"] == pytest.approx(np.log1p(output[source]).median())
            assert output[f"{name}_robust"].tolist() == pytest.approx(
                (
                    (np.log1p(output[source]) - scaling["median"]) / scaling["scale"]
                ).tolist()
            )
        agreement = pd.read_csv(directory / "language_validation.csv")
        assert agreement["seed"].nunique() == (2 if adjusted else 1)
        assert (
            agreement.groupby("seed")["sample_size"]
            .sum()
            .eq(output["word_count"].ge(3).sum())
            .all()
        )
        expected_language = c.identify_language(output, metrics["language_thresholds"])
        assert output["language"].equals(expected_language["language"])
        assert not list(directory.glob(".cleaning-work-*"))
    for output in outputs[1:]:
        pd.testing.assert_frame_equal(outputs[0], output)

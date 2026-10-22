"""Small population checks for the streaming aggregates and uncertainty."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from src import eda
from src import features


def test_wilson_interval_including_empty_and_extreme_months():
    low, high = eda.wilson_interval([0, 5, 10, 0], [10, 10, 10, 0])
    assert low[:3] == pytest.approx([0, 0.23659309, 0.7224672])
    assert high[:3] == pytest.approx([0.2775328, 0.76340691, 1])
    assert np.isnan(low[3]) and np.isnan(high[3])
    with pytest.raises(ValueError, match="Wilson counts"):
        eda.wilson_interval([2], [1])


def test_streaming_aggregates_reconcile_and_sampling_is_deterministic(tmp_path):
    df = pd.DataFrame(
        {
            "title": ["", "", ""],
            "text": ["it burned", "no irritation", "fine"],
            "rating": [1, 5, 4],
            "word_count": [2, 2, 1],
            "helpful_vote": [0, 1, 2],
            "timestamp": [0, 86400000, 5184000000],
            "parent_asin": ["a", "b", "a"],
            "user_hash": ["u", "v", "u"],
            "catalogue_category": ["beauty", None, "beauty"],
            "catalogue_store": ["shop", "shop", None],
        }
    )
    paths = [tmp_path / "part-0.parquet", tmp_path / "part-1.parquet"]
    df.iloc[:2].to_parquet(paths[0], index=False)
    df.iloc[2:].to_parquet(paths[1], index=False)
    outputs, sample, cue_sample = eda.aggregate_partitions(
        paths, pd.Series({"a": "USD <10"})
    )
    assert outputs["rating"].reviews.sum() == 3
    assert outputs["rating"].cue.sum() == 2
    assert outputs["rating"].unnegated.sum() == 1
    assert outputs["monthly"].reviews.tolist() == [2, 0, 1]
    assert outputs["category"].reviews.sum() == 3
    assert outputs["category_year"].reviews.sum() == 3
    assert outputs["price_band"].set_index("price_band").reviews.to_dict() == {
        "USD <10": 2,
        "<missing>": 1,
    }
    assert outputs["coverage"].iloc[0].to_dict() == {
        "first_review_ms": 0,
        "last_review_ms": 5184000000,
    }
    assert len(sample) == 3 and len(cue_sample) == 2
    repeated = eda.aggregate_partitions(paths, pd.Series({"a": "USD <10"}))
    pd.testing.assert_frame_equal(sample, repeated[1])
    pd.testing.assert_frame_equal(cue_sample, repeated[2])


def test_catalogue_price_bands_boundaries_missing_and_invalid_data(tmp_path):
    path = tmp_path / "catalogue.jsonl.gz"

    def write(rows):
        with gzip.open(path, "wt") as source:
            source.writelines(json.dumps(row) + "\n" for row in rows)

    write(
        [
            {"parent_asin": str(i), "price": price}
            for i, price in enumerate([None, 0, 9.99, 10, "24.99", 25, 49.99, 50])
        ]
    )
    assert eda.catalogue_price_bands(path).tolist() == [
        "<missing>",
        "USD <10",
        "USD <10",
        "USD 10 to <25",
        "USD 10 to <25",
        "USD 25 to <50",
        "USD 25 to <50",
        "USD >=50",
    ]
    write(
        [
            {"parent_asin": str(i), "price": price}
            for i, price in enumerate(["from 28.00", "\u2014"])
        ]
    )
    assert eda.catalogue_price_bands(path).tolist() == ["<missing>", "<missing>"]
    for price in [-1, float("inf"), True, "invalid"]:
        write([{"parent_asin": "p", "price": price}])
        with pytest.raises(ValueError):
            eda.catalogue_price_bands(path)
    write([{"parent_asin": "p", "price": None}] * 2)
    with pytest.raises(ValueError, match="unique"):
        eda.catalogue_price_bands(path)
    write([])
    with pytest.raises(ValueError, match="empty"):
        eda.catalogue_price_bands(path)


def test_market_trends_pool_counts_keep_gaps_and_select_top_five():
    monthly = pd.DataFrame(
        {
            "month": ["2020-01", "2021-01", "2022-02"],
            "reviews": [10, 90, 20],
            "cue": [8, 2, 10],
            "unnegated": [6, 1, 8],
            "negated": [2, 1, 2],
        }
    )
    category = pd.DataFrame(
        {
            "category": ["<missing>", "a", "b", "c", "d", "e", "f"],
            "reviews": [1000, 100, 80, 60, 40, 20, 1],
            "cue": [100, 10, 20, 10, 10, 10, 1],
        }
    )
    annual = pd.DataFrame(
        {
            "category": ["a", "a", "a", "b", "b"],
            "year": [2020, 2021, 2022, 2020, 2022],
            "reviews": [10, 20, 30, 10, 10],
            "cue": [1, 4, 3, 1, 3],
            "unnegated": [1, 4, 3, 1, 3],
            "negated": [0] * 5,
        }
    )
    price = pd.DataFrame(
        {"price_band": ["USD <10", "<missing>"], "reviews": [20, 10], "cue": [5, 0]}
    )
    out = eda.market_trends(monthly, category, annual, price)
    calendar = out["calendar_month"].set_index("calendar_month")
    assert calendar.loc[1, "cue_rate"] == pytest.approx(0.1)
    assert calendar.loc[1, "reviews"] == 100
    assert np.isnan(calendar.loc[3, "cue_rate"])
    test = out["seasonality_test"].iloc[0]
    assert test.peak_month == 2 and test.trough_month == 1
    assert test.chi_square == pytest.approx(19.2)
    assert test.dof == 1 and 0 < test.p_value < 0.001
    assert (
        out["category"].iloc[1].wilson_low < 0.1 < out["category"].iloc[1].wilson_high
    )
    assert (
        out["price_band"].iloc[0].wilson_low
        < 0.25
        < out["price_band"].iloc[0].wilson_high
    )
    yoy = out["category_yoy"].set_index(["category", "year"])
    assert set(out["category_yoy"].category) == set("abcde")
    assert yoy.loc[("a", 2021), "change_pp"] == pytest.approx(10)
    assert yoy.loc[("a", 2022), "change_pp"] == pytest.approx(-10)
    assert np.isnan(yoy.loc[("b", 2022), "change_pp"])
    assert yoy.loc[("a", 2021), "interior_year"]
    assert not yoy.loc[("a", 2022), "interior_year"]
    with pytest.raises(ValueError, match="Seasonality"):
        eda.market_trends(monthly.assign(cue=0), category, annual, price)


def test_sample_analysis_covers_features_without_exporting_text():
    texts = [
        "it burned my skin",
        "no irritation",
        "all fine",
        "rancid cream",
        "hair loss",
        "eye infection",
        "my skin had irritation",
        "gentle cream",
    ] * 10
    sample = pd.DataFrame(
        {
            "title": "",
            "text": texts,
            "rating": [1, 5, 4, 2, 3, 5, 1, 4] * 10,
            "timestamp": np.arange(80) * 86400000,
            "user_hash": [f"u{i % 5}" for i in range(80)],
            "parent_asin": [f"p{i % 4}" for i in range(80)],
            "catalogue_category": "beauty",
            "catalogue_store": "shop",
            "word_count": [len(text.split()) for text in texts],
        }
    )
    sample = features.safety_features(sample)
    rating = (
        sample.groupby("rating")
        .agg(reviews=("rating", "size"), cue=("safety_cue", "sum"))
        .reset_index()
    )
    outputs, summary = eda.sample_analysis(
        sample,
        sample.loc[sample.safety_cue],
        {"word_count": {"median": 1, "scale": 2}},
        rating,
    )
    relevance = outputs["feature_relevance"].set_index("feature")
    assert not relevance.loc["reviewer_prior_count", "proxy_derived"]
    assert relevance.loc["skin_reaction_count", "proxy_derived"]
    assert relevance.loc["rating_x_cue", "proxy_derived"]
    assert summary["relevance_size"] == 40
    assert summary["relevance_proxy_positives"] > 0
    assert outputs["svd"].columns.tolist() == ["component_1", "component_2", "group"]
    assert len(summary["svd_explained_variance"]) == 2

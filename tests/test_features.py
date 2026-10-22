"""Synthetic feature checks, including cold starts and strict event-time ordering."""

import numpy as np
import pandas as pd
import pytest

from src import features as f


def frame(texts):
    return pd.DataFrame({"title": "", "text": texts})


def test_negation_scopes_each_mention_and_resets_at_boundaries():
    out = f.safety_features(
        frame(
            [
                "no irritation at all",
                "it burned",
                "it did not cause any rash",
                "no irritation but it burned",
                "no rash. My eyes burned",
                "No rash and absolutely no irritation",
                "not good. it caused irritation",
                "it didn't burn",
                "free of irritation",
                "irritation then no rash",
            ]
        )
    )
    assert out.unnegated_cue.tolist() == [
        False,
        True,
        False,
        True,
        True,
        False,
        True,
        False,
        False,
        True,
    ]
    assert out.negated_cue.tolist() == [
        True,
        False,
        True,
        True,
        True,
        True,
        False,
        True,
        True,
        True,
    ]
    title = pd.DataFrame({"title": ["no"], "text": ["irritation"]})
    assert f.safety_features(title).unnegated_cue.item()


def test_group_counts_retain_overlapping_groups_and_repeated_mentions():
    out = f.safety_features(
        frame(["rash rash and rancid cream", "eye infection", "no irritation"])
    )
    assert out.skin_reaction_count.tolist() == [2, 0, 0]
    assert out.smell_spoilage_count.tolist() == [1, 0, 0]
    assert out.eye_count.tolist() == [0, 1, 0]
    assert out.contamination_count.tolist() == [0, 1, 0]
    assert out.irritation_unnegated_count.tolist() == [0, 0, 0]


def test_negation_handles_contracted_auxiliaries_and_cannot():
    out = f.safety_features(
        frame(
            [
                "my eyes weren't irritated",
                "it can't cause a rash",
                "it wouldn’t burn",
                "it cannot cause irritation",
                "important skin rash",
            ]
        )
    )
    assert out.unnegated_cue.tolist() == [False, False, False, False, True]


def test_five_star_mismatch_requires_unnegated_cue():
    df = f.safety_features(frame(["it burned", "no irritation", "rash"]))
    df["rating"] = [5, 5, 1]
    assert f.rating_text_features(df).rating_text_mismatch.tolist() == [
        True,
        False,
        False,
    ]


def test_shape_uses_saved_parameters_and_handles_empty_text():
    df = frame(["MY skin!", ""])
    df["word_count"] = [2, 0]
    out = f.text_shape_features(df, {"word_count": {"median": 1, "scale": 2}})
    assert out.length_scaled.tolist() == pytest.approx([(np.log1p(2) - 1) / 2, -0.5])
    assert out.capitals_share.tolist() == pytest.approx([2 / 6, 0])
    assert out.exclamation_share.tolist() == pytest.approx([1 / 8, 0])
    assert out.body_part_mention.tolist() == [True, False]


def test_histories_exclude_future_current_and_all_tied_events():
    df = pd.DataFrame(
        {
            "timestamp": [3, 1, 2, 2],
            "user_hash": "u",
            "parent_asin": "p",
            "rating": [5, 1, 2, 4],
            "unnegated_cue": [False, True, False, True],
        },
        index=[4, 4, 9, 0],
    )
    out = f.history_features(df)
    assert out.index.tolist() == df.index.tolist()
    assert out.reviewer_prior_count.tolist() == [3, 0, 1, 1]
    assert out.reviewer_prior_mean_rating.iloc[[0, 2, 3]].tolist() == pytest.approx(
        [7 / 3, 1, 1]
    )
    assert np.isnan(out.reviewer_prior_mean_rating.iloc[1])
    assert out.product_prior_cue_rate.iloc[[0, 2, 3]].tolist() == pytest.approx(
        [2 / 3, 1, 1]
    )
    earlier = f.history_features(df.loc[df.timestamp.lt(3)])
    pd.testing.assert_frame_equal(out.loc[out.timestamp.lt(3)], earlier)


def test_context_encoder_uses_past_and_handles_unknown_missing_and_high_cardinality():
    reference = pd.DataFrame(
        {
            "timestamp": [1, 2],
            "catalogue_category": ["a", "a"],
            "catalogue_store": ["x", None],
        }
    )
    encoder = f.fit_context_encoder(reference, cutoff=3, low_cardinality=1)
    df = pd.DataFrame(
        {
            "timestamp": [3, 4],
            "catalogue_category": ["a", "new"],
            "catalogue_store": [None, "new"],
        }
    )
    out = f.context_features(df, encoder)
    assert out.catalogue_category_onehot_0.tolist() == [True, False]
    assert out.catalogue_category_unknown.tolist() == [False, True]
    assert out.catalogue_store_frequency.tolist() == [0.5, 0]
    assert "catalogue_store_onehot_0" not in out
    with pytest.raises(ValueError, match="strictly before"):
        f.fit_context_encoder(reference, cutoff=2)
    with pytest.raises(ValueError, match="precede"):
        f.context_features(reference, encoder)


def test_time_features_preserve_order_and_age_uses_first_observed_review():
    df = pd.DataFrame(
        {"timestamp": [172800000, 0, 86400000], "parent_asin": ["p", "p", "new"]}
    )
    out = f.time_features(df)
    assert out.product_age_days.tolist() == [2, 0, 0]
    assert out.review_year.tolist() == [1970] * 3
    assert out.review_quarter.tolist() == [1] * 3


def test_interactions_require_both_signals():
    df = pd.DataFrame(
        {
            "rating": [5, 1],
            "unnegated_cue": [True, False],
            "body_part_mention": [True, True],
        }
    )
    out = f.interaction_features(df)
    assert out.rating_x_cue.tolist() == [5, 0]
    assert out.body_x_cue.tolist() == [True, False]


def test_invalid_feature_inputs_fail_without_review_contents():
    with pytest.raises(ValueError, match="Missing feature columns"):
        f.safety_features(pd.DataFrame())
    with pytest.raises(ValueError, match="Null required"):
        f.safety_features(frame([None]))
    with pytest.raises(ValueError, match="Invalid word-count"):
        f.text_shape_features(
            pd.DataFrame({"text": [""], "word_count": [0]}),
            {"word_count": {"median": 0, "scale": 0}},
        )

"""Target-free review features. History includes strictly earlier timestamps only."""

import re

import numpy as np
import pandas as pd


# Week 2 groups, with standalone burns added to cover short reaction accounts.
WORD_GROUPS = {
    "skin_reaction": r"\b(?:rash(?:es)?|hives|itch(?:y|ing|ed)?|blister(?:s|ed)?|swell(?:ing)?|swollen|allergic reaction|chemical burn|burn(?:ed|t|ing|s)?)\b",
    "irritation": r"\birritat(?:ed|ion|ing|es)\b",
    "eye": r"\b(?:eye infection|pink ?eye|stye|eyes? (?:burn(?:ed|ing)?|sting(?:ing)?|swelled|swollen))\b",
    "hair_scalp": r"\b(?:hair (?:fell|falling|fall) out|hair loss|bald spots?|scalp (?:burn(?:ed|ing)?|sores?))\b",
    "smell_spoilage": r"\b(?:rancid|mold(?:y)?|mould(?:y)?|spoiled|rotten|smell(?:s|ed)? (?:bad|awful|terrible|horrible|off|sour|like chemicals?)|foul (?:odor|odour|smell))\b",
    "contamination": r"\b(?:contaminat(?:ed|ion)|bacteria(?:l)?|infection|expired|recall(?:ed)?)\b",
}
PATTERNS = {name: re.compile(pattern, re.I) for name, pattern in WORD_GROUPS.items()}
ANY_CUE = re.compile("|".join(WORD_GROUPS.values()), re.I)
TOKEN = re.compile(r"\b\w+(?:['’]\w+)?\b")
BOUNDARY = re.compile(r"[.!?;:\n]|\b(?:but|however|yet)\b", re.I)
NEGATORS = {
    "no",
    "not",
    "never",
    "without",
    "zero",
    "non",
    "cannot",
    "didnt",
    "doesnt",
    "dont",
    "hasnt",
    "havent",
    "wont",
    "wasnt",
    "isnt",
    "arent",
    "couldnt",
}


def _require(df, columns):
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {sorted(missing)}")
    if df[list(columns)].isna().any().any():
        raise ValueError(f"Null required feature data: {sorted(columns)}")


def _negated(text, start):
    prefix = BOUNDARY.split(text[:start])[-1]
    tokens = [x.casefold() for x in TOKEN.findall(prefix)]
    return any(
        token.replace("'", "").replace("’", "") in NEGATORS
        or token.endswith(("n't", "n’t"))
        for token in tokens[-4:]
    ) or tokens[-2:] == ["free", "of"]


def safety_features(df):
    """Count each group's raw and unnegated matches within a four-token scope."""
    _require(df, ["title", "text"])
    out = df.copy()
    text = out["title"].astype(str) + ". " + out["text"].astype(str)
    candidates = text.str.contains(ANY_CUE)
    counts = np.zeros((len(out), len(PATTERNS) * 2), dtype=np.int32)
    for position in np.flatnonzero(candidates.to_numpy()):
        value = text.iloc[position]
        for j, pattern in enumerate(PATTERNS.values()):
            matches = list(pattern.finditer(value))
            counts[position, j * 2] = len(matches)
            counts[position, j * 2 + 1] = sum(
                not _negated(value, match.start()) for match in matches
            )
    for j, name in enumerate(PATTERNS):
        out[f"{name}_count"] = counts[:, j * 2]
        out[f"{name}_unnegated_count"] = counts[:, j * 2 + 1]
    out["safety_cue"] = counts[:, ::2].sum(axis=1) > 0
    out["unnegated_cue"] = counts[:, 1::2].sum(axis=1) > 0
    out["negated_cue"] = (counts[:, ::2] - counts[:, 1::2]).sum(axis=1) > 0
    return out


def rating_text_features(df):
    _require(df, ["rating", "unnegated_cue"])
    if not df["rating"].isin([1, 2, 3, 4, 5]).all():
        raise ValueError("Rating must be an integer from 1 to 5")
    return df.assign(rating_text_mismatch=df["rating"].eq(5) & df["unnegated_cue"])


def text_shape_features(df, parameters):
    """Use saved descriptive scaling; refit parameters on past data for models."""
    _require(df, ["text", "word_count"])
    center = parameters["word_count"]["median"]
    scale = parameters["word_count"]["scale"]
    if not np.isfinite(center) or not np.isfinite(scale) or scale <= 0:
        raise ValueError("Invalid word-count scaling parameters")
    if (df["word_count"] < 0).any():
        raise ValueError("Word counts cannot be negative")
    out = df.copy()
    text = out["text"].astype(str)
    letters = text.str.count(r"[^\W\d_]")
    out["length_scaled"] = (np.log1p(out["word_count"]) - center) / scale
    out["exclamation_share"] = text.str.count("!").div(text.str.len().clip(lower=1))
    out["capitals_share"] = text.map(lambda s: sum(c.isupper() for c in s)).div(
        letters.clip(lower=1)
    )
    out["body_part_mention"] = text.str.contains(
        r"\b(?:my|our)\s+(?:(?:\w+)\s+){0,2}(?:skin|eyes?|scalp|face|lips?)\b",
        case=False,
    )
    return out


def history_features(df):
    """Histories refer to the supplied event stream, excluding all timestamp ties."""
    _require(df, ["timestamp", "user_hash", "parent_asin", "rating", "unnegated_cue"])
    out = df.copy()
    if (
        not pd.api.types.is_numeric_dtype(out["timestamp"])
        or not np.isfinite(out["timestamp"]).all()
    ):
        raise ValueError("History timestamps must be finite milliseconds")
    for entity, prefix, value in (
        ("user_hash", "reviewer", "rating"),
        ("parent_asin", "product", "unnegated_cue"),
    ):
        totals = (
            out.groupby([entity, "timestamp"], sort=True)[value]
            .agg(["size", "sum"])
            .reset_index()
        )
        groups = totals.groupby(entity, sort=False)
        totals[f"{prefix}_prior_count"] = groups["size"].cumsum() - totals["size"]
        previous_sum = groups["sum"].cumsum() - totals["sum"]
        mean_name = (
            "reviewer_prior_mean_rating"
            if prefix == "reviewer"
            else "product_prior_cue_rate"
        )
        totals[mean_name] = previous_sum.div(
            totals[f"{prefix}_prior_count"].replace(0, np.nan)
        )
        index = pd.MultiIndex.from_frame(out[[entity, "timestamp"]])
        prior = totals.set_index([entity, "timestamp"])
        for column in (f"{prefix}_prior_count", mean_name):
            out[column] = prior[column].reindex(index).to_numpy()
        out[f"{prefix}_cold_start"] = out[f"{prefix}_prior_count"].eq(0)
    return out


def fit_context_encoder(reference, cutoff, low_cardinality=12):
    """Fit vocabulary/frequencies only on events strictly before the cutoff."""
    _require(reference, ["timestamp"])
    if reference.empty or not reference["timestamp"].lt(cutoff).all():
        raise ValueError(
            "Encoder reference must be nonempty and strictly before cutoff"
        )
    result = {"cutoff": int(cutoff), "columns": {}}
    for name in ("catalogue_category", "catalogue_store"):
        if name not in reference:
            raise ValueError(f"Missing feature column: {name}")
        values = reference[name].fillna("<missing>")
        frequency = values.value_counts(normalize=True).to_dict()
        result["columns"][name] = {
            "frequency": frequency,
            "vocabulary": sorted(frequency)
            if len(frequency) <= low_cardinality
            else [],
        }
    return result


def context_features(df, encoder):
    _require(df, ["timestamp"])
    if not df["timestamp"].ge(encoder["cutoff"]).all():
        raise ValueError("Context rows precede encoder cutoff")
    out = df.copy()
    for name, specification in encoder["columns"].items():
        if name not in out:
            raise ValueError(f"Missing feature column: {name}")
        values = out[name].fillna("<missing>")
        out[f"{name}_frequency"] = values.map(specification["frequency"]).fillna(0.0)
        out[f"{name}_unknown"] = ~values.isin(specification["frequency"])
        for i, category in enumerate(specification["vocabulary"]):
            out[f"{name}_onehot_{i}"] = values.eq(category)
    return out


def time_features(df):
    """Product age starts at its first observed event in the supplied history."""
    _require(df, ["timestamp", "parent_asin"])
    out = df.copy()
    dates = pd.to_datetime(out["timestamp"], unit="ms", utc=True, errors="raise")
    first = out.groupby("parent_asin")["timestamp"].transform("min")
    out["review_year"] = dates.dt.year
    out["review_quarter"] = dates.dt.quarter
    out["product_age_days"] = (out["timestamp"] - first) / 86400000
    return out


def interaction_features(df):
    _require(df, ["rating", "unnegated_cue", "body_part_mention"])
    out = df.copy()
    out["rating_x_cue"] = out["rating"] * out["unnegated_cue"]
    out["body_x_cue"] = out["body_part_mention"] & out["unnegated_cue"]
    return out

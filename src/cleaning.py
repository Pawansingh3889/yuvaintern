"""Stream the beauty review release without changing its raw files.

Run with CLEANING_SALT set to a private secret of at least 32 characters:
    python -m src.cleaning RAW.jsonl.gz data/processed --chunksize 100000
"""

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unicodedata
from html import unescape

import numpy as np
import pandas as pd


REQUIRED = {
    "asin",
    "rating",
    "text",
    "title",
    "parent_asin",
    "user_id",
    "timestamp",
    "helpful_vote",
}
WINDOW_START = pd.Timestamp("1996-05-01", tz="UTC")
WINDOW_END = pd.Timestamp("2023-10-01", tz="UTC")
BURST_THRESHOLD = 10
ENGLISH = r"(?i)\b(?:the|and|is|it|this|that|with|for|my|was|not|no|very|have|but|of|to|a|i|on|in|great|good|love|nice|works|perfect|excellent)\b"
OTHER = r"(?i)\b(?:el|la|los|las|muy|pero|para|una|que|con|le|les|une|avec|pas|mais|est|der|die|das|und|nicht|ist|mit|nao|não|uma|muito|produto)\b"
NEGATION = r"(?i)\b(?:no|not|never|without)\b|n['’]t\b"
VIDEO = r"(?i)\[\[VIDEOID[^\]]*\]\]"
BREAK = r"(?i)<br\s*/?>"
RECALL_FRIEND = r"(?i)\b(?:(?:i|we|can|cannot|can't|don't|not)\s+(?:can\s+|quite\s+|really\s+)?recall|recall(?:ed)?\s+(?:using|buying|having|when|the last))\b"
EXPIRED_FRIEND = r"(?i)\b(?:return|refund|returning)\b.{0,50}\bexpir(?:ed|es|y)\b|\bexpir(?:ed|es|y)\b.{0,50}\b(?:return|refund|returning)\b"
STEPS = [
    "schema",
    "decode_html",
    "normalise",
    "missing",
    "duplicates",
    "outliers",
    "language",
    "utc_dates",
    "catalogue",
    "pseudonymise",
    "domain_flags",
]


def validate_schema(df):
    """Reject invalid required data with counts, never row contents."""
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}; rows={len(df)}")
    df = df.copy()
    invalid = {}
    for name in ("rating", "timestamp", "helpful_vote"):
        numeric = pd.to_numeric(df[name], errors="coerce")
        bad = numeric.isna() | ~np.isfinite(numeric) | numeric.mod(1).ne(0)
        if name == "rating":
            bad |= ~numeric.between(1, 5)
        elif name == "helpful_vote":
            bad |= numeric.lt(0)
        else:
            bad |= pd.to_datetime(numeric, unit="ms", utc=True, errors="coerce").isna()
        if bad.any():
            invalid[name] = int(bad.sum())
        else:
            df[name] = numeric.astype("int64")
    for name in ("asin", "parent_asin", "user_id"):
        bad = ~df[name].map(lambda x: isinstance(x, str) and bool(x.strip()))
        if bad.any():
            invalid[name] = int(bad.sum())
    for name in ("text", "title"):
        bad = df[name].notna() & ~df[name].map(lambda x: isinstance(x, str))
        if bad.any():
            invalid[name] = int(bad.sum())
    if invalid:
        raise ValueError(
            f"Schema violations (counts by field): {invalid}; rows={len(df)}"
        )
    return df


def decode_html(df):
    df = df.copy()
    df["missing_title"] = df["title"].isna() | df["title"].fillna("").str.strip().eq("")
    df["html_changed"] = False
    for name in ("text", "title"):
        source = df[name].fillna("").astype("str")
        cleaned = (
            source.map(unescape)
            .str.replace(BREAK, " ", regex=True)
            .str.replace(VIDEO, " ", regex=True)
        )
        df["html_changed"] |= source.ne(cleaned)
        df[name] = cleaned
    return df


def normalise_text(df):
    df = df.copy()
    df["normalisation_changed"] = False
    for name in ("text", "title"):
        source = df[name]
        cleaned = source.map(
            lambda x: " ".join(unicodedata.normalize("NFC", x).split())
        )
        df["normalisation_changed"] |= source.ne(cleaned)
        df[name] = cleaned
    return df


def flag_missing(df):
    df = df.copy()
    df["missing_title"] |= df["title"].eq("")
    df["word_count"] = df["text"].str.count(r"\S+").astype("int64")
    df["is_empty"] = df["word_count"].eq(0)
    df["is_short"] = df["word_count"].lt(3)
    return df


def _digest(parts):
    return hashlib.sha256(
        json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()
    ).digest()


def remove_duplicates(df, drop_rows=None, cross_texts=None, repeated_keys=None):
    """Keep the first normalised product/title/text tuple; flag other repetition."""
    df = df.copy()
    if cross_texts is None:
        products = df.loc[df["text"].ne("")].groupby("text")["parent_asin"].nunique()
        df["dup_cross_product"] = df["text"].isin(products[products.gt(1)].index)
    else:
        df["dup_cross_product"] = df["_text_hash"].isin(cross_texts) & ~df["is_empty"]
    if repeated_keys is None:
        df["repeated_review_key"] = df.duplicated(
            ["user_id", "asin", "timestamp"], keep=False
        )
    else:
        df["repeated_review_key"] = df["_key_hash"].isin(repeated_keys)
    if drop_rows is None:
        return df.drop_duplicates(["parent_asin", "title", "text"], keep="first")
    return df.loc[~df["_row_id"].isin(drop_rows)].copy()


def flag_outliers(df, limits=None, burst_days=None):
    df = df.copy()
    log_length = np.log1p(df["word_count"])
    if limits is None:
        q1, q3 = log_length.quantile([0.25, 0.75])
        limits = {
            "length_lower": q1 - 1.5 * (q3 - q1),
            "length_upper": q3 + 1.5 * (q3 - q1),
            "helpful_upper": df["helpful_vote"].quantile(0.999),
        }
    df["length_outlier"] = (log_length < limits["length_lower"]) | (
        log_length > limits["length_upper"]
    )
    df["helpful_log1p"] = np.log1p(df["helpful_vote"])
    df["helpful_outlier"] = df["helpful_vote"].gt(limits["helpful_upper"])
    dates = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    if burst_days is None:
        counts = df.groupby([df["user_id"], dates.dt.floor("D")])[
            "timestamp"
        ].transform("size")
        df["reviewer_burst"] = counts.ge(BURST_THRESHOLD)
    else:
        df["reviewer_burst"] = df["_day_hash"].isin(burst_days)
    df["timestamp_outside_window"] = dates.lt(WINDOW_START) | dates.ge(WINDOW_END)
    return df


def identify_language(df):
    """A transparent proxy, not a validated language detector or exclusion rule."""
    df = df.copy()
    # Arrow's regex engine treats \w as ASCII; use Python for Unicode letters.
    letters = df["text"].astype(pd.StringDtype(storage="python")).str.count(r"[^\W\d_]")
    df["ascii_letter_ratio"] = (
        df["text"].str.count(r"[A-Za-z]").div(letters.replace(0, np.nan)).fillna(0)
    )
    english = df["text"].str.count(ENGLISH)
    other = df["text"].str.count(OTHER)
    df["language"] = "unknown"
    nonempty = letters.gt(0)
    nonenglish = nonempty & (
        df["ascii_letter_ratio"].lt(0.5) | (other.ge(2) & english.lt(2))
    )
    english_like = (
        nonempty & df["ascii_letter_ratio"].ge(0.9) & english.ge(1) & ~nonenglish
    )
    df.loc[english_like, "language"] = "likely_en"
    df.loc[nonenglish, "language"] = "likely_non_en"
    df["language_non_english"] = df["language"].eq("likely_non_en")
    df["language_unknown"] = df["language"].eq("unknown")
    return df


def derive_dates(df):
    df = df.copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["utc_date"] = df["timestamp_utc"].dt.strftime("%Y-%m-%d")
    df["year"] = df["timestamp_utc"].dt.year
    df["quarter"] = (
        df["year"].astype("str") + "Q" + df["timestamp_utc"].dt.quarter.astype("str")
    )
    return df


def normalise_catalogue(df):
    df = df.copy()
    if (
        "parent_asin" not in df
        or df["parent_asin"].isna().any()
        or df["parent_asin"].duplicated().any()
    ):
        raise ValueError("Catalogue requires unique non-null parent_asin values")
    if (
        not df["parent_asin"]
        .map(lambda x: isinstance(x, str) and bool(x.strip()))
        .all()
    ):
        raise ValueError("Invalid catalogue parent_asin")
    for name in ("title", "store", "main_category"):
        if name not in df:
            df[name] = pd.Series(pd.NA, index=df.index, dtype="str")
        if (df[name].notna() & ~df[name].map(lambda x: isinstance(x, str))).any():
            raise ValueError(f"Invalid catalogue field type: {name}")
        df[name] = df[name].astype("str").str.strip().replace("", pd.NA)
    df = df.rename(
        columns={
            "title": "catalogue_title",
            "store": "catalogue_store",
            "main_category": "catalogue_category",
        }
    )
    titles = (
        df["catalogue_title"]
        .fillna("")
        .map(lambda x: " ".join(unicodedata.normalize("NFC", unescape(x)).split()))
    )
    df["catalogue_title_normalized"] = titles
    size = titles.str.extract(
        r"(?i)\b(\d+(?:\.\d+)?)\s*(ml|millilit(?:er|re)s?|fl\.?\s*oz\.?|fluid ounces?|g|grams?)\b"
    )
    value = pd.to_numeric(size[0], errors="coerce")
    unit = size[1].str.lower()
    df["quantity_ml"] = value.where(unit.str.match(r"ml|millilit", na=False))
    ounces = unit.str.match(r"fl|fluid", na=False)
    df.loc[ounces, "quantity_ml"] = value[ounces] * 29.5735295625
    df["quantity_g"] = value.where(unit.str.match(r"g", na=False))
    df["shade"] = titles.str.extract(
        r"(?i)\bshade\s*[:#-]?\s*([\w]+(?:\s+[\w]+)?)", expand=False
    ).str.casefold()
    return df[
        [
            "parent_asin",
            "catalogue_title",
            "catalogue_store",
            "catalogue_category",
            "catalogue_title_normalized",
            "quantity_ml",
            "quantity_g",
            "shade",
        ]
    ]


def join_catalogue(df, catalogue):
    df = df.merge(
        catalogue, on="parent_asin", how="left", validate="many_to_one", indicator=True
    )
    df["catalogue_unmatched"] = df.pop("_merge").eq("left_only")
    df["catalogue_missing_fields"] = (
        df[["catalogue_title", "catalogue_store", "catalogue_category"]]
        .isna()
        .any(axis=1)
    )
    return df


def _salt():
    salt = os.environ.get("CLEANING_SALT")
    if salt is None or len(salt) < 32:
        raise ValueError("CLEANING_SALT must contain at least 32 private characters")
    return salt.encode()


def pseudonymise(df):
    salt = _salt()
    df = df.copy()
    df["user_hash"] = df["user_id"].map(
        lambda x: hmac.digest(salt, x.encode(), "sha256").hex()
    )
    if "_key_hash" in df:
        df["review_key"] = df["_key_hash"].map(bytes.hex)
    else:
        df["review_key"] = [
            hmac.digest(
                salt,
                json.dumps([u, p, int(t)], separators=(",", ":")).encode(),
                "sha256",
            ).hex()
            for u, p, t in zip(df["user_id"], df["asin"], df["timestamp"])
        ]
    return df.drop(columns="user_id")


def flag_domain(df):
    df = df.copy()
    text = df["title"] + " " + df["text"]
    df["has_negation"] = text.str.contains(NEGATION, regex=True)
    df["recall_false_friend"] = text.str.contains(RECALL_FRIEND, regex=True)
    df["expired_return_window"] = text.str.contains(EXPIRED_FRIEND, regex=True)
    return df


def _quantile(histogram, q, transform=lambda x: x):
    """NumPy's linear quantile from an exact integer frequency histogram."""
    values = np.array(sorted(histogram))
    cumulative = np.cumsum([histogram[x] for x in values])
    position = (int(cumulative[-1]) - 1) * q
    lower, upper = int(np.floor(position)), int(np.ceil(position))
    a, b = values[np.searchsorted(cumulative, [lower + 1, upper + 1])]
    return float(transform(a) + (transform(b) - transform(a)) * (position - lower))


def _fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def run(path, out_dir, chunksize=100000):
    """Two disk passes; global SQL groups make results independent of chunksize."""
    if not isinstance(chunksize, int) or chunksize < 1:
        raise ValueError("chunksize must be a positive integer")
    salt = _salt()
    path, out_dir = Path(path), Path(out_dir)
    catalogue_path = path.with_name("meta_" + path.name)
    if not path.is_file() or not catalogue_path.is_file():
        raise FileNotFoundError(
            "Both the review file and its meta_ catalogue are required"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir / "cleaned").exists():
        raise FileExistsError("cleaned/ already exists; use a fresh output directory")
    start = time.monotonic()
    log = {
        name: {"step": name, "rows_in": 0, "rows_out": 0, "rows_flagged": 0}
        for name in STEPS
    }

    def record(name, before, after, flagged):
        log[name]["rows_in"] += before
        log[name]["rows_out"] += after
        log[name]["rows_flagged"] += int(flagged)

    use_parquet = importlib.util.find_spec("pyarrow") is not None
    extension = ".parquet" if use_parquet else ".csv.gz"

    def write(df, file):
        if use_parquet:
            df.to_parquet(file, index=False)
        else:
            df.to_csv(file, index=False, compression={"method": "gzip", "mtime": 0})

    def read(file):
        if use_parquet:
            return pd.read_parquet(file)
        return pd.read_csv(
            file,
            keep_default_na=False,
            dtype={
                "user_id": "str",
                "asin": "str",
                "parent_asin": "str",
                "title": "str",
                "text": "str",
                "_text_hash": "str",
                "_key_hash": "str",
                "_day_hash": "str",
            },
        )

    by_rating = []

    def tally(df, flags, population):
        for rating, group in df.groupby("rating"):
            for flag in flags:
                by_rating.append(
                    {
                        "population": population,
                        "rating": int(rating),
                        "flag": flag,
                        "rows": len(group),
                        "flagged": int(group[flag].sum()),
                    }
                )

    with tempfile.TemporaryDirectory(prefix=".cleaning-work-", dir=out_dir) as temp:
        work = Path(temp)
        (work / "cleaned").mkdir()
        db = sqlite3.connect(work / "audit.sqlite")
        try:
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("PRAGMA cache_size=-131072")
            db.execute(
                "CREATE TABLE audit (id INTEGER PRIMARY KEY, exact BLOB, text_hash BLOB, parent TEXT, review_key BLOB, user_day BLOB, words INTEGER, votes INTEGER, rating INTEGER)"
            )
            total = 0
            stage_files = []
            for chunk_no, df in enumerate(
                pd.read_json(
                    path,
                    lines=True,
                    chunksize=chunksize,
                    convert_dates=False,
                    dtype=False,
                )
            ):
                try:
                    df = validate_schema(df)
                except ValueError:
                    record("schema", len(df), 0, len(df))
                    pd.DataFrame(log.values()).to_csv(
                        out_dir / "cleaning_failure_log.csv", index=False
                    )
                    raise
                record("schema", len(df), len(df), 0)
                df = decode_html(df)
                record("decode_html", len(df), len(df), df["html_changed"].sum())
                df = normalise_text(df)
                record("normalise", len(df), len(df), df["normalisation_changed"].sum())
                df = flag_missing(df)
                record(
                    "missing",
                    len(df),
                    len(df),
                    (df["is_short"] | df["missing_title"]).sum(),
                )
                df = df[
                    sorted(REQUIRED)
                    + [
                        "missing_title",
                        "html_changed",
                        "normalisation_changed",
                        "word_count",
                        "is_empty",
                        "is_short",
                    ]
                ].copy()
                df["_row_id"] = np.arange(total, total + len(df))
                exact = [
                    _digest([p, title, text])
                    for p, title, text in zip(
                        df["parent_asin"], df["title"], df["text"]
                    )
                ]
                text_hash = [_digest([text]) for text in df["text"]]
                keys = [
                    hmac.digest(
                        salt,
                        json.dumps([u, p, int(t)], separators=(",", ":")).encode(),
                        "sha256",
                    )
                    for u, p, t in zip(df["user_id"], df["asin"], df["timestamp"])
                ]
                days = [
                    hmac.digest(
                        salt,
                        json.dumps(
                            [u, int(t) // 86400000], separators=(",", ":")
                        ).encode(),
                        "sha256",
                    )
                    for u, t in zip(df["user_id"], df["timestamp"])
                ]
                db.executemany(
                    "INSERT INTO audit VALUES (?,?,?,?,?,?,?,?,?)",
                    zip(
                        df["_row_id"].tolist(),
                        exact,
                        text_hash,
                        df["parent_asin"],
                        keys,
                        days,
                        df["word_count"].tolist(),
                        df["helpful_vote"].tolist(),
                        df["rating"].tolist(),
                    ),
                )
                for name, hashes in (
                    ("_text_hash", text_hash),
                    ("_key_hash", keys),
                    ("_day_hash", days),
                ):
                    df[name] = [v.hex() for v in hashes]
                file = work / f"stage-{chunk_no:05d}{extension}"
                write(df, file)
                stage_files.append(file)
                total += len(df)
                if chunk_no % 10 == 0:
                    print(f"Staged {total:,} reviews", flush=True)
            if not total:
                raise ValueError("Review input contains no records")
            db.commit()
            print("Computing global duplicate groups", flush=True)
            db.execute("CREATE TABLE kept_ids (id INTEGER PRIMARY KEY)")
            db.execute(
                "INSERT INTO kept_ids SELECT MIN(id) FROM audit GROUP BY exact ORDER BY MIN(id)"
            )
            print("Identifying exact-copy removals", flush=True)
            # shortcut: lookup sets and catalogue use RAM, use SQL joins if larger releases exceed memory.
            drop_rows = {
                r[0]
                for r in db.execute(
                    "SELECT a.id FROM audit a LEFT JOIN kept_ids k ON a.id=k.id WHERE k.id IS NULL"
                )
            }
            print("Finding cross-product repeated text", flush=True)
            cross_texts = {
                r[0].hex()
                for r in db.execute(
                    "SELECT text_hash FROM audit WHERE words > 0 GROUP BY text_hash HAVING COUNT(DISTINCT parent)>1"
                )
            }
            print("Auditing repeated review keys", flush=True)
            repeated_keys = {
                r[0].hex()
                for r in db.execute(
                    "SELECT review_key FROM audit GROUP BY review_key HAVING COUNT(*)>1"
                )
            }
            key_audit = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(n-1),0), COALESCE(SUM(n),0), COALESCE(SUM(variants>1),0) FROM (SELECT COUNT(*) n, COUNT(DISTINCT exact) variants FROM audit GROUP BY review_key HAVING COUNT(*)>1)"
            ).fetchone()
            print("Computing global outlier thresholds", flush=True)
            db.execute(
                "CREATE TABLE retained AS SELECT a.* FROM kept_ids k JOIN audit a ON a.id=k.id"
            )
            burst_days = {
                r[0].hex()
                for r in db.execute(
                    "SELECT user_day FROM retained GROUP BY user_day HAVING COUNT(*)>=?",
                    (BURST_THRESHOLD,),
                )
            }
            lengths = dict(
                db.execute("SELECT words, COUNT(*) FROM retained GROUP BY words")
            )
            votes = dict(
                db.execute("SELECT votes, COUNT(*) FROM retained GROUP BY votes")
            )
            q1, q3 = [_quantile(lengths, q, np.log1p) for q in (0.25, 0.75)]
            limits = {
                "length_lower": q1 - 1.5 * (q3 - q1),
                "length_upper": q3 + 1.5 * (q3 - q1),
                "helpful_upper": _quantile(votes, 0.999),
            }
            print("Reading and normalising catalogue", flush=True)
            catalogue_parts = []
            for part in pd.read_json(
                catalogue_path,
                lines=True,
                chunksize=chunksize,
                convert_dates=False,
                dtype=False,
            ):
                catalogue_parts.append(normalise_catalogue(part))
            if not catalogue_parts:
                raise ValueError("Catalogue input contains no records")
            catalogue = pd.concat(catalogue_parts, ignore_index=True)
            if catalogue["parent_asin"].duplicated().any():
                raise ValueError("Catalogue parent_asin repeats across chunks")
            metrics = {
                "input_rows": total,
                "removed_exact_duplicates": len(drop_rows),
                "retained_rows": total - len(drop_rows),
                "cross_product_text_groups": len(cross_texts),
                "review_key_audit": dict(
                    zip(
                        [
                            "repeated_groups",
                            "excess_rows",
                            "affected_rows",
                            "groups_with_different_content",
                        ],
                        key_audit,
                    )
                ),
                "thresholds": limits,
                "burst_threshold_per_utc_day": BURST_THRESHOLD,
                "catalogue_rows": len(catalogue),
                "language_method": "ASCII letter ratio plus stopword heuristic; no validated language detector",
                "dataset_window": [str(WINDOW_START), str(WINDOW_END)],
                "flag_counts": {},
            }
            flag_names = [
                "is_empty",
                "is_short",
                "missing_title",
                "html_changed",
                "normalisation_changed",
                "dup_cross_product",
                "repeated_review_key",
                "length_outlier",
                "helpful_outlier",
                "reviewer_burst",
                "timestamp_outside_window",
                "language_non_english",
                "language_unknown",
                "catalogue_unmatched",
                "catalogue_missing_fields",
                "has_negation",
                "recall_false_friend",
                "expired_return_window",
            ]
            for chunk_no, file in enumerate(stage_files):
                df = read(file)
                df["exact_duplicate_removed"] = df["_row_id"].isin(drop_rows)
                tally(
                    df,
                    ["exact_duplicate_removed", "is_empty", "is_short"],
                    "before_deduplication",
                )
                before = len(df)
                df = remove_duplicates(df, drop_rows, cross_texts, repeated_keys)
                record(
                    "duplicates",
                    before,
                    len(df),
                    before
                    - len(df)
                    + int((df["dup_cross_product"] | df["repeated_review_key"]).sum()),
                )
                df = flag_outliers(df, limits, burst_days)
                record(
                    "outliers",
                    len(df),
                    len(df),
                    df[
                        [
                            "length_outlier",
                            "helpful_outlier",
                            "reviewer_burst",
                            "timestamp_outside_window",
                        ]
                    ]
                    .any(axis=1)
                    .sum(),
                )
                df = identify_language(df)
                record(
                    "language",
                    len(df),
                    len(df),
                    df[["language_non_english", "language_unknown"]].any(axis=1).sum(),
                )
                df = derive_dates(df)
                record(
                    "utc_dates", len(df), len(df), df["timestamp_outside_window"].sum()
                )
                df = join_catalogue(df, catalogue)
                record(
                    "catalogue", len(df), len(df), df["catalogue_missing_fields"].sum()
                )
                df["_key_hash"] = df["_key_hash"].map(bytes.fromhex)
                df = pseudonymise(df)
                record("pseudonymise", len(df), len(df), len(df))
                df = flag_domain(df)
                record(
                    "domain_flags",
                    len(df),
                    len(df),
                    df[["has_negation", "recall_false_friend", "expired_return_window"]]
                    .any(axis=1)
                    .sum(),
                )
                tally(df, flag_names, "retained")
                for name in flag_names:
                    metrics["flag_counts"][name] = metrics["flag_counts"].get(
                        name, 0
                    ) + int(df[name].sum())
                for name, flag in (
                    (
                        "catalogue_quantity_available",
                        df["quantity_ml"].notna() | df["quantity_g"].notna(),
                    ),
                    ("catalogue_shade_available", df["shade"].notna()),
                ):
                    metrics["flag_counts"][name] = metrics["flag_counts"].get(
                        name, 0
                    ) + int(flag.sum())
                df = df.drop(
                    columns=[name for name in df if name.startswith("_")]
                    + ["exact_duplicate_removed"]
                )
                if not df.empty:
                    write(df, work / "cleaned" / f"part-{chunk_no:05d}{extension}")
                file.unlink()
                if chunk_no % 10 == 0:
                    print(
                        f"Finalised chunk {chunk_no + 1}/{len(stage_files)}", flush=True
                    )
            ratings = (
                pd.DataFrame(by_rating)
                .groupby(["population", "rating", "flag"], as_index=False)[
                    ["rows", "flagged"]
                ]
                .sum()
            )
            ratings["share"] = ratings["flagged"] / ratings["rows"]
            ratings.to_csv(work / "cleaning_flag_by_rating.csv", index=False)
            pd.DataFrame(log.values()).to_csv(work / "cleaning_log.csv", index=False)
            metrics["elapsed_seconds"] = round(time.monotonic() - start, 2)
            metrics["fingerprints"] = [_fingerprint(path), _fingerprint(catalogue_path)]
            metrics["versions"] = {"pandas": pd.__version__, "numpy": np.__version__}
            metrics["output_format"] = "parquet" if use_parquet else "csv.gz"
            metrics["chunksize"] = chunksize
            metrics["salt_policy"] = (
                "CLEANING_SALT from environment; never written; same secret needed for same pseudonyms"
            )
            metrics["randomness"] = (
                "No stochastic step or sampling; heuristic is deterministic"
            )
            (work / "cleaning_metrics.json").write_text(
                json.dumps(metrics, indent=2) + "\n"
            )
            os.replace(work / "cleaned", out_dir / "cleaned")
            for name in (
                "cleaning_log.csv",
                "cleaning_flag_by_rating.csv",
                "cleaning_metrics.json",
            ):
                os.replace(work / name, out_dir / name)
            print(
                f"Finished: {total:,} input, {metrics['retained_rows']:,} retained",
                flush=True,
            )
        finally:
            db.close()
    return pd.read_csv(out_dir / "cleaning_log.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--chunksize", type=int, default=100000)
    args = parser.parse_args()
    run(args.path, args.out_dir, args.chunksize)

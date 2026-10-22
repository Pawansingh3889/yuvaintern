"""Stream cleaned partitions into aggregate-only EDA evidence.

Run: python -m src.eda
Text samples stay in memory; output files contain no review text or identifiers.
"""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from src import features as f


SEED = 42
SAMPLE_SIZE = 40000
CUE_SAMPLE_SIZE = 20000
COLUMNS = [
    "title",
    "text",
    "rating",
    "word_count",
    "helpful_vote",
    "timestamp",
    "parent_asin",
    "user_hash",
    "catalogue_category",
    "catalogue_store",
]


def wilson_interval(successes, totals):
    """Wilson score interval, undefined for periods with no observations."""
    successes, totals = np.asarray(successes), np.asarray(totals)
    if np.any(successes < 0) or np.any(successes > totals) or np.any(totals < 0):
        raise ValueError("Wilson counts require 0 <= successes <= totals")
    n = np.where(totals > 0, totals, np.nan)
    z = stats.norm.ppf(0.975)
    p = successes / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return np.maximum(0, center - half), np.minimum(1, center + half)


def catalogue_price_bands(path):
    """Read snapshot USD prices without retaining other catalogue attributes."""
    prices = {}
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            product = row["parent_asin"]
            if not isinstance(product, str) or not product.strip() or product in prices:
                raise ValueError(
                    "Catalogue requires unique nonempty parent_asin values"
                )
            price = row["price"]
            band = "<missing>"
            if isinstance(price, str) and (
                price == "\u2014" or re.fullmatch(r"from \d+(?:\.\d+)?", price)
            ):
                price = None
            if price is not None:
                if isinstance(price, bool):
                    raise ValueError(
                        "Catalogue price must be a finite nonnegative number"
                    )
                price = float(price)
                if not np.isfinite(price) or price < 0:
                    raise ValueError(
                        "Catalogue price must be a finite nonnegative number"
                    )
                band = (
                    "USD <10"
                    if price < 10
                    else "USD 10 to <25"
                    if price < 25
                    else "USD 25 to <50"
                    if price < 50
                    else "USD >=50"
                )
            prices[product] = band
    if not prices:
        raise ValueError("Catalogue is empty")
    return pd.Series(prices, name="price_band")


def market_trends(monthly, category, category_year, price_band):
    """Calendar seasonality, segment uncertainty and consecutive-year changes."""
    counts = ["reviews", "cue", "unnegated", "negated"]
    calendar = monthly.assign(calendar_month=pd.to_datetime(monthly.month).dt.month)
    calendar = (
        calendar.groupby("calendar_month")[counts]
        .sum()
        .reindex(range(1, 13), fill_value=0)
    )
    calendar["cue_rate"] = calendar.cue.div(calendar.reviews.replace(0, np.nan))
    calendar["unnegated_rate"] = calendar.unnegated.div(
        calendar.reviews.replace(0, np.nan)
    )
    calendar["wilson_low"], calendar["wilson_high"] = wilson_interval(
        calendar.cue, calendar.reviews
    )
    active = calendar.loc[calendar.reviews.gt(0)]
    contingency = np.array([active.cue, active.reviews - active.cue])
    if len(active) < 2 or (contingency.sum(axis=1) == 0).any():
        raise ValueError("Seasonality test requires two months and both cue classes")
    chi2, p, dof, expected = stats.chi2_contingency(contingency, correction=False)
    test = pd.DataFrame(
        [
            {
                "chi_square": chi2,
                "p_value": p,
                "dof": dof,
                "min_expected": expected.min(),
                "cramers_v": np.sqrt(chi2 / contingency.sum()),
                "peak_month": int(active.cue_rate.idxmax()),
                "trough_month": int(active.cue_rate.idxmin()),
            }
        ]
    )
    segments = {}
    for name, table in (("category", category), ("price_band", price_band)):
        table = table.copy()
        table["wilson_low"], table["wilson_high"] = wilson_interval(
            table.cue, table.reviews
        )
        segments[name] = table
    top = (
        category.loc[category.category.ne("<missing>")].nlargest(5, "reviews").category
    )
    years = pd.to_datetime(monthly.month).dt.year
    grid = pd.MultiIndex.from_product(
        [top, range(years.min(), years.max() + 1)], names=["category", "year"]
    )
    annual = (
        category_year.set_index(["category", "year"])[counts]
        .reindex(grid, fill_value=0)
        .reset_index()
    )
    annual["cue_rate"] = annual.cue.div(annual.reviews.replace(0, np.nan))
    annual["prior_year_cue_rate"] = annual.groupby(
        "category", sort=False
    ).cue_rate.shift()
    annual["change_pp"] = 100 * (annual.cue_rate - annual.prior_year_cue_rate)
    annual["interior_year"] = annual.year.gt(years.min()) & annual.year.lt(years.max())
    return {
        "calendar_month": calendar.reset_index(),
        "seasonality_test": test,
        "category_yoy": annual,
        **segments,
    }


def _reservoir(previous, chunk, size, rng):
    chunk = chunk.assign(_priority=rng.random(len(chunk)))
    chunk = chunk.nsmallest(size, "_priority")
    if previous is not None:
        chunk = pd.concat([previous, chunk], ignore_index=True)
    return chunk.nsmallest(size, "_priority").reset_index(drop=True)


def aggregate_partitions(paths, price_bands=None):
    """Count the population; retain bounded uniform random-priority reservoirs."""
    rating, monthly, category = Counter(), Counter(), Counter()
    category_year, price_band = Counter(), Counter()
    lengths, helpful, groups = Counter(), Counter(), Counter()
    sample = cue_sample = None
    timestamp_minima, timestamp_maxima = [], []
    rng, cue_rng = np.random.default_rng(SEED), np.random.default_rng(SEED + 1)
    total = 0
    for i, path in enumerate(paths):
        df = pq.read_table(path, columns=COLUMNS).to_pandas()
        df = f.safety_features(df)
        total += len(df)
        timestamp_minima.append(int(df.timestamp.min()))
        timestamp_maxima.append(int(df.timestamp.max()))
        dates = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["month"] = (
            dates.dt.year.astype(str) + "-" + dates.dt.month.astype(str).str.zfill(2)
        )
        df["category"] = df["catalogue_category"].fillna("<missing>")
        df["category_year"] = list(zip(dates.dt.year, df["category"]))
        df["price_band"] = (
            df.parent_asin.map(price_bands).fillna("<missing>")
            if price_bands is not None
            else "<missing>"
        )
        for key, counter in (
            ("rating", rating),
            ("month", monthly),
            ("category", category),
            ("category_year", category_year),
            ("price_band", price_band),
        ):
            table = df.groupby(key).agg(
                reviews=("rating", "size"),
                cue=("safety_cue", "sum"),
                unnegated=("unnegated_cue", "sum"),
                negated=("negated_cue", "sum"),
            )
            for name, row in table.iterrows():
                for metric in table:
                    counter[(name, metric)] += int(row[metric])
        lengths.update(df["word_count"].value_counts().to_dict())
        helpful.update(df["helpful_vote"].value_counts().to_dict())
        for name in f.WORD_GROUPS:
            groups[(name, "cue")] += int(df[f"{name}_count"].gt(0).sum())
            groups[(name, "unnegated")] += int(
                df[f"{name}_unnegated_count"].gt(0).sum()
            )
        sample = _reservoir(sample, df, SAMPLE_SIZE, rng)
        cue_sample = _reservoir(
            cue_sample, df.loc[df.safety_cue], CUE_SAMPLE_SIZE, cue_rng
        )
        if (i + 1) % 20 == 0 or i + 1 == len(paths):
            print(f"Partitions {i + 1}/{len(paths)}; reviews {total:,}", flush=True)
    if total == 0:
        raise ValueError("No cleaned reviews found")

    def table(counter, key):
        result = pd.Series(counter).unstack().rename_axis(key).reset_index()
        result["cue_rate"] = result["cue"] / result["reviews"]
        result["unnegated_rate"] = result["unnegated"] / result["reviews"]
        return result

    outputs = {
        "rating": table(rating, "rating"),
        "monthly": table(monthly, "month"),
        "category": table(category, "category"),
        "price_band": table(price_band, "price_band"),
    }
    annual = table(category_year, "category_year")
    annual[["year", "category"]] = pd.DataFrame(
        annual.pop("category_year").tolist(), index=annual.index
    )
    outputs["category_year"] = annual
    months = outputs["monthly"].set_index("month")
    complete = pd.period_range(months.index.min(), months.index.max(), freq="M").astype(
        str
    )
    months = months.reindex(complete)
    for column in ("reviews", "cue", "negated", "unnegated"):
        months[column] = months[column].fillna(0).astype("int64")
    months["cue_rate"] = months["cue"].div(months["reviews"].replace(0, np.nan))
    months["unnegated_rate"] = months["unnegated"].div(
        months["reviews"].replace(0, np.nan)
    )
    months["wilson_low"], months["wilson_high"] = wilson_interval(
        months["unnegated"], months["reviews"]
    )
    outputs["monthly"] = months.rename_axis("month").reset_index()
    outputs["category"] = outputs["category"].sort_values("reviews", ascending=False)
    for name, counts in (("length", lengths), ("helpful", helpful)):
        outputs[name] = (
            pd.Series(counts).sort_index().rename_axis(name).reset_index(name="reviews")
        )
    outputs["groups"] = pd.DataFrame(
        [
            {
                "group": name,
                "reviews": total,
                "cue": groups[(name, "cue")],
                "unnegated": groups[(name, "unnegated")],
                "cue_rate": groups[(name, "cue")] / total,
                "unnegated_rate": groups[(name, "unnegated")] / total,
            }
            for name in f.WORD_GROUPS
        ]
    )
    outputs["coverage"] = pd.DataFrame(
        {
            "first_review_ms": [min(timestamp_minima)],
            "last_review_ms": [max(timestamp_maxima)],
        }
    )
    assert outputs["rating"].reviews.sum() == outputs["monthly"].reviews.sum() == total
    assert outputs["category"].reviews.sum() == total
    return (
        outputs,
        sample.drop(columns="_priority"),
        cue_sample.drop(columns="_priority"),
    )


def sample_analysis(sample, cue_sample, scaling, rating):
    """Pairwise statistics and target-free features on fixed-size samples."""
    engineered = f.rating_text_features(sample)
    engineered = f.text_shape_features(engineered, scaling)
    # shortcut: histories cover this sample only, use complete earlier events for modeling.
    engineered = f.history_features(engineered)
    engineered = f.time_features(engineered)
    engineered = f.interaction_features(engineered)
    cutoff = int(engineered.timestamp.quantile(0.5, interpolation="nearest"))
    reference = engineered.loc[engineered.timestamp.lt(cutoff)]
    encoder = f.fit_context_encoder(reference, cutoff)
    evaluated = f.context_features(
        engineered.loc[engineered.timestamp.ge(cutoff)], encoder
    )
    proxy = evaluated.unnegated_cue & evaluated.rating.le(2)
    if proxy.nunique() != 2:
        raise ValueError("Feature relevance requires both proxy classes")
    new_columns = [column for column in evaluated if column not in sample]
    new_columns += ["safety_cue", "unnegated_cue", "negated_cue"]
    new_columns += [
        name for name in sample if name.endswith("_count") and name != "word_count"
    ]
    rows = []
    for name in new_columns:
        values = evaluated[name]
        if not pd.api.types.is_numeric_dtype(values) and values.dtype != bool:
            continue
        valid = values.notna()
        association = None
        if values[valid].nunique() > 1 and proxy[valid].nunique() > 1:
            association = float(
                stats.pointbiserialr(
                    proxy[valid].astype(int), values[valid].astype(float)
                ).statistic
            )
        rows.append(
            {
                "feature": name,
                "n": int(valid.sum()),
                "point_biserial_r": association,
                "proxy_derived": name
                in {
                    "safety_cue",
                    "unnegated_cue",
                    "negated_cue",
                    "rating_x_cue",
                    "rating_text_mismatch",
                    "body_x_cue",
                }
                or name.startswith(tuple(f.WORD_GROUPS)),
            }
        )
    relevance = pd.DataFrame(rows).sort_values(
        "point_biserial_r", key=lambda s: s.abs(), ascending=False
    )
    numeric = [
        "rating",
        "length_scaled",
        "exclamation_share",
        "capitals_share",
        "body_part_mention",
        "unnegated_cue",
        "rating_text_mismatch",
        "product_age_days",
        "review_year",
        "reviewer_prior_count",
        "product_prior_count",
        "catalogue_store_frequency",
    ]
    spearman = evaluated[numeric].astype(float).corr(method="spearman")
    lengths_cue = sample.loc[sample.safety_cue, "word_count"]
    lengths_other = sample.loc[~sample.safety_cue, "word_count"]
    if lengths_cue.empty or lengths_other.empty:
        raise ValueError("Length comparison requires cue and non-cue reviews")
    u = stats.mannwhitneyu(
        lengths_cue, lengths_other, alternative="two-sided", method="asymptotic"
    )
    contingency = np.array([rating.cue, rating.reviews - rating.cue])
    chi2, p, dof, expected = stats.chi2_contingency(contingency, correction=False)
    vectorizer = TfidfVectorizer(
        min_df=3, max_df=0.98, max_features=5000, ngram_range=(1, 2), sublinear_tf=True
    )
    matrix = vectorizer.fit_transform(cue_sample.title + " " + cue_sample.text)
    svd = TruncatedSVD(n_components=2, random_state=SEED)
    coordinates = svd.fit_transform(matrix)
    group_counts = cue_sample[[f"{name}_count" for name in f.WORD_GROUPS]]
    dominant = group_counts.idxmax(axis=1).str.removesuffix("_count")
    projection = pd.DataFrame(
        {
            "component_1": coordinates[:, 0],
            "component_2": coordinates[:, 1],
            "group": dominant,
        }
    )
    projection = projection.sample(min(2500, len(projection)), random_state=SEED)
    summaries = {
        "seed": SEED,
        "sample_size": len(sample),
        "cue_sample_seed": SEED + 1,
        "cue_sample_size": len(cue_sample),
        "relevance_size": len(evaluated),
        "relevance_proxy_positives": int(proxy.sum()),
        "encoder_cutoff_ms": cutoff,
        "chi_square": float(chi2),
        "chi_square_p": float(p),
        "chi_square_dof": int(dof),
        "chi_square_min_expected": float(expected.min()),
        "cramers_v": float(np.sqrt(chi2 / contingency.sum())),
        "mann_whitney_u": float(u.statistic),
        "mann_whitney_p": float(u.pvalue),
        "rank_biserial": float(
            2 * u.statistic / (len(lengths_cue) * len(lengths_other)) - 1
        ),
        "length_cue_n": len(lengths_cue),
        "length_other_n": len(lengths_other),
        "length_cue_median": float(lengths_cue.median()),
        "length_other_median": float(lengths_other.median()),
        "svd_explained_variance": svd.explained_variance_ratio_.tolist(),
        "svd_vocabulary_size": len(vectorizer.vocabulary_),
        "sample_reviewer_cold_start_share": float(
            engineered.reviewer_cold_start.mean()
        ),
        "sample_product_cold_start_share": float(engineered.product_cold_start.mean()),
        "five_star_mismatch_sample": int(engineered.rating_text_mismatch.sum()),
        "scaling": scaling,
        "context_encoder": encoder,
    }
    return {
        "feature_relevance": relevance,
        "spearman": spearman,
        "svd": projection,
    }, summaries


def run(input_dir, output_dir, metrics_path, catalogue_path):
    paths = sorted(Path(input_dir).glob("part-*.parquet"))
    if not paths:
        raise FileNotFoundError(f"No cleaned parquet partitions in {input_dir}")
    metrics = json.loads(Path(metrics_path).read_text())
    outputs, sample, cue_sample = aggregate_partitions(
        paths, catalogue_price_bands(catalogue_path)
    )
    outputs.update(
        market_trends(
            outputs["monthly"],
            outputs["category"],
            outputs["category_year"],
            outputs["price_band"],
        )
    )
    rows = int(outputs["rating"].reviews.sum())
    if rows != metrics["retained_rows"]:
        raise ValueError("EDA population does not reconcile with cleaning metrics")
    extra, summary = sample_analysis(
        sample, cue_sample, metrics["numeric_scaling"], outputs["rating"]
    )
    summary.update(
        {
            "population_rows": rows,
            "partitions": len(paths),
            "cue_reviews": int(outputs["rating"].cue.sum()),
            "unnegated_reviews": int(outputs["rating"].unnegated.sum()),
            "negated_reviews": int(outputs["rating"].negated.sum()),
            "verified_purchase_available": False,
            "history_scope": "40,000-review uniform sample, not complete user or product histories",
            "catalogue_timing": "Snapshot metadata lacks effective dates; context requires historical metadata before predictive use",
        }
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, table in {**outputs, **extra}.items():
        table.to_csv(output_dir / f"{name}.csv", index=name == "spearman")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    print(f"Saved aggregate-only evidence to {output_dir}", flush=True)


def plot_aggregates(directory, output_dir=None):
    """Draw the notebook/report figures exclusively from saved aggregate files."""
    import importlib.util

    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    directory = Path(directory)
    tables = {
        name: pd.read_csv(directory / f"{name}.csv")
        for name in (
            "rating",
            "length",
            "helpful",
            "groups",
            "category",
            "monthly",
            "svd",
            "feature_relevance",
            "calendar_month",
            "price_band",
            "category_yoy",
        )
    }
    figures = {}
    ink, orange, green = "#1F3A4D", "#C76826", "#5B8975"
    with plt.rc_context(
        {"font.size": 9, "axes.spines.top": False, "axes.spines.right": False}
    ):
        fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.4))
        rating = tables["rating"]
        axes[0].bar(rating.rating, rating.reviews / rating.reviews.sum(), color=ink)
        axes[0].set(
            xlabel="Star rating (stars)",
            ylabel="Share of all reviews",
            title="Rating mix",
        )
        for ax, name, label in zip(
            axes[1:], ["length", "helpful"], ["review length in words", "helpful votes"]
        ):
            table = tables[name]
            ax.hist(
                np.log1p(table[name]),
                bins=35,
                weights=table.reviews / table.reviews.sum(),
                color=ink,
            )
            ax.set(
                xlabel=f"log(1 + {label})",
                ylabel="Share of all reviews per bin",
                title=label.capitalize(),
            )
        for ax in axes:
            ax.yaxis.set_major_formatter(PercentFormatter(1))
        figures["univariate"] = fig

        fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.7))
        axes[0].plot(rating.rating, rating.cue_rate, "o-", color=ink, label="Any cue")
        axes[0].plot(
            rating.rating,
            rating.unnegated_rate,
            "s-",
            color=orange,
            label="Unnegated cue",
        )
        axes[0].set(
            xlabel="Star rating (stars)",
            ylabel="Share of reviews at this rating",
            title="Safety words by rating",
        )
        axes[0].legend(frameon=False)
        both = rating.negated + rating.unnegated - rating.cue
        bottom = np.zeros(len(rating))
        for count, label, color in (
            (rating.cue - rating.unnegated, "Negated only", green),
            (both, "Mixed mentions", orange),
            (rating.cue - rating.negated, "Unnegated only", ink),
        ):
            share = count / rating.cue
            axes[1].bar(rating.rating, share, bottom=bottom, label=label, color=color)
            bottom += share
        axes[1].set(
            xlabel="Star rating (stars)",
            ylabel="Share of cue reviews at this rating",
            title="Scope of the matched mentions",
        )
        axes[1].set_ylim(0, 1.25)
        axes[1].set_yticks(np.arange(0, 1.01, 0.2))
        axes[1].legend(frameon=False, fontsize=7, loc="upper center", ncol=2)
        for ax in axes:
            ax.set_xticks([1, 2, 3, 4, 5])
            ax.yaxis.set_major_formatter(PercentFormatter(1))
        figures["rating_cues"] = fig

        for name, key, title in (
            ("groups", "group", "Safety-word groups"),
            ("category", "category", "Top categories by review volume"),
        ):
            table = tables[name].head(10).iloc[::-1]
            fig, ax = plt.subplots(figsize=(7.6, 3.7))
            labels = table[key].str.replace("_", " ").str.slice(0, 35)
            ax.barh(
                np.arange(len(table)) - 0.17,
                table.cue_rate,
                xerr=np.array(
                    [
                        np.maximum(0, table.cue_rate - table.wilson_low),
                        np.maximum(0, table.wilson_high - table.cue_rate),
                    ]
                )
                if name == "category"
                else None,
                height=0.33,
                color=ink,
                label="Any cue",
            )
            ax.barh(
                np.arange(len(table)) + 0.17,
                table.unnegated_rate,
                height=0.33,
                color=orange,
                label="Unnegated cue",
            )
            ax.set_yticks(np.arange(len(table)), labels)
            denominator = (
                "all reviews" if name == "groups" else "reviews in this category"
            )
            ax.set(
                xlabel=f"Share of {denominator}",
                ylabel="Word group" if name == "groups" else "Catalogue main category",
                title=title,
            )
            ax.xaxis.set_major_formatter(PercentFormatter(1))
            ax.legend(frameon=False, loc="lower right", fontsize=8)
            if name == "category":
                ax.set_xlim(0, table.cue_rate.max() * 1.5)
            figures[name] = fig

        monthly = tables["monthly"]
        dates = pd.to_datetime(monthly.month)
        fig, axes = plt.subplots(2, 1, figsize=(8.6, 5.2), sharex=True)
        axes[0].plot(dates, monthly.reviews, color=ink)
        axes[0].set(
            xlabel="Review month (UTC calendar month)",
            ylabel="Review count (reviews/month)",
            title="Monthly volume and unnegated cue rate",
        )
        axes[1].plot(dates, monthly.unnegated_rate, color=orange, label="Unnegated cue")
        axes[1].fill_between(
            dates,
            monthly.wilson_low,
            monthly.wilson_high,
            color=orange,
            alpha=0.2,
            label="Wilson 95% interval",
        )
        axes[1].set(
            xlabel="Review month (UTC calendar month)",
            ylabel="Share of reviews in this month",
        )
        axes[1].yaxis.set_major_formatter(PercentFormatter(1))
        axes[1].legend(frameon=False)
        figures["monthly"] = fig

        fig, axes = plt.subplots(2, 2, figsize=(11, 7.2))
        calendar = tables["calendar_month"]
        axes[0, 0].bar(calendar.calendar_month, calendar.reviews, color=ink)
        axes[0, 0].set(
            xlabel="Calendar month (January=1)",
            ylabel="Reviews across years (count)",
            title="Seasonal review volume",
        )
        axes[0, 1].plot(calendar.calendar_month, calendar.cue_rate, "o-", color=orange)
        axes[0, 1].fill_between(
            calendar.calendar_month,
            calendar.wilson_low,
            calendar.wilson_high,
            color=orange,
            alpha=0.2,
        )
        axes[0, 1].set(
            xlabel="Calendar month (January=1)",
            ylabel="Share of reviews in calendar month",
            title="Any-cue rate and Wilson 95% interval",
        )
        for ax in axes[0]:
            ax.set_xticks(range(1, 13))
        price = (
            tables["price_band"]
            .set_index("price_band")
            .reindex(
                ["USD <10", "USD 10 to <25", "USD 25 to <50", "USD >=50", "<missing>"]
            )
            .dropna(subset=["reviews"])
        )
        axes[1, 0].barh(
            price.index,
            price.cue_rate,
            color=ink,
            xerr=np.array(
                [
                    np.maximum(0, price.cue_rate - price.wilson_low),
                    np.maximum(0, price.wilson_high - price.cue_rate),
                ]
            ),
        )
        axes[1, 0].set(
            xlabel="Share of reviews in price band",
            ylabel="Snapshot catalogue price (USD)",
            title="Price mix and Wilson 95% interval",
        )
        annual = tables["category_yoy"]
        annual = annual.loc[annual.interior_year]
        annual = annual.loc[annual.year.ge(annual.year.max() - 9)]
        for name, group in annual.loc[annual.interior_year].groupby(
            "category", sort=False
        ):
            axes[1, 1].plot(group.year, group.cue_rate, label=name[:30])
        axes[1, 1].set(
            xlabel="Review year (latest ten interior years)",
            ylabel="Share of reviews in category/year",
            title="Five largest categories by review volume",
        )
        axes[1, 1].legend(frameon=False, fontsize=6)
        for ax in (axes[0, 1], axes[1, 0], axes[1, 1]):
            (ax.xaxis if ax is axes[1, 0] else ax.yaxis).set_major_formatter(
                PercentFormatter(1)
            )
        figures["market_trends"] = fig

        correlations = pd.read_csv(directory / "spearman.csv", index_col=0)
        fig, ax = plt.subplots(figsize=(9.2, 7.3))
        if importlib.util.find_spec("seaborn"):
            import seaborn as sns

            sns.heatmap(
                correlations,
                ax=ax,
                vmin=-1,
                vmax=1,
                center=0,
                cmap="BrBG",
                annot=True,
                fmt=".2f",
                annot_kws={"fontsize": 6},
                cbar_kws={"label": "Spearman rank correlation"},
            )
        else:
            mesh = ax.imshow(correlations, vmin=-1, vmax=1, cmap="BrBG")
            ax.set_xticks(range(len(correlations)), correlations.columns, rotation=90)
            ax.set_yticks(range(len(correlations)), correlations.index)
            fig.colorbar(mesh, ax=ax, label="Spearman rank correlation")
        ax.set(
            xlabel="Numeric review feature",
            ylabel="Numeric review feature",
            title="Numeric feature relationships (sample)",
        )
        figures["spearman"] = fig

        fig, ax = plt.subplots(figsize=(7.6, 4.0))
        for name, group in tables["svd"].groupby("group"):
            ax.scatter(
                group.component_1,
                group.component_2,
                s=7,
                alpha=0.35,
                label=name.replace("_", " "),
            )
        ax.set(
            xlabel="TF-IDF SVD component 1 (unitless)",
            ylabel="TF-IDF SVD component 2 (unitless)",
            title="Cue-review text projection",
        )
        ax.legend(frameon=False, fontsize=7, loc="upper right")
        figures["svd"] = fig

        relevance = tables["feature_relevance"].dropna(subset=["point_biserial_r"])
        table = (
            pd.concat(
                [
                    relevance.loc[relevance.proxy_derived].head(5),
                    relevance.loc[~relevance.proxy_derived].head(5),
                ]
            )
            .sort_values("point_biserial_r", key=lambda s: s.abs())
            .reset_index(drop=True)
        )
        fig, ax = plt.subplots(figsize=(8.7, 4.2))
        labels = (
            table.feature
            + np.where(table.proxy_derived, " *", "")
            + " (n="
            + table.n.astype(str)
            + ")"
        )
        ax.barh(
            labels,
            table.point_biserial_r,
            color=np.where(table.proxy_derived, orange, ink),
        )
        ax.set(
            xlabel="Point-biserial r with weak proxy (unitless)",
            ylabel="Engineered feature (* proxy-linked)",
            title="Engineered feature associations",
        )
        figures["relevance"] = fig

        for name, fig in figures.items():
            fig.tight_layout()
            if output_dir is not None:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                fig.savefig(Path(output_dir) / f"{name}.png", dpi=180)
    return figures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/cleaned"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/eda"))
    parser.add_argument(
        "--metrics", type=Path, default=Path("data/processed/cleaning_metrics.json")
    )
    parser.add_argument(
        "--catalogue",
        type=Path,
        default=Path(
            "data/raw/amazon_reviews_2023/meta_Beauty_and_Personal_Care.jsonl.gz"
        ),
    )
    args = parser.parse_args()
    run(args.input, args.output, args.metrics, args.catalogue)

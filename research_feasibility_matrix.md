# Research feasibility matrix

Can each research question be answered with public data inside six weeks? Assessed on 11 October 2026 from simple counts on the candidate data. No model was trained.

Ratings: **High** means the data is in hand and sufficient. **Medium** means it depends on work not yet done. **Low** means the data cannot support a firm test.

## Matrix

| RQ | Question | Data needed | Data available | Evidence so far | Main blocker | Feasibility | Decision |
|---|---|---|---|---|---|---|---|
| RQ1 | Can people label safety complaints consistently? | Review text; two annotators; a guideline | 23.9M reviews in hand | 614,203 reviews contain a safety-related word; informal read found about 1 in 5 genuine | A second annotator has not been confirmed | Medium | Core. Pilot of 50 in Week 2 |
| RQ2 | Does a classifier beat a keyword search? | At least 500 labelled reviews with about 60 positives or more | Depends on RQ1 | Keyword hits are mostly not complaints, so there is room to improve on the baseline | Positive cases are rare | Medium | Core. Needs the annotation milestone |
| RQ3 | Can weak supervision reduce hand labelling? | Labelling functions; hand labels to check them | Reviews, star ratings, FDA reaction terms | 46% of keyword hits are in five-star reviews, so rating and negation rules should add information | Unknown until rules are measured against hand labels | Medium | Core. Runs before modelling |
| RQ4 | Do complaint rates rise before a recall? | Recalled products with dated earlier reviews, plus comparison products | 40 recalled lines listed; Amazon reviews to September 2023 | 8 lines have at least 20 reviews in the 12 months before recall; only 1 microbial line has volume | Too few qualifying products; no batch link | Low | Exploratory. Descriptive comparison and one case study |
| RQ5 | Can a flagged product be traced to the right official record? | Reviewed product and notice pairs with attributes | 296 French notices; 64,237 catalogue records | 30 barcode-linked products, 17 with names; one documented wrong-size match | Few pairs; reviews have no batch number | Low | Exploratory. Batch tracing is a future extension |

## Dataset feasibility checkpoint

The checkpoint is decided at the end of Week 2. Criteria were fixed on 11 October 2026.

| ID | Criterion | Threshold | Observed | Status |
|---|---|---|---|---|
| F1 | Dated beauty reviews with text available locally | At least 500,000 | 23,874,796 (23,911,390 less 36,594 with no text) | Met |
| F2 | Keyword-enriched pool to sample from | At least 5,000 candidate reviews | 614,203 | Met |
| F3 | Genuine complaints among keyword hits | At least 10% in a labelled pilot | About 22% (13 of 60) in an informal single-reader check | Provisional; confirm in the pilot |
| F4 | Annotator agreement in a 50-review pilot | Cohen's kappa at least 0.60 | Not yet run | Pending |
| F5 | Expected positives in the 1,000 sample | At least 100 | Roughly 120 to 160 if F3 holds | Provisional |
| F6 | Recalled lines with at least 20 reviews in the 12 months before recall | At least 20 | 8 of 40 | Not met |

Reading the checkpoint:

- **F1 to F5 decide the core study (RQ1 to RQ3).** If F3 or F4 fails in the pilot, the guideline and keyword lists are revised and the pilot repeated once before the main annotation round.
- **F6 decides RQ4.** It is not met, so RQ4 is limited to a descriptive comparison and a case study. No predictive model of recalls will be built.

## Evidence detail

### Safety-related words in 23,911,390 reviews

| Word group | Reviews | Share |
|---|---|---|
| Any group | 614,203 | 2.57% |
| Skin reaction (rash, hives, itch, blister, swelling, allergic reaction) | 264,803 | 1.11% |
| Irritation | 188,371 | 0.79% |
| Smell and spoilage (rancid, mould, smells bad) | 104,162 | 0.44% |
| Contamination (bacteria, infection, expired, recall) | 48,399 | 0.20% |
| Hair and scalp (hair fell out, hair loss, bald spots) | 36,581 | 0.15% |
| Eye (eye infection, eyes burning or swollen) | 7,405 | 0.03% |

Groups overlap.

### Keyword hits by star rating

| Stars | Reviews | With a keyword | Share with a keyword | Share of all keyword hits |
|---|---|---|---|---|
| 1 | 2,840,878 | 164,625 | 5.8% | 26.8% |
| 2 | 1,275,031 | 53,254 | 4.2% | 8.7% |
| 3 | 1,715,821 | 49,821 | 2.9% | 8.1% |
| 4 | 2,616,444 | 63,328 | 2.4% | 10.3% |
| 5 | 15,463,216 | 283,175 | 1.8% | 46.1% |

### Informal check of 60 random keyword hits

| Reading | Count |
|---|---|
| Clear adverse reaction, spoilage or contamination involving the reviewed product | 13 |
| Bad smell only, possibly preference | 5 |
| Negation, condition relieved, another product, or unrelated use of the word | 42 |

One reader, no guideline, no second opinion. Planning input only.

### Recalled product lines with earlier reviews (40 lines)

| Measure | Lines |
|---|---|
| Title match in the Amazon catalogue | 27 |
| At least 1 review before the recall | 23 |
| At least 20 reviews before the recall | 14 |
| At least 20 reviews in the 12 months before | 8 |
| At least 100 reviews in the 12 months before | 3 |

Title matching only, on a hand-picked list. Not reviewed for variant, lot or country.

## What would change a rating

| RQ | Would move up if | Would move down if |
|---|---|---|
| RQ1 | A second annotator is confirmed and pilot kappa is at least 0.70 | Only one annotator is available (test-retest fallback) |
| RQ2 | The 1,000 sample yields more than 150 positives | Fewer than 60 positives after 500 labels |
| RQ3 | Individual rules reach useful precision on the development labels | Rules add nothing over the keyword baseline |
| RQ4 | A list built from the full recall files finds 20 or more qualifying lines | The reviewed matches turn out to be mostly wrong variants |
| RQ5 | More reviewed product and notice pairs are added | No further pairs can be reviewed in time |

## Method limits

- The counts were first made with one-off scripts on 11 October 2026 and were reproduced exactly by `complaint_detection.ipynb` on 13 October 2026. The informal check of 60 reviews was a separate one-off read.
- Keyword lists were written before reading any reviews and were not tuned.
- All figures describe one US marketplace, in English, up to September 2023.

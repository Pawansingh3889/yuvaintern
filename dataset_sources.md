# Dataset sources

Every source considered for the project, with its official link, what it is for, and its limits. Sizes are as observed on the date in the "Checked" column. This file supports the Week 1 report and is the starting point for the Week 2 source register.

Research questions: RQ1 annotation reliability, RQ2 complaint detection, RQ3 weak supervision, RQ4 early signal before recall (exploratory), RQ5 traceability to official records (exploratory).

## Summary

| # | Source | Owner | Used for | Local status |
|---|---|---|---|---|
| 1 | Amazon Reviews 2023, Beauty and Personal Care | McAuley Lab, UC San Diego | RQ1 to RQ4 | Downloaded |
| 2 | openFDA cosmetic adverse event reports | U.S. FDA | RQ3 vocabulary | Downloaded |
| 3 | FDA cosmetics adverse event dashboard | U.S. FDA | Context | Not downloaded |
| 4 | Health Canada recalls and safety alerts | Health Canada | RQ4 | Downloaded |
| 5 | openFDA drug recall enforcement reports | U.S. FDA | RQ4 | Downloaded |
| 6 | FDA Data Dashboard recalls | U.S. FDA | RQ4 | Not downloaded |
| 7 | RappelConso V2 | French economy ministries (DGCCRF) | RQ5 | Downloaded |
| 8 | Open Beauty Facts | Open Food Facts | RQ5 | Downloaded |
| 9 | EU Safety Gate 2025 report | European Commission | Context | Read online |
| 10 | UK Product Safety Database reports | Office for Product Safety and Standards | Context | Downloaded |
| 11 | Sephora Products and Skincare Reviews | Kaggle contributor | Rejected | In local archive |

## Primary source

### 1. Amazon Reviews 2023, Beauty and Personal Care

| | |
|---|---|
| Official page | https://amazon-reviews-2023.github.io/ |
| Files | `review_categories/Beauty_and_Personal_Care.jsonl.gz` (2.96 GB), `meta_categories/meta_Beauty_and_Personal_Care.jsonl.gz` (711 MB) |
| Citation | Hou et al. (2024), arXiv:2403.03952 |
| Access | Direct download, no account |
| Licence | None stated on the project page. Review text is not redistributed. |
| Coverage | Amazon US marketplace, to September 2023 |
| Update frequency | Static release |
| Checked | 11 October 2026 |

Observed contents:

| Measure | Value |
|---|---|
| Reviews | 23,911,390 |
| Products in the catalogue file | 1,028,914 |
| Verified purchase | 21,785,369 (91.1%) |
| Five-star reviews | 15,463,216 (64.7%) |
| One-star reviews | 2,840,878 (11.9%) |
| Reviews with no text | 36,594 |
| Average length | about 38 words |
| Reviews containing at least one safety-related word | 614,203 (2.6%) |

Review fields: `rating`, `title`, `text`, `images`, `asin`, `parent_asin`, `user_id`, `timestamp`, `helpful_vote`, `verified_purchase`. Product fields include `title`, `store`, `categories`, `details`, `average_rating`, `rating_number`, `parent_asin`.

Limits: no batch or lot number; no purchase location; posting time, not time of use; reviewers are self-selected; some reviews are fake or machine-written; ends before any recall published after September 2023.

## Official complaint and recall sources

### 2. openFDA cosmetic adverse event reports

| | |
|---|---|
| Official page | https://open.fda.gov/apis/cosmetic/event/ |
| Access | Open API and bulk download |
| Size | 85,511 reports; data last updated 31 August 2025 |
| Checked | 11 October 2026 |

Fields: `report_number`, `initial_received_date`, `event_date`, `products`, `reactions` (MedDRA terms), `outcomes`, `patient`, `report_type`.

Limits: reports are unverified and do not show causation. 71% of reports name a cancer term and 12% name a skin, hair or irritation term. The most frequent reaction term is ovarian cancer (29,563 mentions), which reflects litigation-driven reporting, not everyday cosmetic reactions. Terms relevant here are much rarer: alopecia 4,171, pruritus 2,552, rash 1,933, burning sensation 1,484. Product names are free text. Useful as a vocabulary source for labelling functions, not as ground truth.

### 3. FDA cosmetics adverse event dashboard

| | |
|---|---|
| Announcement | https://www.fda.gov/news-events/press-announcements/fda-launches-real-time-adverse-event-reporting-dashboard-cosmetic-products |
| Access | Interactive dashboard with downloadable listings |
| Update frequency | Daily |
| Checked | 11 October 2026 (announcement read; data not downloaded) |

Holds serious adverse event reports required under MoCRA plus voluntary reports. The FDA states the reports are unverified and are not an indicator of a product's safety profile.

### 4. Health Canada recalls and safety alerts

| | |
|---|---|
| Official page | https://open.canada.ca/data/en/dataset/d38de914-c94c-429b-8ab1-8776c31643e3 |
| File | https://recalls-rappels.canada.ca/sites/default/files/opendata-donneesouvertes/HCRSAMOpenData.json |
| Access | Open JSON and CSV |
| Licence | Open Government Licence, Canada |
| Size | 34,212 records; 201 in "Beauty and personal care"; 93 of those dated 2012 to September 2023 |
| Checked | 11 October 2026 |

Fields: `NID`, `Title`, `URL`, `Organization`, `Product`, `Issue`, `What you should do`, `Category`, `Recall class`, `Last updated`, `Archived`.

Limits: Canadian market; recalls are usually lot-specific; `Last updated` is not always the first publication date; 81 of the 201 beauty records have an empty `Issue` field.

### 5. openFDA drug recall enforcement reports

| | |
|---|---|
| Official page | https://open.fda.gov/apis/drug/enforcement/ |
| Access | Open API |
| Size | 18,010 records in the bulk file fingerprinted on 13 October 2026 |
| Checked | 13 October 2026 |

Covers products regulated as drugs in the United States, which includes sunscreen, antiperspirant and hand sanitiser. 74 records from 2020 to September 2023 give benzene as the recall reason. Benzene cannot be perceived by a user, so these serve as a comparison group for RQ4.

Note: openFDA has no cosmetics recall endpoint, and its food enforcement endpoint holds almost no cosmetics.

### 6. FDA Data Dashboard recalls

| | |
|---|---|
| Official page | https://datadashboard.fda.gov/oii/cd/recalls.htm |
| Access | Filtered download |
| Checked | Not downloaded |

The only identified source of US recalls with a cosmetics product type. To assess in Week 2.

## Sources for traceability (RQ5)

### 7. RappelConso V2

| | |
|---|---|
| Official page | https://www.data.gouv.fr/datasets/rappelconso-v2-rappels-de-produits |
| Licence | French Open Licence 2.0 |
| Size | 296 cosmetic notices retained in the 2 October 2026 snapshot |
| Update frequency | Continuous; portal record last modified 10 October 2026 |

Holds brand, product name, barcode, batch text, hazard, instructions and notice link. Limits: French market; a first probe found no brand overlap with US review data.

### 8. Open Beauty Facts

| | |
|---|---|
| Official page | https://www.data.gouv.fr/datasets/open-beauty-facts |
| Licence | Open Database Licence (ODbL): attribution and share-alike |
| Size | 64,237 records in the 2 October 2026 snapshot |

Volunteer-entered product catalogue with barcodes, names, brands and quantities. Limits: incomplete and uneven; 30 products link to French notices by barcode, 17 with usable names.

## Context only

### 9. EU Safety Gate 2025 report

https://op.europa.eu/webpub/just/safety-gate-2025-report/en/

Aggregate alert statistics: 4,671 alerts in 2025, cosmetics 36%. No product-level join.

### 10. UK Product Safety Database reports

https://www.gov.uk/government/statistics/product-safety-database-annual-reports

Aggregate tables. Definitions differ from EU and French counts, so the figures are never pooled.

## Rejected

### 11. Sephora Products and Skincare Reviews

https://www.kaggle.com/datasets/nadyinky/sephora-products-and-skincare-reviews

8,494 products with dated skincare reviews to March 2023. None of the 173 brand names in the French recall notices appears in its product list, and it is smaller than source 1 for the same market. Kept only as a documented negative result.

## Where the files are

- `data/raw/` holds unchanged downloads and is excluded from Git.
- `data/raw/amazon_reviews_2023/`, `data/raw/health_canada/` and `data/raw/openfda/` hold the files used by `complaint_detection.ipynb`.
- `data/raw/download_records.json` holds the link, size, file time and SHA-256 hash of each file.
- The Sephora files are in the local archive outside the repository.

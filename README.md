# YuvaIntern: cosmetic safety complaint detection

Main problem: detect genuine safety complaints (skin reactions, spoilage, contamination) in online beauty reviews early enough for a person to investigate them. See `roadmap.md` for the six-week plan and `docs/week_01/` for the Week 1 research proposal.

Exploratory questions: whether complaint rates rise before a recall, and whether a flagged product can be traced to the correct official recall record. The recall-matching notebook described below is earlier scoping work for the second of these.

Supporting files: `dataset_sources.md` (every source with link, licence and limits), `references.md` (APA 7 list) and `research_feasibility_matrix.md` (what the data can and cannot support).

## Earlier scoping: recall matching notebook

Open `cosmetic_recall_analysis.ipynb` in Jupyter and choose Run > Run All Cells.
The notebook uses the installed Anaconda Python kernel. It inspects French cosmetic recall records and UK aggregate product safety tables, then checks feasibility against an independent Open Beauty Facts catalogue. It compares word and character TF-IDF retrieval, displays errors, tests unsupported suggestions for other product identities, and checks one source-reviewed batch example. Semantic AI matching is a later research step that needs reviewed labels and a fresh evaluation set.

## Read the feasibility results

Sections 14 to 23 explain the human problem, existing services, catalogue coverage, matching errors, batch uncertainty and the decision to continue or narrow the project. Section 27 gives the updated STAR summary.

Choose Run > Run All Cells to reproduce the results from the saved snapshots. Rerunning does not contact a website. The notebook validates catalogue size and hash, schema, join uniqueness, data reconciliation, product split separation and the reviewed batch cases. Result CSVs are regenerated in `data/processed` and excluded from Git.

Catalogue barcode joins are provisional identity labels. They do not label affected batches or certify product safety. No user study, injury reduction, Indian applicability, live-feed performance or advantage over existing services has been established.

### Current decision

The verified catalogue contains 64,237 records. Accepted barcode identities overlap 30 products across 22 of the 296 French cosmetic notices. Only 17 overlapping products have usable catalogue names, leaving 8 evaluation queries. Word TF-IDF returns a linked notice first for 6 of 8 queries; character TF-IDF does so for 5 of 8. This small, provisional benchmark does not support a broad accuracy claim.

Both methods rank an older 300 ml Activilong recall above the barcode-linked 250 ml recall. The official records have different barcodes and batches. This gives the study a concrete focus: distinguish variants, preserve batch conditions and display uncertainty. Narrow the project to data quality, matching errors and reviewed batch interpretation while expanding independently reviewed examples. Package size is a feature to test next, not an improvement already established.

## Review signal question

Why ask it: Health Canada's 2025 recall of amika Mirrorball shampoo records 48 reports of foul odour and two reports of irritation or allergic reaction received by the company. Complaints of that kind may be visible in customer feedback before a notice is published. A review pattern would be a prompt for investigation. It is not evidence that a product is unsafe.

What the test needs: reviews with dates, for products that were later recalled, written before the notice was published, plus comparable products that were not recalled.

Candidate sources checked on 2 October 2026:

| Source | What it holds | Limits for this project |
|---|---|---|
| [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/) (McAuley Lab) | Beauty_and_Personal_Care: 23.9M ratings on 1.0M items. All_Beauty: 701.5K ratings on 112.6K items. Review timestamp, `parent_asin`, and item title, store and details. May 1996 to September 2023. | Not yet downloaded or measured. The project page states no licence and no marketplace. Ends before any recall published after September 2023. |
| [openFDA cosmetic adverse events](https://open.fda.gov/apis/cosmetic/event) | 85,511 reports with received date, free-text product names and reaction terms. | Reports sent to the US regulator, not reviews. A report is not proof the product caused the reaction. Product names are unstandardised. |
| [Sephora Products and Skincare Reviews](https://www.kaggle.com/datasets/nadyinky/sephora-products-and-skincare-reviews) (Kaggle) | 8,494 products; dated skincare reviews. The largest review file runs from 2008 to March 2023. | US retailer. No brand in common with the French notices (see below). |
| Open French-language reviews for products in RappelConso | None found. | Paid scrapers exist. They are not used here because of site terms and cost. |

First probe, run outside the notebook on files from the earlier work, exact brand-name matching only, not reviewed:

- 173 distinct brand names appear in the 296 French cosmetic notices.
- Sephora product list: 0 of 173 brands match.
- openFDA product names: 12 of 173 brands appear, and some are ordinary words (for example "essence"). A brand match is not a product match.
- openFDA holds two reports naming amika products and none naming Mirrorball.

What this means: with the data in hand, the French notices cannot be used to test review signals. Week 2 measures product-level overlap between recalled products and Amazon Reviews 2023. If fewer than 20 recalled products have reviews dated before their notice, the question is reported as a single case study and matching stays the only evaluated contribution. Twenty is a planning threshold, not a power calculation.

## Sources

- France: https://www.data.gouv.fr/datasets/rappelconso-v2-rappels-de-produits
- UK: https://www.gov.uk/government/statistics/product-safety-database-annual-reports
- Independent product catalogue: https://www.data.gouv.fr/datasets/open-beauty-facts
- Publisher's download guidance: https://support.openfoodfacts.org/help/en-gb/11-open-beauty-facts/70-where-can-i-download-open-beauty-facts-data

Open Beauty Facts is citizen-contributed data under ODbL. Its attribution and share-alike conditions apply to reuse. French recall data is published under the Open Licence. Review combined-dataset publication terms before redistributing joined records. The catalogue download record is in `data/raw/openbeautyfacts-download.json`.

Original downloads are copied unchanged to `data/raw`, which is excluded from Git. After cloning, download the files from the sources above into `data/raw` before running the notebook. This is a historical snapshot. A missing match does not establish safety. UK and French counts have different definitions and must not be pooled.

## Submission structure

`docs/week_01` through `docs/week_06` hold the weekly Word reports when prepared.

Week 1 is `docs/week_01/Week_01_Cosmetic_Safety_Complaint_Detection.docx`, with its submission text in `docs/week_01/week_01_submission_description.md`. It replaces an earlier Week 1 report on recall matching, which remains in the Git history.

## Previous work

The earlier notebooks, data and reports were moved intact to a local archive outside this repository (`project-archives/yuvaintern-2026-10-02-123625`).
The separate `beauty-review-analysis` Git repository was not changed.

## Environment

The package versions used for this notebook are recorded in `requirements.txt`.
No installation is needed with the current Anaconda environment.

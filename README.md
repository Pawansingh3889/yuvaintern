# YuvaIntern: cosmetic recall analysis

Problem: connect a specific cosmetic product and batch to an applicable official recall and its consumer guidance.

Open `cosmetic_recall_analysis.ipynb` in Jupyter and choose Run > Run All Cells.
The notebook uses the installed Anaconda Python kernel. It inspects French cosmetic recall records and UK aggregate product safety tables, then checks feasibility against an independent Open Beauty Facts catalogue. It compares word and character TF-IDF retrieval, displays errors, tests unsupported suggestions for other product identities, and checks one source-reviewed batch example. Semantic AI matching is a later research step that needs reviewed labels and a fresh evaluation set.

## Read the feasibility results

Sections 14 to 23 explain the human problem, existing services, catalogue coverage, matching errors, batch uncertainty and the decision to continue or narrow the project. Section 27 gives the updated STAR summary.

Choose Run > Run All Cells to reproduce the results from the saved snapshots. Rerunning does not contact a website. The notebook validates catalogue size and hash, schema, join uniqueness, data reconciliation, product split separation and the reviewed batch cases. Result CSVs are regenerated in `data/processed` and excluded from Git.

Catalogue barcode joins are provisional identity labels. They do not label affected batches or certify product safety. No user study, injury reduction, Indian applicability, live-feed performance or advantage over existing services has been established.

### Current decision

The verified catalogue contains 64,237 records. Accepted barcode identities overlap 30 products across 22 of the 296 French cosmetic notices. Only 17 overlapping products have usable catalogue names, leaving 8 evaluation queries. Word TF-IDF returns a linked notice first for 6 of 8 queries; character TF-IDF does so for 5 of 8. This small, provisional benchmark does not support a broad accuracy claim.

Both methods rank an older 300 ml Activilong recall above the barcode-linked 250 ml recall. The official records have different barcodes and batches. This gives the study a concrete focus: distinguish variants, preserve batch conditions and display uncertainty. Narrow the project to data quality, matching errors and reviewed batch interpretation while expanding independently reviewed examples. Package size is a feature to test next, not an improvement already established.

## Sources

- France: https://www.data.gouv.fr/datasets/rappelconso-v2-rappels-de-produits
- UK: https://www.gov.uk/government/statistics/product-safety-database-annual-reports
- Independent product catalogue: https://www.data.gouv.fr/datasets/open-beauty-facts
- Publisher's download guidance: https://support.openfoodfacts.org/help/en-gb/11-open-beauty-facts/70-where-can-i-download-open-beauty-facts-data

Open Beauty Facts is citizen-contributed data under ODbL. Its attribution and share-alike conditions apply to reuse. French recall data is published under the Open Licence. Review combined-dataset publication terms before redistributing joined records. The catalogue download record is in `data/raw/openbeautyfacts-download.json`.

Original downloads are copied unchanged to `data/raw`. This is a historical snapshot. A missing match does not establish safety. UK and French counts have different definitions and must not be pooled.

## Submission structure

`submissions/week_01` through `submissions/week_06` hold the weekly Word reports when prepared.

Week 1 is prepared in `submissions/week_01/Week_01_Cosmetic_Recall_Problem_Definition.docx` with its 278-word submission text in `submissions/week_01/Submission_Description.txt`. The report includes industry and academic references, four hypotheses, feasibility findings, variables, a validation plan, the six-week roadmap and a STAR summary. Later weekly reports will follow the same problem.

## Previous work

The earlier notebooks, data and reports were moved intact to a local archive outside this repository (`project-archives/yuvaintern-2026-10-02-123625`).
The separate `beauty-review-analysis` Git repository was not changed.

## Environment

The package versions used for this notebook are recorded in `requirements.txt`.
No installation is needed with the current Anaconda environment.

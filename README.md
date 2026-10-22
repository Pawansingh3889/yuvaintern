# YuvaIntern: cosmetic safety complaint detection

Six-week Data Science with Python internship (YuvaIntern, Beauty and Wellness). The
project finds genuine safety complaints (skin reactions, spoilage, contamination) in
public beauty product reviews early enough for a person to investigate them.

## Weekly reports

| Week | Report |
|---|---|
| 1 | [Problem definition](docs/week_01/Week_01_Cosmetic_Safety_Complaint_Detection.docx) |
| 2 | [Data sourcing strategy](docs/week_02/Week_02_Data_Sourcing_Strategy.docx) |
| 3 | [Data cleaning pipeline](docs/week_03/Week_03_Data_Cleaning_Pipeline.docx) |
| 4 | [EDA and feature engineering](docs/week_04/Week_04_EDA_and_Feature_Engineering.docx) |

## Repository contents

- `src/cleaning.py`: the Week 3 cleaning and preprocessing pipeline.
- `src/eda.py`: the Week 4 exploratory analysis over the cleaned reviews.
- `src/features.py`: the Week 4 engineered features (time ordered, no future leakage).
- `tests/`: offline pytest checks on synthetic data (no credentials or downloads).
- `complaint_detection.ipynb`: the analysis notebook; every reported number comes from it.
- `dataset_sources.md`: every data source with link, licence and limits.
- `data/labels/annotation_guideline.md`: the labelling guide for safety complaints.

## Run it

Data: Amazon Reviews 2023, Beauty and Personal Care
(https://amazon-reviews-2023.github.io/). Download the review and metadata files into
`data/raw/amazon_reviews_2023/`. Raw and processed data are not committed.

```
pip install -r requirements.txt
python -m pytest tests/
export CLEANING_SALT=<private random secret, 32+ characters>
python -m src.cleaning data/raw/amazon_reviews_2023/Beauty_and_Personal_Care.jsonl.gz data/processed --chunksize 100000
python -m src.eda
jupyter nbconvert --to notebook --execute --inplace complaint_detection.ipynb
```

No review text or raw reviewer identifiers are published in this repository.

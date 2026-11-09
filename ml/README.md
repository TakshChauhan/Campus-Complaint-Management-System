# CCMS Complaint Data and ML Work

Our ML/documentation group is preparing complaint data and software design diagrams for the Campus Complaint Management System. This is groundwork for understanding what kinds of campus complaints are received and for evaluating how they might be categorized later.

**Sprint 1 status:** The `ml-v2/integration` branch contains complaint CSV files and UML documentation. The reviewed branch does **not** show a trained classifier, model evaluation pipeline or an ML inference API connected to FastAPI. The backend's current department suggestion endpoint uses keywords, not these datasets.

## Datasets

The repository currently includes these files under `ml/data/complaints/`:

| File | Description |
| --- | --- |
| `complaints_300.csv` | Complaint dataset contributed for the team's classification work |
| `complaints_450.csv` | Additional complaint dataset contributed by the ML team |
| `Google_Form_Data.csv` | Complaint responses supplied in a Google Form-style CSV export |

All three files have the header fields:

```csv
TITLE,DESCRIPTION,LOCATION,COMMITTEE
```

- `TITLE`: a short summary of the problem.
- `DESCRIPTION`: the fuller report of what happened.
- `LOCATION`: the area or facility mentioned in the report.
- `COMMITTEE`: the dataset's label for the committee expected to handle that complaint.

The CSV **committee labels are not necessarily the same as the backend's provisional department names**. A future classifier will need an explicit mapping, data-quality review and agreed evaluation method before its predictions can be presented as department recommendations.

The filenames suggest dataset sizes, but this README does not assert that all rows are verified or that all records are independent. Check counts, duplicates and class distributions as part of ML preparation.

### Privacy and data provenance

Before publishing, sharing or training on complaint data, the team should verify where each record came from, whether it is synthetic or collected from people, and whether it contains names, room numbers or other information that could identify a student. The presence of a CSV in GitHub does **not** establish consent to republish personal information.

Please record any permitted data source, collection date, consent/permission basis, anonymization steps and known limitations. Avoid committing an unreviewed raw form export if it contains sensitive responses.

## UML and Software Engineering documents

Diagrams are stored in [`docs/architecture/uml/`](../docs/architecture/uml/), including class, sequence, activity and use-case views of the proposed CCMS workflow. They describe the **system design** and may include intended capabilities that extend beyond the currently implemented Sprint 1 routes; do not read every operation shown in a diagram as production-ready code.

## Work contributed through GitHub

The ML and documentation team's reviewed PRs include [#12](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/12), [#15](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/15) and [#16](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/16), merged into `ml-v2/integration`. Team members Yash, Krish and Rushil contributed datasets and design artifacts through individual branches.

## Potential next steps

If the team decides to build an ML model in a later sprint, a sensible process is to review the data source and labels, clean and split the data, establish a simple baseline, report held-out evaluation metrics and only then consider integrating a model with the backend. These are **proposed next steps**, not features included in the current branch.

See the [main README](../README.md) for the app overview and the [contribution guide](../CONTRIBUTING.md) for our workflow.

# Sprint 2 - Duplicate Detection Evaluation

## 1. Objective

Evaluate TF-IDF and cosine similarity for warning students about potentially duplicate campus complaints before submission. The goal is to identify a suitable similarity threshold that balances precision and recall while minimizing incorrect duplicate warnings.

## 2. Dataset

### Labelled complaint pairs

- **File:** `ml/data/labelled_pairs.csv`
- **Total pairs:** 100
- **Duplicate pairs (label 1):** 50
- **Non-duplicate pairs (label 0):** 50

The dataset contains pairs of complaints labelled according to whether they describe the same underlying issue.

**Labelling rule:** Two complaints are considered duplicates if they describe the same problem. Location alone does not determine whether complaints are duplicates because the matching function uses complaint titles and descriptions.


### Data limitations

- The 100-pair dataset is relatively easy: many duplicate pairs have near-identical wording, while many non-duplicate pairs concern unrelated topics.
- Labels were assigned by a single reviewer and require independent verification.
- Dataset provenance, permission to use the data, and potential personally identifiable information must be reviewed before sharing or using the data for training.

### Hold-out pairs (S4-27)

`ml/data/holdout_pairs.csv` has 40 labelled complaint pairs (20 duplicate, 20 not) for evaluating the duplicate detector. They have the same columns as `labelled_pairs.csv`. They were not used to choose the threshold.

Source: the complaints are new text written in the style of the existing data (formal English and Hinglish) and do not reuse any complaint from `labelled_pairs.csv`. They were drafted with AI assistance (Claude) and every label was reviewed by Yash.

Structure: rows 1-20 are hard cases (the same issue in different words, and similar words about a different issue or block); rows 21-40 are typical cases (near-identical wording for duplicates, unrelated topics for non-duplicates). Hard and typical rows can be evaluated separately.

## 3. Methodology

For each complaint pair:

1. Combine the title and description of the first complaint.
2. Combine the title and description of the second complaint.
3. Convert both texts into TF-IDF vectors using `TfidfVectorizer(stop_words="english")`, matching the production vectorizer settings. The evaluation fits its vectorizer on the labelled pair texts, while production fits it on the current query and accessible candidate complaints; therefore, the fitting context differs.
4. Calculate cosine similarity between the two complaint vectors.
5. Predict a duplicate when the similarity score is greater than or equal to the tested threshold.
6. Calculate precision, recall, F1-score, true positives (TP), false positives (FP), and false negatives (FN).

### TF-IDF configuration

The evaluation uses:

`TfidfVectorizer(stop_words="english")`

This matches the vectorizer configuration in `backend/app/services/duplicate_service.py`.

Default scikit-learn settings are used for lowercase conversion, unigram features, and term-frequency processing.

## 5. Results - Labelled Dataset

**Evaluation date:** 1 November 2026

**Dataset:** `ml/data/labelled_pairs.csv`

**Command:** `python ml/evaluate.py`

Total pairs: 100 (50 duplicate and 50 non-duplicate).

| Threshold | Precision | Recall | F1-score | TP | FP | FN |
|---:|---:|---:|---:|---:|---:|---:|
| 0.05 | 0.758 | 1.000 | 0.862 | 50 | 16 | 0 |
| 0.10 | 0.909 | 1.000 | 0.952 | 50 | 5 | 0 |
| 0.15 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| 0.20 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| 0.25 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| 0.30 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| **0.375** | **1.000** | **1.000** | **1.000** | **50** | **0** | **0** |
| 0.40 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| 0.50 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| 0.60 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| 0.70 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |

Thresholds from 0.15 to 0.70 produced identical results on this dataset. Perfect scores on this small dataset do not establish perfect performance on unseen complaints.

## 6. Production Threshold Selection

The production duplicate-detection service uses a similarity threshold of **0.375**, defined by `PRODUCTION_THRESHOLD` in `backend/app/services/duplicate_service.py`.

A pair is predicted as a duplicate when its cosine similarity is greater than or equal to the configured threshold.

### Evaluation-based selection

The evaluation uses 100 labelled complaint pairs: 50 duplicate pairs and 50 non-duplicate pairs.

The evaluator reports:
- Minimum duplicate-pair similarity: **0.7429**
- Maximum non-duplicate-pair similarity: **0.1417**

This leaves a clear score gap between the two classes. The selected threshold **0.375** lies inside this gap: it is above the highest non-duplicate score and below the lowest duplicate score.

At threshold 0.375, precision, recall, and F1-score are all **1.000**, with 50 true positives, zero false positives, and zero false negatives.

Thresholds from 0.15 to 0.70 also produced identical metrics on this dataset. The score gap supports selecting 0.375 rather than retaining 0.70 without evidence-based justification.

### Limitations of threshold selection

The selected threshold is provisional because:
- The evaluation uses only 100 labelled complaint pairs.
- The same dataset is used for threshold evaluation and selection; an independent holdout dataset is unavailable.
- The labelled examples may not represent the variety of real student complaints.
- TF-IDF measures lexical similarity and may not identify complaints that describe the same issue using substantially different wording.

Perfect scores on this dataset do not guarantee perfect performance on unseen or real-world complaints. Further evaluation on a larger and more representative dataset, including an independent holdout set, is required before treating the threshold as final.

Duplicate detection remains an advisory feature. Students must retain the ability to submit complaints even when similar complaints are suggested.


### Duplicate matching privacy boundaries (Sprint 4)

The production duplicate service compares only complaint titles and descriptions. It does not use student names, creator IDs or other identity fields as similarity features.

Candidate complaints are filtered by access rules before their text is read. The service permits a student's own complaints and published complaints visible under the department-wide or verified-hostel visibility rules. Private complaints belonging to other students, and complaints outside the student's permitted hostel scope, must not be exposed through suggestions.

The response does not include creator identity. It returns limited suggestion details such as complaint title, department, status and similarity score. Duplicate suggestions are advisory and must not prevent complaint submission.

The evaluation uses labelled text pairs and does not test database access control or prove that production privacy rules are correctly enforced. Those rules require separate backend tests.
## 7. Expected Service Behaviour

The duplicate-detection service is intended to:

- Return up to three relevant duplicate suggestions above the configured threshold.
- Include only necessary complaint details, such as title, department, status, and similarity score.
- Avoid exposing complaint creators' identities.
- Consider public complaints and the current student's own complaints, subject to the approved access rules.
- Fail safely: if duplicate detection is unavailable, return an empty suggestion list and allow submission to continue.

These behaviours must be verified against the actual service implementation and tests before being described as completed.

## 8. Limitations and Next Steps

- **Original threshold-selection results:** The threshold was initially selected and evaluated using the same pairs, so those results may be optimistic. A separate 40-pair hold-out evaluation is now documented in Section 10.
- **Limited dataset:** The available pairs may not represent the full variety of campus complaints.
- **Lexical matching:** TF-IDF measures word overlap rather than semantic meaning. Paraphrases with few shared words may receive low scores.
- **Language variation:** Hinglish wording and spelling mistakes may reduce similarity.
- **Synthetic examples:** Hand-written examples may not fully reflect real student complaints.
- **Label quality:** Independent review of the labels is still needed.

Recommended next steps:

1. Verify the dataset filenames, locations, and labels.
2. Continue validating the fixed threshold on larger, separate held-out datasets.
3. Confirm that the service uses the same TF-IDF settings and selected threshold.
4. Test top-three suggestions, privacy restrictions, and failure fallback.
5. Record the final verified threshold and evaluation results.

## 9. Reproducibility

The evaluation can be reproduced using the labelled complaint-pair dataset and the evaluation script included in this repository.

### Requirements

- Python environment with the dependencies listed in the project's requirements file.
- Labelled complaint-pair dataset available at `ml/data/labelled_pairs.csv`.
- Evaluation script available at `ml/evaluate.py`.

### Running the evaluation

From the repository root, run:

```bash
python ml/evaluate.py
```

The script:

1. Loads the labelled complaint pairs.
2. Combines the complaint title and description for each complaint.
3. Applies TF-IDF vectorization with English stop-word removal.
4. Calculates cosine similarity for each pair.
5. Evaluates duplicate predictions across the configured similarity thresholds.
6. Reports precision, recall, F1-score, true positives, false positives, and false negatives.

The evaluation uses the same TF-IDF text-processing configuration as the production duplicate-detection service.

### Production configuration

The production threshold is defined by `PRODUCTION_THRESHOLD` in:

`backend/app/services/duplicate_service.py`

The production threshold is **0.375**.

### Reproducibility note

The reported results correspond to the labelled dataset available in the repository at the time of evaluation. Reproducing the results requires using the same dataset and evaluation implementation. Changes to either may produce different metrics.

The evaluation results are based on a limited labelled dataset and should not be interpreted as a guarantee of performance on all real-world complaints.

## 10. Independent Synthetic Hold-out Evaluation (Sprint 4)

### Dataset and provenance

- File: `ml/data/holdout_pairs.csv`
- Total pairs: **40**
- Duplicate pairs (label 1): **20**
- Non-duplicate pairs (label 0): **20**
- Missing required values: **0**

This is a separate synthetic hold-out dataset created by Yash with AI assistance and human label review. It contains newly written complaint-style examples; it was not collected from real student complaints.

The dataset is separate from `ml/data/labelled_pairs.csv`, which was used for threshold selection. The hold-out pairs and labels were not used to tune the production threshold.

Rows 1-20 are hard cases. Rows 21-40 are typical cases.

### Methodology

The evaluator combines complaint titles and descriptions, applies `TfidfVectorizer(stop_words="english")`, and calculates cosine similarity for each pair.

The production threshold remains fixed at **0.375**. It was selected before this hold-out evaluation and has not been changed based on these results. A pair is predicted as a duplicate when its similarity is greater than or equal to 0.375.

### Hard cases (rows 1-20)

These cases include paraphrased duplicates and similar wording describing different issues.

| Metric | Result |
|---|---:|
| True Positives (TP) | 0 |
| False Positives (FP) | 5 |
| True Negatives (TN) | 5 |
| False Negatives (FN) | 10 |
| Precision | 0.000 |
| Recall | 0.000 |
| F1-score | 0.000 |
| Total pairs | 20 |

The detector caught **0 of 10 duplicate pairs** in the hard group. All 10 hard duplicate pairs were missed.

### Typical cases (rows 21-40)

These cases include near-identical wording for duplicates and unrelated topics for non-duplicates.

| Metric | Result |
|---|---:|
| True Positives (TP) | 10 |
| False Positives (FP) | 0 |
| True Negatives (TN) | 10 |
| False Negatives (FN) | 0 |
| Precision | 1.000 |
| Recall | 1.000 |
| F1-score | 1.000 |
| Total pairs | 20 |

The detector caught **10 of 10 duplicate pairs** in the typical group and correctly rejected all 10 non-duplicate pairs.

### Combined hold-out results

| Metric | Result |
|---|---:|
| Threshold | 0.375 |
| True Positives (TP) | 10 |
| False Positives (FP) | 5 |
| True Negatives (TN) | 15 |
| False Negatives (FN) | 10 |
| Precision | 0.667 |
| Recall | 0.500 |
| F1-score | 0.571 |
| Total pairs | 40 |

The combined recall of 0.500 hides a substantial difference between the two groups: the detector caught none of the hard paraphrased duplicates, while it caught all typical duplicates.

### Interpretation and limitations

The results expose a key limitation of lexical TF-IDF similarity. It performs well when duplicate complaints use similar words, but may fail when the same issue is expressed using substantially different wording.

These are synthetic evaluation examples, not real student complaint data. AI-assisted generation and human label review do not establish that the dataset fully represents real campus complaints.

The dataset is small and provides an initial independent evaluation, not a definitive estimate of production performance. Further validation should use a larger, representative dataset of real complaints with appropriate privacy safeguards and independent labels.

The threshold remains **0.375**. These results do not justify changing it based on this small synthetic hold-out set. Duplicate suggestions remain advisory and must not prevent students from submitting complaints.

### Reproducibility

From the repository root, run:

```bash
python ml/evaluate_holdout.py

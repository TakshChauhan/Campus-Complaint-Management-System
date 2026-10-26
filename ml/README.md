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

# Sprint 2 — Duplicate Detection Evaluation

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

The evaluation also includes results previously reported for a combined dataset of 205 pairs, containing 99 duplicate pairs and 106 non-duplicate pairs. The combined dataset's filename and location should be confirmed in the repository before reproducing those results.

### Data limitations

- The 100-pair dataset is relatively easy: many duplicate pairs have near-identical wording, while many non-duplicate pairs concern unrelated topics.
- The additional synthetic examples in the combined evaluation were team/assistant-created and may not represent real student submissions.
- Labels were assigned by a single reviewer and require independent verification.
- Dataset provenance, permission to use the data, and potential personally identifiable information must be reviewed before sharing or using the data for training.

## 3. Methodology

For each complaint pair:

1. Join the title and description of each complaint into one text.
2. Convert the text into TF-IDF vectors using:
   - `ngram_range=(1, 2)`
   - `stop_words="english"`
   - `sublinear_tf=True`
3. Calculate cosine similarity between the two complaint vectors.
4. Predict a duplicate when the similarity score is greater than or equal to the selected threshold.
5. Calculate precision, recall, F1-score, true positives (TP), false positives (FP), and false negatives (FN).

The vectorizer configuration should match the implementation in `backend/app/services/duplicate_service.py`.

## 4. Results — Combined Dataset

The following results were reported for the combined dataset of 205 pairs. They are included as preliminary results and should be reproduced using the verified dataset and evaluation script.

| Threshold | Precision | Recall | F1-score | TP | FP | FN |
|---:|---:|---:|---:|---:|---:|---:|
| 0.05 | 0.870 | 0.879 | 0.874 | 87 | 13 | 12 |
| **0.10** | **0.975** | **0.778** | **0.865** | **77** | **2** | **22** |
| 0.15 | 0.986 | 0.687 | 0.810 | 68 | 1 | 31 |
| 0.20 | 0.984 | 0.606 | 0.750 | 60 | 1 | 39 |
| 0.25 | 1.000 | 0.566 | 0.723 | 56 | 0 | 43 |
| 0.30 | 1.000 | 0.525 | 0.689 | 52 | 0 | 47 |
| 0.40 | 1.000 | 0.505 | 0.671 | 50 | 0 | 49 |
| 0.50 | 1.000 | 0.505 | 0.671 | 50 | 0 | 49 |
| 0.60 | 1.000 | 0.505 | 0.671 | 50 | 0 | 49 |
| 0.70 | 1.000 | 0.333 | 0.500 | 33 | 0 | 66 |

## 5. Results — Labelled Dataset

The following results were reported for `labelled_pairs.csv`, containing 100 pairs.

| Threshold | Precision | Recall | F1-score | TP | FP | FN |
|---:|---:|---:|---:|---:|---:|---:|
| 0.05 | 0.877 | 1.000 | 0.935 | 50 | 7 | 0 |
| 0.10 | 0.980 | 1.000 | 0.990 | 50 | 1 | 0 |
| 0.15–0.60 | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| 0.70 | 1.000 | 0.700 | 0.824 | 35 | 0 | 15 |

These results indicate that the labelled dataset is easier than the combined evaluation set. Perfect scores on this dataset do not establish perfect performance on unseen complaints.

## 6. Initial Threshold Selection: 0.10

The initial candidate threshold is **0.10**, based on the reported combined-dataset results and the preference to minimize incorrect duplicate warnings.

At this threshold, the combined-dataset results were:

- Precision: 0.975
- Recall: 0.778
- F1-score: 0.865
- False positives: 2
- False negatives: 22

At threshold 0.05, recall is higher, but there are 13 false positives. Threshold 0.10 reduces false positives to 2, at the cost of missing more actual duplicate pairs.

Duplicate detection should be an advisory feature rather than a submission blocker. Students should retain the option to submit a complaint even when similar complaints are suggested.

**Status:** Threshold 0.10 is a provisional candidate. Confirm that the service uses this threshold and validate it on separate, representative held-out pairs before treating it as final.

## 7. Expected Service Behaviour

The duplicate-detection service is intended to:

- Return up to three relevant duplicate suggestions above the configured threshold.
- Include only necessary complaint details, such as title, department, status, and similarity score.
- Avoid exposing complaint creators' identities.
- Consider public complaints and the current student's own complaints, subject to the approved access rules.
- Fail safely: if duplicate detection is unavailable, return an empty suggestion list and allow submission to continue.

These behaviours must be verified against the actual service implementation and tests before being described as completed.

## 8. Limitations and Next Steps

- **No independent holdout:** The threshold was selected and evaluated using the same pairs, so results may be optimistic.
- **Limited dataset:** The available pairs may not represent the full variety of campus complaints.
- **Lexical matching:** TF-IDF measures word overlap rather than semantic meaning. Paraphrases with few shared words may receive low scores.
- **Language variation:** Hinglish wording and spelling mistakes may reduce similarity.
- **Synthetic examples:** Hand-written examples may not fully reflect real student complaints.
- **Label quality:** Independent review of the labels is still needed.

Recommended next steps:

1. Verify the dataset filenames, locations, and labels.
2. Validate the threshold on separate held-out pairs.
3. Confirm that the service uses the same TF-IDF settings and selected threshold.
4. Test top-three suggestions, privacy restrictions, and failure fallback.
5. Record the final verified threshold and evaluation results.

## 9. Reproducibility

Run commands from the repository root.

Install the required dependency if necessary:

```bash
python -m pip install scikit-learn
```

Run the existing evaluation script after confirming its filename and dataset path. If the script supports a dataset-path argument, use the verified path to `labelled_pairs.csv`.

The combined-dataset results require the actual combined dataset and should not be treated as reproducible until its filename, location, and evaluation command are confirmed.


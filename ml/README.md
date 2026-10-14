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

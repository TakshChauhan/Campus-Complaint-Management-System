import csv
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    confusion_matrix,
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.metrics.pairwise import cosine_similarity

DATASET = Path(__file__).resolve().parent / "data" / "holdout_pairs.csv"
THRESHOLD = 0.375


def report_group(name, labels, predictions):
    tn, fp, fn, tp = confusion_matrix(
        labels, predictions, labels=[0, 1]
    ).ravel()

    precision = precision_score(labels, predictions, zero_division=0)
    recall = recall_score(labels, predictions, zero_division=0)
    f1 = f1_score(labels, predictions, zero_division=0)

    print(f"\n{name}")
    print(f"Pairs: {len(labels)}")
    print(f"TP: {tp} | FP: {fp} | TN: {tn} | FN: {fn}")
    print(f"Precision: {precision:.3f}")
    print(f"Recall:    {recall:.3f}")
    print(f"F1-score:  {f1:.3f}")


def main():
    with open(DATASET, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != 40:
        raise ValueError(f"Expected 40 hold-out pairs, found {len(rows)}")

    required = {
        "title_a", "description_a",
        "title_b", "description_b", "label",
    }

    if not required.issubset(rows[0]):
        raise ValueError(f"Required columns: {sorted(required)}")

    labels, texts_a, texts_b = [], [], []

    for row in rows:
        label = row["label"].strip()
        if label not in {"0", "1"}:
            raise ValueError(f"Invalid label: {label!r}")

        labels.append(int(label))
        texts_a.append(
            row["title_a"].strip() + " " + row["description_a"].strip()
        )
        texts_b.append(
            row["title_b"].strip() + " " + row["description_b"].strip()
        )

    vectorizer = TfidfVectorizer(stop_words="english")
    vectors = vectorizer.fit_transform(texts_a + texts_b)

    n = len(rows)
    scores = [
        cosine_similarity(vectors[i], vectors[n + i])[0, 0]
        for i in range(n)
    ]
    predictions = [int(score >= THRESHOLD) for score in scores]

    print("INDEPENDENT SYNTHETIC HOLD-OUT EVALUATION")
    print(f"Dataset: {DATASET.name}")
    print(f"Total pairs: {n}")
    print(f"Fixed threshold: {THRESHOLD}")

    report_group("HARD CASES (rows 1-20)", labels[:20], predictions[:20])
    report_group("TYPICAL CASES (rows 21-40)", labels[20:], predictions[20:])
    report_group("COMBINED RESULTS", labels, predictions)


if __name__ == "__main__":
    main()

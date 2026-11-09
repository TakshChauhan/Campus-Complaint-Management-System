import csv
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import (
    confusion_matrix,
    precision_score,
    recall_score,
    f1_score,
)

DATASET = Path(__file__).resolve().parent / "data" / "holdout_pairs.csv"
THRESHOLD = 0.375


def main():
    with open(DATASET, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("Hold-out dataset is empty.")

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

    tn, fp, fn, tp = confusion_matrix(
        labels, predictions, labels=[0, 1]
    ).ravel()

    print("INDEPENDENT HOLD-OUT EVALUATION")
    print(f"Dataset: {DATASET.name}")
    print(f"Total pairs: {n}")
    print(f"Fixed threshold: {THRESHOLD}")
    print(f"Precision: {precision_score(labels, predictions, zero_division=0):.3f}")
    print(f"Recall:    {recall_score(labels, predictions, zero_division=0):.3f}")
    print(f"F1-score:  {f1_score(labels, predictions, zero_division=0):.3f}")
    print(f"TP: {tp} | FP: {fp} | TN: {tn} | FN: {fn}")


if __name__ == "__main__":
    main()

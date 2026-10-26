
import csv
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import precision_score, recall_score, f1_score
from sklearn.metrics import confusion_matrix

DATASET = Path(__file__).resolve().parent / "data" / "labelled_pairs.csv"
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70]


def main():
    with open(DATASET, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("Dataset is empty.")

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

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )

    vectors = vectorizer.fit_transform(texts_a + texts_b)
    n = len(rows)

    scores = [
        cosine_similarity(vectors[i], vectors[n + i])[0, 0]
        for i in range(n)
    ]

    print(f"Total pairs: {n}")
    print("\nThreshold | Precision | Recall | F1    | TP | FP | FN")
    print("-" * 60)

    for threshold in THRESHOLDS:
        predictions = [int(score >= threshold) for score in scores]
        tn, fp, fn, tp = confusion_matrix(
            labels, predictions, labels=[0, 1]
        ).ravel()

        precision = precision_score(labels, predictions, zero_division=0)
        recall = recall_score(labels, predictions, zero_division=0)
        f1 = f1_score(labels, predictions, zero_division=0)

        print(
            f"{threshold:9.2f} | {precision:9.3f} | "
            f"{recall:6.3f} | {f1:5.3f} | "
            f"{tp:2d} | {fp:2d} | {fn:2d}"
        )


if __name__ == "__main__":
    main()

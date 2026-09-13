"""Train the two MAWOS ML models and persist artifacts + honest metrics.

  * Scholarship: CART decision tree (criterion='entropy'), per report §4.2.
  * Placement:   Random Forest (n_estimators=100), per report §4.2.

Depth is capped and data carries injected noise, so reported accuracy is a
genuine generalisation estimate, not a re-derivation of a hand-written rule.

Run:  python ml/train.py
"""
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.tree import DecisionTreeClassifier

from generate_datasets import DATA_DIR, main as generate_data

MODELS_DIR = Path(__file__).resolve().parent / "models"
SEED = 42


def _evaluate(model, X_train, X_test, y_train, y_test) -> dict:
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    cv = cross_val_score(model, X_train, y_train, cv=5)
    return {
        "test_accuracy": round(accuracy_score(y_test, pred), 4),
        "precision": round(precision_score(y_test, pred), 4),
        "recall": round(recall_score(y_test, pred), 4),
        "f1": round(f1_score(y_test, pred), 4),
        "cv5_mean_accuracy": round(cv.mean(), 4),
        "cv5_std": round(cv.std(), 4),
        "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
        "n_train": len(X_train), "n_test": len(X_test),
    }


def main():
    if not (DATA_DIR / "scholarship_synthetic.csv").exists():
        generate_data()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    metrics = {}

    # ---- Scholarship: CART ---------------------------------------------
    sch = pd.read_csv(DATA_DIR / "scholarship_synthetic.csv")
    X = sch[["cgpa", "attendance_pct", "family_income", "backlogs", "fees_cleared"]].values
    y = sch["eligible"].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2,
                                              random_state=SEED, stratify=y)
    cart = DecisionTreeClassifier(criterion="entropy", max_depth=8,
                                  min_samples_leaf=3, random_state=SEED)
    metrics["scholarship_cart"] = _evaluate(cart, X_tr, X_te, y_tr, y_te)
    metrics["scholarship_cart"]["features"] = [
        "cgpa", "attendance_pct", "family_income", "backlogs", "fees_cleared"]
    joblib.dump(cart, MODELS_DIR / "scholarship_cart.joblib")

    # ---- Placement: Random Forest ----------------------------------------
    plc = pd.read_csv(DATA_DIR / "placement_synthetic.csv")
    X = plc[["cgpa", "backlogs", "attendance_pct"]].values
    y = plc["placed"].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2,
                                              random_state=SEED, stratify=y)
    rf = RandomForestClassifier(n_estimators=100, max_depth=8,
                                min_samples_leaf=5, random_state=SEED)
    metrics["placement_rf"] = _evaluate(rf, X_tr, X_te, y_tr, y_te)
    metrics["placement_rf"]["features"] = ["cgpa", "backlogs", "attendance_pct"]
    joblib.dump(rf, MODELS_DIR / "placement_rf.joblib")

    with open(MODELS_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

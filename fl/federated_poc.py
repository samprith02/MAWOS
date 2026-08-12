"""Federated Learning proof-of-concept (offline, Phase-3/future-work module).

Scenario: 4 VTU-affiliated colleges want a shared scholarship-eligibility
model WITHOUT pooling raw student records (DPDP Act-aligned). We simulate
non-IID college shards from the synthetic scholarship dataset via a
Dirichlet split and compare:

  * Centralised logistic regression (upper bound — requires pooling data)
  * Local-only training (no collaboration)
  * FedAvg  (McMahan et al., 2017)
  * FedProx (Li et al., 2020; proximal term stabilises non-IID training)

Note: CART / Random Forest cannot be federated by weight averaging, which is
exactly why this module swaps in logistic regression for the FL experiment.

Run:  python fl/federated_poc.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "ml" / "data" / "scholarship_synthetic.csv"
RESULTS = Path(__file__).resolve().parent / "results"

SEED = 123
N_CLIENTS = 4
ROUNDS = 40
LOCAL_EPOCHS = 8
LR = 0.15
MU_PROX = 0.1
DIRICHLET_ALPHA = 0.3

FEATURES = ["cgpa", "attendance_pct", "family_income", "backlogs", "fees_cleared"]


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def local_train(w, Xc, yc, epochs, lr, w_global=None, mu=0.0):
    """Mini-batch gradient descent on logistic loss (+ optional proximal term)."""
    n = len(yc)
    rng = np.random.default_rng(0)
    for _ in range(epochs):
        idx = rng.permutation(n)
        for start in range(0, n, 32):
            b = idx[start:start + 32]
            Xb, yb = Xc[b], yc[b]
            grad = Xb.T @ (sigmoid(Xb @ w) - yb) / len(b)
            if w_global is not None and mu > 0:
                grad += mu * (w - w_global)
            w = w - lr * grad
    return w


def accuracy(w, X, y):
    return float(np.mean((sigmoid(X @ w) >= 0.5).astype(int) == y))


def dirichlet_shards(y, n_clients, alpha, rng):
    """Non-IID label split: each class distributed over clients ~ Dirichlet."""
    shards = [[] for _ in range(n_clients)]
    for cls in np.unique(y):
        cls_idx = np.where(y == cls)[0]
        rng.shuffle(cls_idx)
        props = rng.dirichlet([alpha] * n_clients)
        cuts = (np.cumsum(props) * len(cls_idx)).astype(int)[:-1]
        for shard, part in zip(shards, np.split(cls_idx, cuts)):
            shard.extend(part.tolist())
    return [np.array(sorted(s)) for s in shards]


def run_experiment(X, y, seed: int):
    """One full run (shard split + all four training regimes) for one seed."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(y))
    n_test = int(0.2 * len(y))
    test_idx, train_idx = perm[:n_test], perm[n_test:]
    X_tr, y_tr, X_te, y_te = X[train_idx], y[train_idx], X[test_idx], y[test_idx]

    shards = dirichlet_shards(y_tr, N_CLIENTS, DIRICHLET_ALPHA, rng)
    d = X.shape[1]

    w_central = local_train(np.zeros(d), X_tr, y_tr, epochs=ROUNDS * LOCAL_EPOCHS, lr=LR)
    acc_central = accuracy(w_central, X_te, y_te)

    local_accs = []
    for s in shards:
        if len(s) < 5:
            continue
        w_loc = local_train(np.zeros(d), X_tr[s], y_tr[s],
                            epochs=ROUNDS * LOCAL_EPOCHS, lr=LR)
        local_accs.append(accuracy(w_loc, X_te, y_te))
    acc_local = float(np.mean(local_accs))

    history = {"FedAvg": [], "FedProx": []}
    for algo, mu in (("FedAvg", 0.0), ("FedProx", MU_PROX)):
        w = np.zeros(d)
        for _ in range(ROUNDS):
            client_ws, sizes = [], []
            for s in shards:
                if len(s) == 0:
                    continue
                cw = local_train(w.copy(), X_tr[s], y_tr[s], LOCAL_EPOCHS, LR,
                                 w_global=w, mu=mu)
                client_ws.append(cw)
                sizes.append(len(s))
            sizes = np.array(sizes, dtype=float)
            w = np.average(np.stack(client_ws), axis=0, weights=sizes / sizes.sum())
            history[algo].append(accuracy(w, X_te, y_te))

    return {
        "centralised": acc_central,
        "local_only": acc_local,
        "FedAvg": history["FedAvg"][-1],
        "FedProx": history["FedProx"][-1],
        "history": history,
        "shard_sizes": [int(len(s)) for s in shards],
    }


def main():
    if not DATA.exists():
        raise SystemExit("Run ml/generate_datasets.py first.")
    df = pd.read_csv(DATA)
    X = df[FEATURES].values.astype(float)
    y = df["eligible"].values.astype(float)

    # standardise + bias column
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)
    X = np.hstack([X, np.ones((len(X), 1))])

    # Multi-seed protocol: 5 independent shardings/splits, mean +/- std —
    # single-seed point estimates are not acceptable evidence.
    seeds = [SEED + 111 * k for k in range(5)]
    runs = [run_experiment(X, y, s) for s in seeds]

    def agg(key):
        vals = np.array([r[key] for r in runs])
        return f"{vals.mean():.4f} ± {vals.std():.4f}"

    history = runs[0]["history"]  # convergence plot from the first seed
    results = {
        "setup": {"clients": N_CLIENTS, "rounds": ROUNDS,
                  "local_epochs": LOCAL_EPOCHS, "dirichlet_alpha": DIRICHLET_ALPHA,
                  "seeds": seeds,
                  "shard_sizes_per_seed": [r["shard_sizes"] for r in runs]},
        "test_accuracy_mean_std_over_5_seeds": {
            "centralised (pooled data)": agg("centralised"),
            "local-only (no collaboration)": agg("local_only"),
            "FedAvg": agg("FedAvg"),
            "FedProx (mu=0.1)": agg("FedProx"),
        },
    }
    acc_central = float(np.mean([r["centralised"] for r in runs]))
    acc_local = float(np.mean([r["local_only"] for r in runs]))

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "fl_results.json").write_text(json.dumps(
        {**results, "history": history}, indent=2))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(7, 4.2))
        plt.plot(history["FedAvg"], label="FedAvg")
        plt.plot(history["FedProx"], label=f"FedProx (μ={MU_PROX})")
        plt.axhline(acc_central, ls="--", c="green", label="Centralised (pooled)")
        plt.axhline(acc_local, ls=":", c="red", label="Local-only avg")
        plt.xlabel("Communication round")
        plt.ylabel("Global test accuracy")
        plt.title(f"Federated scholarship model — {N_CLIENTS} colleges, "
                  f"non-IID (Dirichlet α={DIRICHLET_ALPHA})")
        plt.legend()
        plt.tight_layout()
        plt.savefig(RESULTS / "fl_convergence.png", dpi=140)
        print(f"Plot: {RESULTS / 'fl_convergence.png'}")
    except ImportError:
        pass

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

"""2D coordinates for the explorer's atlas: unit vectors -> PCA(50) -> exact t-SNE, numpy only.

About 3k units take a minute or two. Coordinates are stored per embedding model in `unit_xy` and
recomputed only when asked (`cli project`), so the explorer starts instantly afterwards.
"""
from __future__ import annotations
import array

import numpy as np

SCHEMA = "CREATE TABLE IF NOT EXISTS unit_xy(model TEXT, unit_id TEXT, x REAL, y REAL, PRIMARY KEY(model, unit_id));"


def unit_matrix(con, model: str) -> tuple[list[str], np.ndarray]:
    rows = con.execute("SELECT unit_id, vec FROM unit_vec WHERE kind='unit' AND model=? ORDER BY unit_id",
                       (model,)).fetchall()
    if not rows:
        return [], np.zeros((0, 1), "float32")
    mat = np.array([array.array("f", b) for _, b in rows], dtype="float32")
    mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
    return [r[0] for r in rows], mat


def _affinities(d2: np.ndarray, perplexity: float) -> np.ndarray:
    n = d2.shape[0]
    target = np.log(perplexity)
    P = np.zeros((n, n))
    for i in range(n):
        lo, hi, beta = 1e-20, 1e20, 1.0
        di = np.delete(d2[i], i)
        for _ in range(60):
            p = np.exp(-(di - di.min()) * beta)
            s = p.sum()
            h = np.log(s) + beta * (di * p).sum() / s - beta * di.min()
            if abs(h - target) < 1e-4:
                break
            if h > target:
                lo = beta
                beta = beta * 2 if hi == 1e20 else (beta + hi) / 2
            else:
                hi = beta
                beta = (beta + lo) / 2
        P[i, np.arange(n) != i] = p / s
    P = (P + P.T) / (2 * n)
    return np.maximum(P, 1e-12)


def tsne(X: np.ndarray, perplexity: float = 30.0, iters: int = 750, seed: int = 0, log=print) -> np.ndarray:
    X = X - X.mean(0)
    U, S, _ = np.linalg.svd(X, full_matrices=False)
    X = U[:, :50] * S[:50]
    sq = (X ** 2).sum(1)
    d2 = np.maximum(sq[:, None] + sq[None, :] - 2 * X @ X.T, 0)
    P = _affinities(d2, perplexity)
    Y = X[:, :2] / (np.std(X[:, 0]) + 1e-9) * 1e-2          # PCA init: stable, deterministic layouts
    rng = np.random.default_rng(seed)
    Y += rng.normal(0, 1e-4, Y.shape)
    vel, gains = np.zeros_like(Y), np.ones_like(Y)
    for it in range(iters):
        exag = 12.0 if it < 250 else 1.0
        sy = (Y ** 2).sum(1)
        num = 1.0 / (1.0 + sy[:, None] + sy[None, :] - 2 * Y @ Y.T)
        np.fill_diagonal(num, 0)
        Q = np.maximum(num / num.sum(), 1e-12)
        W = (exag * P - Q) * num
        grad = 4 * (np.diag(W.sum(1)) - W) @ Y
        mom = 0.5 if it < 250 else 0.8
        gains = np.where(np.sign(grad) != np.sign(vel), gains + 0.2, gains * 0.8).clip(0.01)
        vel = mom * vel - 200.0 * gains * grad
        Y += vel
        Y -= Y.mean(0)
        if (it + 1) % 250 == 0:
            log(f"  t-SNE {it + 1}/{iters}")
    return Y


def build(con, model: str, log=print) -> int:
    con.executescript(SCHEMA)
    ids, mat = unit_matrix(con, model)
    if not ids:
        return 0
    Y = tsne(mat.astype("float64"), log=log)
    Y = (Y - Y.min(0)) / (Y.max(0) - Y.min(0) + 1e-9)
    con.execute("DELETE FROM unit_xy WHERE model=?", (model,))
    con.executemany("INSERT INTO unit_xy VALUES(?,?,?,?)",
                    [(model, uid, float(x), float(y)) for uid, (x, y) in zip(ids, Y)])
    con.commit()
    return len(ids)

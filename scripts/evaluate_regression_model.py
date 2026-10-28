"""Evaluación técnica del modelo de ventas: CV temporal y curva de aprendizaje, solo sobre train (2016-2023)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

import sales_forecast as sf

EVAL_DIR = sf.ROOT / "data" / "eval"
N_SPLITS, VAL_MONTHS = 5, 12
# Mismos hiperparámetros que sales_forecast.train_model (línea base evaluada).
BASE_PARAMS = {"n_estimators": 500, "min_samples_leaf": 2, "max_features": 1.0}
CANDIDATES = {
    "base (leaf=2, mf=1.0)": BASE_PARAMS,
    "leaf=4": {**BASE_PARAMS, "min_samples_leaf": 4},
    "leaf=8": {**BASE_PARAMS, "min_samples_leaf": 8},
    "leaf=4, mf=0.5": {**BASE_PARAMS, "min_samples_leaf": 4, "max_features": 0.5},
}


def make_folds(n_rows: int) -> list[tuple[np.ndarray, np.ndarray]]:
    tscv = TimeSeriesSplit(n_splits=N_SPLITS, test_size=VAL_MONTHS)
    return list(tscv.split(np.arange(n_rows)))


def assert_chronological(folds: list[tuple[np.ndarray, np.ndarray]]) -> None:
    prev_val_end = -1
    for tr, va in folds:
        assert (np.diff(tr) == 1).all() and (np.diff(va) == 1).all(), "índices no contiguos/ordenados"
        assert set(tr).isdisjoint(va), "solapamiento train/val"
        assert tr.max() < va.min(), "validación anterior al entrenamiento"
        assert va.min() > prev_val_end, "los folds no avanzan en el tiempo"
        prev_val_end = va.max()


def fit(train: pd.DataFrame, params: dict) -> RandomForestRegressor:
    # Features construidas solo con `train` (el fold), nunca con la serie completa.
    X, y = sf.build_training_set(train)
    model = RandomForestRegressor(random_state=sf.SEED, n_jobs=1, **params)
    return model.fit(X, y)


def errors(actual: np.ndarray, pred: np.ndarray) -> dict:
    mae = mean_absolute_error(actual, pred)
    rmse = float(np.sqrt(mean_squared_error(actual, pred)))
    return {"mae": float(mae), "rmse": rmse, "rmse_pct_mean": rmse / actual.mean() * 100}


def train_errors(model: RandomForestRegressor, train: pd.DataFrame) -> dict:
    X, _ = sf.build_training_set(train)
    rev = train["revenue_eur"].to_numpy()
    pred = model.predict(X) * rev[:-12]
    return errors(rev[12:], pred)


def val_errors(model: RandomForestRegressor, train: pd.DataFrame, val: pd.DataFrame) -> dict:
    pred, *_ = sf.forecast(model, train, val)
    return errors(val["revenue_eur"].to_numpy(), pred)


def val_errors_one_step(model: RandomForestRegressor, train: pd.DataFrame, val: pd.DataFrame) -> dict:
    """Pronóstico a 1 mes con lags reales: comparable con el error de entrenamiento (sin acumulación recursiva)."""
    history = train["revenue_eur"].tolist()
    actual = val["revenue_eur"].tolist()
    pred = []
    for month, y in zip(val["month"], actual):
        ratio = model.predict(np.array([sf.features_at(history, month)]))[0]
        pred.append(ratio * history[-12])
        history.append(y)
    return errors(np.array(actual), np.array(pred))


def run_cv(train: pd.DataFrame, params: dict) -> pd.DataFrame:
    folds = make_folds(len(train))
    assert_chronological(folds)
    rows = []
    for k, (tr, va) in enumerate(folds, 1):
        tr_df, va_df = train.iloc[tr].reset_index(drop=True), train.iloc[va].reset_index(drop=True)
        model = fit(tr_df, params)
        t, v = train_errors(model, tr_df), val_errors(model, tr_df, va_df)
        v1 = val_errors_one_step(model, tr_df, va_df)
        rows.append({
            "fold": k, "train_months": len(tr), "val_start": f"{va_df['month'].min():%Y-%m}",
            "train_mae": t["mae"], "train_rmse": t["rmse"],
            "val_mae": v["mae"], "val_rmse": v["rmse"], "val_rmse_pct_mean": v["rmse_pct_mean"],
            "val1_mae": v1["mae"], "val1_rmse": v1["rmse"], "val1_rmse_pct_mean": v1["rmse_pct_mean"],
        })
    return pd.DataFrame(rows)


def summarize(cv: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in cv.columns if c.startswith(("train_mae", "train_rmse", "val_", "val1_")) and c != "val_start"]
    return pd.DataFrame({"mean": cv[cols].mean(), "std": cv[cols].std(ddof=1)})


def learning_curve(train: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Validación fija = últimos 12 meses del train; entrenamiento = prefijos crecientes anteriores."""
    val = train.iloc[-VAL_MONTHS:].reset_index(drop=True)
    pool = train.iloc[:-VAL_MONTHS]
    rows = []
    for n in range(24, len(pool) + 1, 12):
        tr_df = pool.iloc[:n].reset_index(drop=True)
        model = fit(tr_df, params)
        t, v = train_errors(model, tr_df), val_errors(model, tr_df, val)
        rows.append({"train_months": n, "train_rmse": t["rmse"], "val_rmse": v["rmse"]})
    return pd.DataFrame(rows)


def plot_learning_curve(lc: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(lc["train_months"], lc["train_rmse"], marker="o", label="Entrenamiento")
    ax.plot(lc["train_months"], lc["val_rmse"], marker="o", label="Validación (2023)")
    ax.set_xlabel("Meses de entrenamiento")
    ax.set_ylabel("RMSE (EUR)")
    ax.set_title("Curva de aprendizaje - Random Forest, ingresos TrackFlow")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    train, _ = sf.split_train_test(sf.load_sales())  # el test 2024-2025 no se toca
    print(f"Ingreso mensual medio (train): {train['revenue_eur'].mean():,.0f} EUR")

    cv = run_cv(train, BASE_PARAMS)
    cv.to_csv(EVAL_DIR / "cv_metrics.csv", index=False)
    summary = summarize(cv)
    summary.to_csv(EVAL_DIR / "cv_summary.csv")
    print(cv.round(1).to_string(index=False))
    print(summary.round(1).to_string())

    lc = learning_curve(train, BASE_PARAMS)
    lc.to_csv(EVAL_DIR / "learning_curve.csv", index=False)
    plot_learning_curve(lc, EVAL_DIR / "learning_curve.png")
    print(lc.round(0).to_string(index=False))

    cand = []
    for name, params in CANDIDATES.items():
        s = summarize(run_cv(train, params))
        cand.append({
            "config": name,
            "train_rmse": s.loc["train_rmse", "mean"],
            "val_rmse_mean": s.loc["val_rmse", "mean"],
            "val_rmse_std": s.loc["val_rmse", "std"],
            "val_mae_mean": s.loc["val_mae", "mean"],
            "val1_rmse_mean": s.loc["val1_rmse", "mean"],
        })
    cand = pd.DataFrame(cand)
    cand.to_csv(EVAL_DIR / "candidates_cv.csv", index=False)
    print(cand.round(0).to_string(index=False))


if __name__ == "__main__":
    main()

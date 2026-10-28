"""Predicción de ingresos mensuales de TrackFlow con Random Forest (split temporal 8/2 años)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "raw" / "trackflow_sales.csv"
PLOT_PATH = ROOT / "docs" / "sales_forecast.png"
EXPECTED_COLUMNS = [
    "month",
    "revenue_eur",
    "shipments_processed",
    "avg_revenue_per_shipment_eur",
    "market",
]
TRAIN_YEARS, TEST_YEARS = 8, 2
FEATURE_NAMES = [
    "lag1", "lag2", "lag3", "roll_mean3", "roll_std3", "roll_mean12",
    "month_sin", "month_cos", "is_peak", "is_feb",
]

# Elección: Random Forest. Con solo 84 filas de entrenamiento XGBoost sobreajusta con facilidad y
# exige ajuste fino; RF es estable con hiperparámetros por defecto, explicable
# (feature_importances_) y su dispersión entre árboles da el rango de variabilidad.


def load_sales(path: Path = CSV_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    if list(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(f"Columnas inesperadas: {list(df.columns)}")
    df = df[df["market"] == "consolidated"].copy()
    df["month"] = pd.to_datetime(df["month"])
    df = df.sort_values("month").reset_index(drop=True)
    if df["revenue_eur"].isna().any():
        # Interpolación causal: solo usa el pasado, no filas futuras.
        df["revenue_eur"] = df["revenue_eur"].ffill()
    if (df["revenue_eur"] <= 0).any():
        raise ValueError("revenue_eur debe ser positivo")
    expected = pd.date_range(df["month"].min(), df["month"].max(), freq="MS")
    if len(expected) != len(df) or not (df["month"].values == expected.values).all():
        raise ValueError("Hay meses faltantes o duplicados")
    return df


def split_train_test(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Primeros 8 años = train, 2 años más recientes = test (corte temporal por año)."""
    years = sorted(df["month"].dt.year.unique())
    if len(years) < TRAIN_YEARS + TEST_YEARS:
        raise ValueError("Datos insuficientes para split 8/2 años")
    train_years = years[:TRAIN_YEARS]
    test_years = years[-TEST_YEARS:]
    train = df[df["month"].dt.year.isin(train_years)].reset_index(drop=True)
    test = df[df["month"].dt.year.isin(test_years)].reset_index(drop=True)
    return train, test


def features_at(history: list[float], month: pd.Timestamp) -> list[float]:
    """Features de un mes usando solo `history` (meses anteriores). Escala-libres: divididas por lag12."""
    base = history[-12]
    h = np.asarray(history, dtype=float)
    m = month.month
    return [
        h[-1] / base,
        h[-2] / base,
        h[-3] / base,
        h[-3:].mean() / base,
        h[-3:].std() / base,
        h[-12:].mean() / base,
        np.sin(2 * np.pi * m / 12),
        np.cos(2 * np.pi * m / 12),
        float(m in (11, 12)),
        float(m == 2),
    ]


def build_training_set(train: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Target = ingreso / ingreso 12 meses antes (el RF no extrapola niveles, sí ratios)."""
    rev = train["revenue_eur"].tolist()
    X, y = [], []
    for i in range(12, len(rev)):
        X.append(features_at(rev[:i], train["month"].iloc[i]))
        y.append(rev[i] / rev[i - 12])
    return np.array(X), np.array(y)


def train_model(train: pd.DataFrame) -> tuple[RandomForestRegressor, np.ndarray]:
    X, y = build_training_set(train)
    model = RandomForestRegressor(n_estimators=500, min_samples_leaf=2, random_state=SEED, n_jobs=1)
    model.fit(X, y)
    # PSI compara scores del modelo en train vs test (ambos suavizados por el promedio de árboles).
    return model, model.predict(X)


def forecast(model: RandomForestRegressor, train: pd.DataFrame, test: pd.DataFrame):
    """Pronóstico recursivo: el test nunca se usa como entrada, solo las predicciones previas."""
    history = train["revenue_eur"].tolist()
    mean, low, high, ratios = [], [], [], []
    for month in test["month"]:
        x = np.array([features_at(history, month)])
        tree_preds = np.array([t.predict(x)[0] for t in model.estimators_])
        base = history[-12]
        pred = tree_preds.mean() * base
        mean.append(pred)
        low.append(np.percentile(tree_preds, 10) * base)
        high.append(np.percentile(tree_preds, 90) * base)
        ratios.append(tree_preds.mean())
        history.append(pred)
    return np.array(mean), np.array(low), np.array(high), np.array(ratios)


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 5) -> float:
    """Population Stability Index con cortes por cuantiles de `expected`."""
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def _gini(actual: np.ndarray, pred: np.ndarray) -> float:
    order = np.argsort(-pred, kind="stable")
    a = actual[order]
    lorenz = np.cumsum(a) / a.sum()
    n = len(a)
    return float(lorenz.sum() / n - (n + 1) / (2 * n))


def normalized_gini(actual: np.ndarray, pred: np.ndarray) -> float:
    return _gini(actual, pred) / _gini(actual, actual)


def evaluate(test: pd.DataFrame, pred: np.ndarray, train_ratios: np.ndarray, pred_ratios: np.ndarray) -> dict:
    actual = test["revenue_eur"].to_numpy()
    return {
        "MSE": float(mean_squared_error(actual, pred)),
        "RMSE": float(np.sqrt(mean_squared_error(actual, pred))),
        "MAPE_%": float(np.mean(np.abs(actual - pred) / actual) * 100),
        "PSI": psi(train_ratios, pred_ratios),
        "Gini": normalized_gini(actual, pred),
        "K2": float(r2_score(actual, pred)),
    }


def plot(train: pd.DataFrame, test: pd.DataFrame, mean, low, high, path: Path = PLOT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(train["month"].iloc[-24:], train["revenue_eur"].iloc[-24:], color="grey", label="Histórico (train)")
    ax.plot(test["month"], test["revenue_eur"], color="black", label="Real (test)")
    ax.plot(test["month"], mean, color="tab:blue", label="Predicción RF")
    ax.fill_between(test["month"], low, high, color="tab:blue", alpha=0.25, label="Rango P10-P90 entre árboles")
    ax.set_title("TrackFlow: ingresos mensuales, predicción vs real (2024-2025)")
    ax.set_ylabel("revenue_eur")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> dict:
    df = load_sales()
    train, test = split_train_test(df)
    model, train_ratios = train_model(train)
    mean, low, high, pred_ratios = forecast(model, train, test)
    metrics = evaluate(test, mean, train_ratios, pred_ratios)
    plot(train, test, mean, low, high)
    print(f"Train: {train['month'].min():%Y-%m} a {train['month'].max():%Y-%m} ({len(train)} meses)")
    print(f"Test:  {test['month'].min():%Y-%m} a {test['month'].max():%Y-%m} ({len(test)} meses)")
    for k, v in metrics.items():
        print(f"{k}: {v:,.4f}")
    importances = sorted(zip(FEATURE_NAMES, model.feature_importances_), key=lambda t: -t[1])
    print("Importancias:", ", ".join(f"{n}={v:.3f}" for n, v in importances[:5]))
    return metrics


if __name__ == "__main__":
    main()

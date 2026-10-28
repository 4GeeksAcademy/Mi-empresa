import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import sales_forecast as sf  # noqa: E402


def test_split_8_2_sin_fuga():
    df = sf.load_sales()
    train, test = sf.split_train_test(df)

    assert train["month"].dt.year.nunique() == 8
    assert test["month"].dt.year.nunique() == 2
    assert train["month"].min() == pd.Timestamp("2016-01-01")
    assert train["month"].max() == pd.Timestamp("2023-12-01")
    assert test["month"].min() == pd.Timestamp("2024-01-01")
    assert test["month"].max() == pd.Timestamp("2025-12-01")
    assert train["month"].max() < test["month"].min()
    assert set(train["month"]).isdisjoint(test["month"])
    assert len(train) == 96 and len(test) == 24


def test_features_no_usan_el_futuro():
    df = sf.load_sales()
    train, _ = sf.split_train_test(df)
    history = train["revenue_eur"].tolist()[:30]
    month = train["month"].iloc[30]
    full = train["revenue_eur"].tolist()
    assert sf.features_at(history, month) == sf.features_at(full[:30], month)
    assert full[30] not in history

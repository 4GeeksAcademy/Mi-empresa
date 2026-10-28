import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import evaluate_regression_model as ev  # noqa: E402
import sales_forecast as sf  # noqa: E402


@pytest.fixture(scope="module")
def train():
    return sf.split_train_test(sf.load_sales())[0]


def test_folds_preservan_orden_cronologico(train):
    folds = ev.make_folds(len(train))
    assert len(folds) >= 5
    ev.assert_chronological(folds)
    for tr, va in folds:
        assert train["month"].iloc[tr].max() < train["month"].iloc[va].min()
    starts = [train["month"].iloc[va].min() for _, va in folds]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


def test_folds_no_tocan_el_test(train):
    for tr, va in ev.make_folds(len(train)):
        assert train["month"].iloc[va].max() <= np.datetime64("2023-12-01")


def test_assert_chronological_detecta_orden_roto():
    bad = [(np.arange(20, 30), np.arange(0, 10))]
    with pytest.raises(AssertionError):
        ev.assert_chronological(bad)

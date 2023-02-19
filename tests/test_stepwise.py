"""Test composite estimator class."""
import numpy as np
import numpy.testing as npt
import pytest

from sparselm.model import L2L0, Lasso, StepwiseEstimator
from sparselm.model_selection import (  # sklearn clone cannot be used by StepwiseEstimator.
    clone,
)


def test_make_composite():
    # Test making a composite estimator.
    lasso1 = Lasso(fit_intercept=True, alpha=1.0)
    lasso2 = Lasso(fit_intercept=True, alpha=2.0)
    l2l0 = L2L0(groups=[0, 0, 1, 2], alpha=0.1, eta=4.0)
    steps = [("lasso1", lasso1), ("lasso2", lasso2), ("l2l0", l2l0)]

    # Not enough scopes
    scope1 = [0, 1, 8]
    scope2 = [2, 3]
    with pytest.raises(ValueError):
        _ = StepwiseEstimator(steps, [scope1, scope2])

    # Bad scopes with overlap on 8.
    scope1 = [0, 1, 8]
    scope2 = [2, 3]
    scope3 = [4, 5, 6, 7, 8]
    with pytest.raises(ValueError):
        _ = StepwiseEstimator(steps, [scope1, scope2, scope3])

    # Bad scopes with missing index 5.
    scope1 = [0, 1, 8]
    scope2 = [2, 3]
    scope3 = [4, 6, 7]
    with pytest.raises(ValueError):
        _ = StepwiseEstimator(steps, [scope1, scope2, scope3])

    scope1 = [0, 1, 8]
    scope2 = [2, 3]
    scope3 = [4, 5, 6, 7]
    estimator = StepwiseEstimator(steps, [scope1, scope2, scope3])
    assert estimator._estimators[0].fit_intercept
    assert not estimator._estimators[1].fit_intercept
    assert not estimator._estimators[2].fit_intercept

    # check parameters. Nested estimator case not tested yet.
    params = estimator.get_params(deep=True)
    assert params["lasso1"].get_params(deep=True)["alpha"] == 1.0
    assert params["lasso2"].get_params(deep=True)["alpha"] == 2.0
    assert params["l2l0"].get_params(deep=True)["alpha"] == 0.1
    assert params["l2l0"].get_params(deep=True)["eta"] == 4.0
    assert params["lasso1__alpha"] == 1.0
    assert params["lasso2__alpha"] == 2.0
    assert params["l2l0__alpha"] == 0.1
    assert params["l2l0__eta"] == 4.0

    estimator.set_params(lasso2__alpha=0.5, l2l0__alpha=0.2, l2l0__eta=3.0)
    params = estimator.get_params(deep=True)
    assert params["lasso1"].get_params(deep=True)["alpha"] == 1.0
    assert params["lasso2"].get_params(deep=True)["alpha"] == 0.5
    assert params["l2l0"].get_params(deep=True)["alpha"] == 0.2
    assert params["l2l0"].get_params(deep=True)["eta"] == 3.0
    assert params["lasso1__alpha"] == 1.0
    assert params["lasso2__alpha"] == 0.5
    assert params["l2l0__alpha"] == 0.2
    assert params["l2l0__eta"] == 3.0

    # Test unsafe clone, such that composite can be used in the optimizers.
    # Currently, have to mute sanity check from origianl sklearn clone.
    cloned = clone(estimator)
    params = cloned.get_params(deep=True)
    assert params["lasso1"].get_params(deep=True)["alpha"] == 1.0
    assert params["lasso2"].get_params(deep=True)["alpha"] == 0.5
    assert params["l2l0"].get_params(deep=True)["alpha"] == 0.2
    assert params["l2l0"].get_params(deep=True)["eta"] == 3.0
    assert params["lasso1__alpha"] == 1.0
    assert params["lasso2__alpha"] == 0.5
    assert params["l2l0__alpha"] == 0.2
    assert params["l2l0__eta"] == 3.0


def test_toy_composite():
    lasso1 = Lasso(fit_intercept=True, alpha=1e-9)
    lasso2 = Lasso(fit_intercept=True, alpha=1e-9)
    l2l0 = L2L0(groups=[0, 0, 1, 2], alpha=0, eta=1e-9)
    steps = [("lasso1", lasso1), ("lasso2", lasso2), ("l2l0", l2l0)]

    scope1 = [0, 1, 8]
    scope2 = [2, 3]
    scope3 = [4, 5, 6, 7]
    estimator = StepwiseEstimator(steps, [scope1, scope2, scope3])

    w_test = np.random.normal(scale=2, size=9) * 0.2
    w_test[0] = 10
    w_test[-1] = 0.5
    # A bad feature matrix.
    bad_X = np.random.random(size=(20, 12))
    bad_X[:, 0] = 1
    with pytest.raises(ValueError):
        estimator.fit(bad_X, np.random.random(size=20))
    X = np.random.random(size=(20, 9))
    X[:, 0] = 1
    X[:, -1] = -8 * np.random.random(size=20)
    y = np.dot(X, w_test) + np.random.normal(scale=0.01, size=20)
    estimator.fit(X, y)
    assert estimator.intercept_ == estimator._estimators[0].intercept_
    assert not np.isclose(estimator.intercept_, 0)
    assert not np.any(np.isnan(estimator.coef_))

    for sub, scope in zip(estimator._estimators, estimator.estimator_feature_indices):
        npt.assert_array_almost_equal(sub.coef_, estimator.coef_[scope])
    coef_1 = estimator.coef_.copy()
    intercept_1 = estimator.intercept_

    # Now do not fit intercept.
    estimator._estimators[0].fit_intercept = False
    estimator.fit(X, y)
    coef_2 = estimator.coef_.copy()
    intercept_2 = estimator.intercept_
    assert np.isclose(intercept_2, 0)

    # Do some naive assertion on the fitted coefficients.
    assert abs(coef_1[0] + intercept_1 - 10) / 10 <= 0.1
    assert abs(coef_2[0] - 10) / 10 <= 0.1
    # assert np.linalg.norm(coef_2 - w_test) / np.linalg.norm(w_test) <= 0.4
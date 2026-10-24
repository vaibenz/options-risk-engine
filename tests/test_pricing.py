import numpy as np

from riskengine.pricing import bs_price


def test_known_value():
    # Hull example: S=42 K=40 r=10% sigma=20% T=0.5 -> call 4.76, put 0.81
    c = bs_price(42, 40, 0.5, 0.10, 0.0, 0.20, True)
    p = bs_price(42, 40, 0.5, 0.10, 0.0, 0.20, False)
    assert abs(c - 4.76) < 0.01
    assert abs(p - 0.81) < 0.01


def test_put_call_parity():
    S, K, T, r, q, vol = 100.0, 95.0, 0.75, 0.03, 0.01, 0.25
    c = bs_price(S, K, T, r, q, vol, True)
    p = bs_price(S, K, T, r, q, vol, False)
    assert np.isclose(c - p, S * np.exp(-q * T) - K * np.exp(-r * T))


def test_expired_is_intrinsic():
    assert bs_price(105, 100, 0.0, 0.02, 0.0, 0.3, True) == 5.0
    assert bs_price(105, 100, 0.0, 0.02, 0.0, 0.3, False) == 0.0


def test_vectorised():
    px = bs_price([90, 100, 110], 100, 1.0, 0.0, 0.0, 0.2, [True, True, False])
    assert px.shape == (3,)
    assert px[0] < px[1]


def _bump(f, x, h):
    return (f(x + h) - f(x - h)) / (2 * h)


def test_greeks_match_finite_differences():
    from riskengine.pricing import bs_greeks

    S, K, T, r, q, vol = 100.0, 105.0, 0.5, 0.02, 0.01, 0.3
    for is_call in (True, False):
        g = bs_greeks(S, K, T, r, q, vol, is_call)
        delta_fd = _bump(lambda s: bs_price(s, K, T, r, q, vol, is_call), S, 0.01)
        gamma_fd = (bs_price(S + 0.5, K, T, r, q, vol, is_call) - 2 * bs_price(S, K, T, r, q, vol, is_call)
                    + bs_price(S - 0.5, K, T, r, q, vol, is_call)) / 0.25
        vega_fd = _bump(lambda v: bs_price(S, K, T, r, q, v, is_call), vol, 1e-4) / 100
        theta_fd = (bs_price(S, K, T - 1 / 365, r, q, vol, is_call) - bs_price(S, K, T, r, q, vol, is_call))

        assert np.isclose(g["delta"], delta_fd, atol=1e-5)
        assert np.isclose(g["gamma"], gamma_fd, atol=1e-4)
        assert np.isclose(g["vega"], vega_fd, atol=1e-5)
        assert np.isclose(g["theta"], theta_fd, atol=2e-3)

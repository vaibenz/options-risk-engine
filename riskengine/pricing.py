"""Black-Scholes-Merton pricing for European options.

Everything here is vectorised with numpy so a whole book can be priced
in one call. Conventions:
    S     spot
    K     strike
    T     time to expiry in years
    r     continuously compounded risk free rate
    q     continuous dividend yield
    sigma implied vol (annualised, e.g. 0.2 for 20%)
    is_call  True for calls, False for puts
"""
import numpy as np
from scipy.stats import norm

# below this T we treat the option as expired and return intrinsic
_MIN_T = 1e-8


def _d1_d2(S, K, T, r, q, sigma):
    sqrt_t = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return d1, d2


def bs_price(S, K, T, r, q, sigma, is_call):
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    is_call = np.asarray(is_call, dtype=bool)

    T_safe = np.maximum(T, _MIN_T)
    d1, d2 = _d1_d2(S, K, T_safe, r, q, sigma)
    df_q = np.exp(-q * T_safe)
    df_r = np.exp(-r * T_safe)

    call = S * df_q * norm.cdf(d1) - K * df_r * norm.cdf(d2)
    put = K * df_r * norm.cdf(-d2) - S * df_q * norm.cdf(-d1)
    px = np.where(is_call, call, put)

    intrinsic = np.where(is_call, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
    return np.where(T <= _MIN_T, intrinsic, px)


def bs_greeks(S, K, T, r, q, sigma, is_call):
    """Analytic greeks per one option (not scaled by qty or multiplier).

    vega  is per 1 vol point (0.01 change in sigma)
    theta is per calendar day
    rho   is per 1% move in rates
    """
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    is_call = np.asarray(is_call, dtype=bool)

    T_safe = np.maximum(T, _MIN_T)
    sqrt_t = np.sqrt(T_safe)
    d1, d2 = _d1_d2(S, K, T_safe, r, q, sigma)
    df_q = np.exp(-q * T_safe)
    df_r = np.exp(-r * T_safe)
    pdf_d1 = norm.pdf(d1)

    delta = np.where(is_call, df_q * norm.cdf(d1), df_q * (norm.cdf(d1) - 1.0))
    gamma = df_q * pdf_d1 / (S * sigma * sqrt_t)
    vega = S * df_q * pdf_d1 * sqrt_t / 100.0

    common = -S * df_q * pdf_d1 * sigma / (2 * sqrt_t)
    theta_call = common - r * K * df_r * norm.cdf(d2) + q * S * df_q * norm.cdf(d1)
    theta_put = common + r * K * df_r * norm.cdf(-d2) - q * S * df_q * norm.cdf(-d1)
    theta = np.where(is_call, theta_call, theta_put) / 365.0

    rho = np.where(is_call, K * T_safe * df_r * norm.cdf(d2), -K * T_safe * df_r * norm.cdf(-d2)) / 100.0

    expired = T <= _MIN_T
    zero = np.zeros_like(delta)
    itm = np.where(is_call, S > K, S < K)
    delta = np.where(expired, np.where(itm, np.where(is_call, 1.0, -1.0), 0.0), delta)
    return {
        "delta": delta,
        "gamma": np.where(expired, zero, gamma),
        "vega": np.where(expired, zero, vega),
        "theta": np.where(expired, zero, theta),
        "rho": np.where(expired, zero, rho),
    }

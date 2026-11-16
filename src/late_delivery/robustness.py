"""Phase 3 robustness checks (ADR-0007 §7, ADR-0011).

Sensitivity to unobserved confounding (check 6, ADR-0011 §5): Cinelli and Hazlett (2020),
"Making Sense of Sensitivity", hand-rolled. The formulas follow the numeric methods of the
sensemakr R package (v0.1.6): partial_r2, robustness_value, ovb_partial_r2_bound, bias,
adjusted_estimate (reduce = TRUE) and adjusted_se.

Partial R² values come from plain-OLS (iid) fits with the headline formula, fixed effects and
singleton drop, using residual sums of squares of nested fits. The bias uses the iid SE; the
adjusted CI uses the headline's seller-clustered SE scaled by the same SE factor (ADR-0011 §5).
"""

import math
import warnings

import pyfixest as pf
from scipy.stats import t as student_t

from late_delivery.fe import CATEGORICAL_CONTROLS, FIXED_EFFECTS, NUMERIC_CONTROLS


# --- Sensitivity formulas (Cinelli and Hazlett 2020; sensemakr numeric methods) -------------------

def partial_r2(t_stat: float, dof: float) -> float:
    """Partial R² of a regressor with the outcome, from its t statistic and residual df."""
    return t_stat**2 / (t_stat**2 + dof)


def group_partial_r2(rss_restricted: float, rss_full: float) -> float:
    """Partial R² of a group of regressors: share of the restricted model's residual SS they explain."""
    if not 0 < rss_full <= rss_restricted:
        raise ValueError(f"nested fits out of order: rss_full={rss_full}, rss_restricted={rss_restricted}")
    return (rss_restricted - rss_full) / rss_restricted


def robustness_value(t_stat: float, dof: float, q: float = 1.0, alpha: float = 1.0) -> float:
    """RV_q (alpha = 1): confounder strength that cuts the estimate by 100q%; RV_{q,alpha} otherwise.

    ponytail: the 'extreme' case (sensemakr extreme_robustness_value, when q*|f| > 1/f_crit) is not
    implemented and raises; it needs |t| > dof / t_crit, far outside this project's estimates.
    """
    fq = q * abs(t_stat / math.sqrt(dof))
    f_crit = abs(student_t.ppf(alpha / 2, dof - 1)) / math.sqrt(dof - 1)
    fqa = fq - f_crit
    if fqa <= 0:
        return 0.0
    if f_crit > 0 and fq > 1 / f_crit:
        raise NotImplementedError("extreme robustness value case (q*|f| > 1/f_crit) not implemented")
    return 2 / (1 + math.sqrt(1 + 4 / fqa**2))


def ovb_partial_r2_bound(r2dxj_x: float, r2yxj_dx: float, kd: float = 1.0, ky: float | None = None) -> tuple[float, float]:
    """(R²_{D~Z|X}, R²_{Y~Z|D,X}) for a confounder kd (ky) times as strong as benchmark Xj."""
    ky = kd if ky is None else ky
    r2dz_x = kd * (r2dxj_x / (1 - r2dxj_x))
    if r2dz_x >= 1:
        raise ValueError(f"implied R2(D~Z|X) = {r2dz_x:.4f} >= 1: impossible kd = {kd}")
    r2zxj_xd = kd * r2dxj_x**2 / ((1 - kd * r2dxj_x) * (1 - r2dxj_x))
    if r2zxj_xd >= 1:
        raise ValueError(f"impossible kd = {kd}")
    r2yz_dx = ((math.sqrt(ky) + math.sqrt(r2zxj_xd)) / math.sqrt(1 - r2zxj_xd))**2 * (r2yxj_dx / (1 - r2yxj_dx))
    if r2yz_dx > 1:
        warnings.warn(f"implied R2(Y~Z|D,X) = {r2yz_dx:.4f} > 1 at k = {kd}; set to 1 (as sensemakr does)")
        r2yz_dx = 1.0
    return r2dz_x, r2yz_dx


def bias(se: float, dof: float, r2dz_x: float, r2yz_dx: float) -> float:
    """Omitted-variable bias for a confounder with the given partial R² values (sensemakr eq. 14)."""
    return math.sqrt(r2yz_dx * r2dz_x / (1 - r2dz_x)) * se * math.sqrt(dof)


def adjusted_estimate(estimate: float, se: float, dof: float, r2dz_x: float, r2yz_dx: float) -> float:
    """The estimate moved toward 0 by the bias (sensemakr reduce = TRUE)."""
    sign = -1.0 if estimate < 0 else 1.0
    return sign * (abs(estimate) - bias(se, dof, r2dz_x, r2yz_dx))


def adjusted_se(se: float, dof: float, r2dz_x: float, r2yz_dx: float) -> float:
    """SE after adjusting for the confounder; ADR-0011 §5 passes the clustered SE here."""
    return math.sqrt(1 - r2yz_dx) / math.sqrt(1 - r2dz_x) * se * math.sqrt(dof / (dof - 1))


def confounder_bounds(estimate: float, se_iid: float, se_ci: float, crit: float, dof: float,
                      r2dxj_x: float, r2yxj_dx: float, ks=(1, 2, 3)) -> list[dict]:
    """Bias-adjusted estimate and 95% CI for confounders k times as strong as one benchmark (kd = ky = k).

    se_iid feeds the bias (data geometry); se_ci and crit give the CI (ADR-0011 §5: the headline's
    clustered SE and its CI critical value).
    """
    rows = []
    for k in ks:
        r2dz_x, r2yz_dx = ovb_partial_r2_bound(r2dxj_x, r2yxj_dx, kd=k)
        est = adjusted_estimate(estimate, se_iid, dof, r2dz_x, r2yz_dx)
        se = adjusted_se(se_ci, dof, r2dz_x, r2yz_dx)
        rows.append({"k": k, "r2dz_x": r2dz_x, "r2yz_dx": r2yz_dx, "adjusted_estimate": est, "adjusted_se": se,
                     "adjusted_t": est / se, "ci95_low": est - crit * se, "ci95_high": est + crit * se})
    return rows


# --- Plain-OLS fits for partial R² ----------------------------------------------------------------

def fit_iid(f, outcome: str, terms: list[str], drop: tuple[str, ...] = ()) -> dict:
    """Headline formula fit with iid SEs (same FE, singletons dropped), optionally without some controls.

    Returns N, residual df, residual sum of squares, and the iid estimate, SE and t for each term.
    `drop` names analysis-frame control columns to leave out (a benchmark group).
    """
    unknown = set(drop) - set(CATEGORICAL_CONTROLS) - set(NUMERIC_CONTROLS)
    if unknown:
        raise ValueError(f"not a control: {sorted(unknown)}")
    rhs = list(terms) + [f"C({c})" for c in CATEGORICAL_CONTROLS if c not in drop] \
        + [c for c in NUMERIC_CONTROLS if c not in drop]
    fml = f"{outcome} ~ {' + '.join(rhs)} | {FIXED_EFFECTS}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pyfixest announces singleton drops
        m = pf.feols(fml, data=f, vcov="iid", fixef_rm="singleton")
    missing = [x for x in terms if x not in m._coefnames]
    if missing:
        raise RuntimeError(f"{fml}: term dropped as collinear: {missing}")
    coef, se, tstat = m.coef(), m.se(), m.tstat()
    return {
        "formula": fml, "n_obs": int(m._N), "dof": int(m.variance_covariance.df_t),
        "rss": float((m.resid() ** 2).sum()),
        "terms": {x: {"estimate": float(coef[x]), "se": float(se[x]), "t": float(tstat[x])} for x in terms},
    }

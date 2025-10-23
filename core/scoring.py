from typing import Dict, Any
import math

def nz(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d

def momentum_score(chg_15m, chg_1h, chg_4h, chg_24h, vol_accel):
    # clip extreme tails & weight
    s = 0.0
    s += max(min(nz(chg_15m), 50), -25) * 0.20
    s += max(min(nz(chg_1h), 50), -25) * 0.35
    s += max(min(nz(chg_4h), 60), -30) * 0.20
    s += max(min(nz(chg_24h), 80), -40) * 0.10
    s += (max(min(nz(vol_accel), 8), 0) - 1) * 12
    return s

def fundamental_score(mcap_usd, fdv_usd, circ_ratio):
    s = 0.0
    mc = nz(mcap_usd, 0)
    fdv = nz(fdv_usd, 0)
    cr = nz(circ_ratio, 0)
    if mc>0:
        s += max(0, 12 - math.log10(mc))  # smaller caps get small bonus
    if fdv>0 and mc>0:
        dil = fdv/mc
        if dil < 1.3: s += 2.0
        elif dil < 2.0: s += 0.5
        else: s -= 1.0
    if cr>0:
        if cr >= 0.6: s += 1.5
        elif cr <= 0.2: s -= 1.0
    return s

def unlock_risk_score(days_to_unlock, pct_unlock):
    # negative weight if a big unlock is imminent
    d = nz(days_to_unlock, 999)
    p = nz(pct_unlock, 0)
    s = 0.0
    if d <= 3 and p >= 1: s -= 5.0
    elif d <= 7 and p >= 1: s -= 3.0
    elif d <= 14 and p >= 1: s -= 1.5
    if p >= 5: s -= 3.0
    if p >= 10: s -= 5.0
    return s

def usage_dev_score(active_users=None, tvl_change_7d=None, commits_30d=None, contributors=None):
    s = 0.0
    if tvl_change_7d is not None:
        if tvl_change_7d > 10: s += 2.0
        elif tvl_change_7d < -10: s -= 1.0
    if commits_30d is not None:
        if commits_30d > 50: s += 2.0
        elif commits_30d > 10: s += 1.0
    if contributors is not None:
        if contributors >= 5: s += 1.0
    return s

def smart_alpha_score(components: Dict[str, Any]):
    w = dict(momentum=0.35, fundamentals=0.25, unlock=0.20, usage=0.20)
    total = (components.get("momentum",0)*w["momentum"] +
             components.get("fundamentals",0)*w["fundamentals"] +
             components.get("unlock",0)*w["unlock"] +
             components.get("usage",0)*w["usage"])
    # normalize to ~0..100-ish
    # Here we just cap to [0, 100] for display
    return max(0.0, min(100.0, total + 50))

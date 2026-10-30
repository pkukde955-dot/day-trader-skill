"""Deterministic educational ICT-inspired filter; not a validated trading edge."""
from decimal import Decimal, ROUND_DOWN

def _d(x): return Decimal(str(x))
def _valid(c):
    return all(k in c for k in ("open","high","low","close","volume","time")) and c["high"]>=c["low"]>0

def detect_setup(candles_5m,candles_1h,mark):
    neutral={"signal":"NONE","reason":"insufficient_or_invalid_data"}
    if len(candles_5m)<5 or len(candles_1h)<3 or not all(_valid(x) for x in candles_5m[-5:]+candles_1h[-3:]):
        return neutral
    m=_d(mark); h=candles_1h
    if m<=0: return neutral
    bias="LONG" if h[-1]["high"]>h[-2]["high"] and h[-1]["low"]>h[-2]["low"] else "SHORT" if h[-1]["high"]<h[-2]["high"] and h[-1]["low"]<h[-2]["low"] else "NONE"
    if bias=="NONE": return {"signal":"NONE","reason":"neutral_1h_structure"}
    a,b,c=candles_5m[-3:]
    prior=candles_5m[-4]
    long_sweep=b["low"]<min(x["low"] for x in candles_5m[-5:-2]) and c["close"]>b["low"] and c["close"]>c["open"] and c["close"]>prior["high"] and c["low"]>a["high"]
    short_sweep=b["high"]>max(x["high"] for x in candles_5m[-5:-2]) and c["close"]<b["high"] and c["close"]<c["open"] and c["close"]<prior["low"] and c["high"]<a["low"]
    if bias=="LONG" and long_sweep:
        entry=m; stop=min(b["low"],c["low"]); risk=entry-stop
        if stop<=0 or risk<=0: return {"signal":"NONE","reason":"invalid_long_risk"}
        return {"signal":"LONG","entry":entry,"stop":stop,"target":entry+risk*Decimal("2"),"reason":"1h_bullish_structure_5m_sweep_reclaim_bos_fvg"}
    if bias=="SHORT" and short_sweep:
        entry=m; stop=max(b["high"],c["high"]); risk=stop-entry
        if risk<=0: return {"signal":"NONE","reason":"invalid_short_risk"}
        return {"signal":"SHORT","entry":entry,"stop":stop,"target":entry-risk*Decimal("2"),"reason":"1h_bearish_structure_5m_sweep_reclaim_bos_fvg"}
    return {"signal":"NONE","reason":"no_full_confluence"}

def size_for_risk(equity,entry,stop,risk_fraction,quantity_step,min_quantity,leverage,max_leverage):
    eq,en,st,rf,step,mn,lev,ml=map(_d,(equity,entry,stop,risk_fraction,quantity_step,min_quantity,leverage,max_leverage))
    if min(eq,en,st,rf,step,mn,lev)>0 or en==st: pass
    else: return Decimal("0")
    if lev>ml or rf>Decimal("0.02"): return Decimal("0")
    per_unit=abs(en-st)
    risk_qty=eq*rf/per_unit
    margin_qty=eq*Decimal("0.20")*lev/en
    qty=min(risk_qty,margin_qty)
    qty=(qty/step).to_integral_value(rounding=ROUND_DOWN)*step
    return qty if qty>=mn else Decimal("0")

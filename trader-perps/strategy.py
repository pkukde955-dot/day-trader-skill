"""Read-only ICT-inspired sweep, reclaim, BOS and FVG setup detector."""
from decimal import Decimal

def D(x): return Decimal(str(x))

def bias_1h(candles):
    if len(candles) < 20: return "NEUTRAL"
    c=candles[-20:]; m=10
    h1=max(D(x["high"]) for x in c[:m]); h2=max(D(x["high"]) for x in c[m:])
    l1=min(D(x["low"]) for x in c[:m]); l2=min(D(x["low"]) for x in c[m:])
    if h2>h1 and l2>l1: return "BULLISH"
    if h2<h1 and l2<l1: return "BEARISH"
    return "NEUTRAL"

def detect_setup(candles_5m,candles_1h,mark_price,lookback=10,min_rr="2"):
    if len(candles_5m)<15 or len(candles_1h)<20:
        return {"signal":"NONE","reason":"insufficient_history"}
    mark=D(mark_price); bias=bias_1h(candles_1h)
    if mark<=0 or bias=="NEUTRAL":
        return {"signal":"NONE","reason":"invalid_mark_or_neutral_bias","htf_bias":bias}
    prior=candles_5m[-lookback-2:-2]; sweep=candles_5m[-2]; confirm=candles_5m[-1]
    ph=max(D(x["high"]) for x in prior); pl=min(D(x["low"]) for x in prior)
    sh,sl=D(sweep["high"]),D(sweep["low"]); sc=D(sweep["close"])
    co,cc=D(confirm["open"]),D(confirm["close"])
    bull_fvg=D(candles_5m[-1]["low"])>D(candles_5m[-3]["high"])
    bear_fvg=D(candles_5m[-1]["high"])<D(candles_5m[-3]["low"])
    rr=D(min_rr)
    if bias=="BULLISH" and sl<pl and sc>pl and cc>sh and cc>co and bull_fvg and mark>sl:
        return {"signal":"LONG","reason":"sell_side_sweep_reclaim_bos_fvg","htf_bias":bias,
                "entry":mark,"stop":sl,"target":mark+(mark-sl)*rr,"risk_reward":rr}
    if bias=="BEARISH" and sh>ph and sc<ph and cc<sl and cc<co and bear_fvg and mark<sh:
        return {"signal":"SHORT","reason":"buy_side_sweep_reject_bos_fvg","htf_bias":bias,
                "entry":mark,"stop":sh,"target":mark-(sh-mark)*rr,"risk_reward":rr}
    return {"signal":"NONE","reason":"no_full_confluence","htf_bias":bias}

def size_for_risk(equity,entry,stop,risk_fraction,quantity_step,min_quantity,leverage,max_leverage,max_margin_fraction="0.20"):
    from decimal import ROUND_DOWN
    equity,entry,stop,step=map(D,(equity,entry,stop,quantity_step))
    risk,minimum,lev,cap=map(D,(risk_fraction,min_quantity,leverage,max_leverage))
    mf=D(max_margin_fraction); distance=abs(entry-stop)
    if min(equity,entry,step,minimum,lev,distance)<=0: raise ValueError("Sizing inputs must be positive")
    if risk<=0 or risk> D("0.05") or lev<1 or lev>cap or not 0<mf<=1:
        raise ValueError("Risk/leverage/margin cap invalid")
    raw=equity*risk/distance; margin_cap=equity*mf*lev/entry
    qty=(min(raw,margin_cap)/step).to_integral_value(rounding=ROUND_DOWN)*step
    return qty if qty>=minimum else D("0")

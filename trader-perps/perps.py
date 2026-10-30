#!/usr/bin/env python3
"""CoinDCX USDT perpetual scanner and paper-entry CLI; no live trading."""
import argparse,json,os,sys,time
from decimal import Decimal
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
sys.path.insert(0,os.path.join(ROOT,"trader-scanner","crypto")); sys.path.insert(0,HERE)
from coindcx_perps import CoinDCXPerpsClient,PerpsDataError
from perps_paper import PerpsPaperTrader,PaperPerpsError
from strategy import detect_setup,size_for_risk

def safe(v):
    if isinstance(v,Decimal): return str(v)
    if isinstance(v,dict): return {k:safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)): return [safe(x) for x in v]
    return v

def scan(client,pair):
    ins=client.instrument(pair); ticker=client.ticker_for(pair); now=int(time.time())
    m=ticker.get("mp")
    if m is None: raise PerpsDataError("No documented mark price")
    c5=client.candles(pair,"5m",now-3*86400,now)
    c1=client.candles(pair,"1h",now-30*86400,now)
    setup=detect_setup(c5,c1,m)
    return {"pair":pair,"mark_price":m,"ticker_timestamp":ticker.get("timestamp"),
      "instrument":{"quantity_increment":ins["quantity_increment"],"min_trade_size":ins["min_trade_size"],
        "price_increment":ins["price_increment"],"funding_frequency":ins.get("funding_frequency")},
      "funding":client.funding_snapshot(ticker,ins),"candles_5m":len(c5),"candles_1h":len(c1),"setup":setup}

def main():
    p=argparse.ArgumentParser(description="CoinDCX USDT perpetual paper trader")
    p.add_argument("command",choices=("scan","paper-entry")); p.add_argument("--pairs",default="B-BTC_USDT,B-ETH_USDT")
    p.add_argument("--balance",default="1000"); p.add_argument("--risk",default="0.005")
    p.add_argument("--leverage",default="2"); p.add_argument("--journal",default="trader/perps-paper.jsonl")
    p.add_argument("--output",default="trader/perps-watchlist.json"); a=p.parse_args()
    client=CoinDCXPerpsClient(); rows=[]
    for pair in filter(None,(x.strip() for x in a.pairs.split(","))):
      try:
        row=scan(client,pair)
        if a.command=="paper-entry" and row["setup"]["signal"] in ("LONG","SHORT"):
          meta,s=row["instrument"],row["setup"]; engine=PerpsPaperTrader(starting_balance=a.balance,journal_path=a.journal)
          qty=size_for_risk(engine.status()["equity"],s["entry"],s["stop"],a.risk,
             meta["quantity_increment"],meta["min_trade_size"],a.leverage,a.leverage)
          if qty<=0: row["paper_result"]={"status":"BLOCKED","reason":"risk_cap_or_minimum_quantity"}
          else:
            result=engine.open_position(pair,s["signal"],s["entry"],qty,a.leverage,
              "signal-"+str(row["ticker_timestamp"])+"-"+pair,
              quantity_step=meta["quantity_increment"],min_quantity=meta["min_trade_size"])
            row["paper_result"]={"status":"OPENED",**safe(result)}
        rows.append(row)
      except (PerpsDataError,PaperPerpsError,ValueError) as e: rows.append({"pair":pair,"status":"ERROR","reason":str(e)})
    payload={"mode":"PAPER_ONLY","live_trading_enabled":False,"generated_at":int(time.time()),"results":rows}
    os.makedirs(os.path.dirname(a.output) or ".",exist_ok=True)
    with open(a.output,"w",encoding="utf-8") as f: json.dump(safe(payload),f,indent=2)
    print(json.dumps(safe(payload),indent=2))
    return 0 if rows and all(x.get("status")!="ERROR" for x in rows) else 1
if __name__=="__main__": raise SystemExit(main())

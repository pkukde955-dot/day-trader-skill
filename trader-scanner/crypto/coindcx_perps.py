"""Read-only CoinDCX USDT perpetual market data client (documented public APIs only)."""
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from decimal import Decimal

API = "https://api.coindcx.com"
PUBLIC = "https://public.coindcx.com"

class PerpsDataError(Exception):
    pass

def _get(url, timeout=8):
    req = Request(url, headers={"User-Agent":"day-trader-skill-perps/1.0","Accept":"application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise PerpsDataError("HTTP status %s" % response.status)
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise PerpsDataError("Response exceeds safety limit")
        return json.loads(raw.decode("utf-8"))
    except PerpsDataError:
        raise
    except Exception as exc:
        raise PerpsDataError("CoinDCX public data request failed: %s" % exc) from exc

class CoinDCXPerpsClient:
    def __init__(self, max_age_ms=15000):
        self.max_age_ms = int(max_age_ms)
        self._instruments = {}

    def active_instruments(self):
        data = _get(API + "/exchange/v1/derivatives/futures/data/active_instruments?" +
                    urlencode({"margin_currency_short_name[]":"USDT"}))
        if not isinstance(data, list):
            raise PerpsDataError("Unexpected active-instruments payload")
        return [x for x in data if isinstance(x,str) and x.startswith("B-") and x.endswith("_USDT")]

    def instrument(self, pair):
        if pair not in self._instruments:
            if pair not in self.active_instruments():
                raise PerpsDataError("Pair is not an active USDT perpetual: " + str(pair))
            data = _get(API + "/exchange/v1/derivatives/futures/data/instrument?" +
                        urlencode({"pair":pair,"margin_currency_short_name":"USDT"}))
            item = data.get("instrument") if isinstance(data,dict) else None
            if not isinstance(item,dict) or item.get("pair") != pair or item.get("kind") != "perpetual" or item.get("status") != "active":
                raise PerpsDataError("Instrument metadata failed validation")
            for key in ("quantity_increment","min_trade_size","price_increment"):
                if Decimal(str(item.get(key,"0"))) <= 0:
                    raise PerpsDataError("Invalid instrument field: " + key)
            self._instruments[pair] = item
        x=self._instruments[pair]
        return {"quantity_increment":Decimal(str(x["quantity_increment"])),
                "min_trade_size":Decimal(str(x["min_trade_size"])),
                "price_increment":Decimal(str(x["price_increment"])),
                "funding_frequency":x.get("funding_frequency"),"raw":x}

    def ticker_for(self, pair):
        data = _get(PUBLIC + "/market_data/v3/current_prices/futures/rt")
        prices = data.get("prices") if isinstance(data,dict) else None
        item = prices.get(pair) if isinstance(prices,dict) else None
        if not isinstance(item,dict):
            raise PerpsDataError("No current futures ticker for " + pair)
        ts = item.get("bmST") or data.get("ts")
        now = int(time.time()*1000)
        if not isinstance(ts,(int,float)) or ts <= 0 or now-ts > self.max_age_ms or ts-now > 5000:
            raise PerpsDataError("Stale or invalid mark-price timestamp for " + pair)
        try:
            mark=Decimal(str(item["mp"]))
            if not mark.is_finite() or mark <= 0: raise ValueError()
        except Exception as exc:
            raise PerpsDataError("Invalid mark price for " + pair) from exc
        return {"mp":mark,"last_price":Decimal(str(item.get("ls",item["mp"]))),
                "funding_rate":item.get("fr"),"effective_funding_rate":item.get("efr"),
                "timestamp":int(ts),"raw":item}

    def candles(self, pair, interval, start, end):
        resolution={"5m":"5","1h":"60"}.get(interval)
        if not resolution: raise PerpsDataError("Only documented 5m and 1h resolutions supported")
        if int(end)<=int(start): raise PerpsDataError("Invalid candle time range")
        url=PUBLIC+"/market_data/candlesticks?"+urlencode({"pair":pair,"from":int(start),"to":int(end),"resolution":resolution,"pcode":"f"})
        data=_get(url)
        if not isinstance(data,list) or not data: raise PerpsDataError("No futures candles returned")
        rows=[]
        for c in data:
            try:
                row={k:Decimal(str(c[k])) for k in ("open","high","low","close","volume")}
                row["time"]=int(c["time"])
                if any(not v.is_finite() for v in row.values() if isinstance(v,Decimal)): raise ValueError()
                if row["low"]<=0 or row["high"]<max(row["open"],row["close"],row["low"]) or row["low"]>min(row["open"],row["close"]): raise ValueError()
                rows.append(row)
            except Exception as exc: raise PerpsDataError("Malformed candle payload") from exc
        rows.sort(key=lambda x:x["time"])
        if len({x["time"] for x in rows}) != len(rows): raise PerpsDataError("Duplicate candle timestamps")
        return rows

    def trades(self, pair, limit=100):
        if not 1 <= int(limit) <= 500: raise PerpsDataError("Trade limit must be 1..500")
        data=_get(API+"/exchange/v1/derivatives/futures/data/trades?"+urlencode({"pair":pair}))
        if not isinstance(data,list): raise PerpsDataError("Malformed futures trades")
        return data[-int(limit):]

    def orderbook(self, pair, depth=50):
        if depth not in (10,20,50): raise PerpsDataError("Orderbook depth must be 10, 20 or 50")
        data=_get(PUBLIC+"/market_data/v3/orderbook/"+pair+"-futures/"+str(depth))
        if not isinstance(data,dict) or not isinstance(data.get("bids"),dict) or not isinstance(data.get("asks"),dict):
            raise PerpsDataError("Malformed futures orderbook")
        if not data["bids"] or not data["asks"]: raise PerpsDataError("Empty futures orderbook")
        return data

    def funding_snapshot(self, ticker, instrument):
        rate=ticker.get("funding_rate")
        return {"funding_rate":rate,"effective_funding_rate":ticker.get("effective_funding_rate"),
                "mark_timestamp":ticker.get("timestamp"),
                "note":"Observed public ticker fields only; no funding schedule or settlement is inferred."}

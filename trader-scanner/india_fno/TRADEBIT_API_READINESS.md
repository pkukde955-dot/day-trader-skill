# Tradebit API readiness - NSE/BSE F&O

**Status checked:** 2026-10-26  
**Repository branch:** `feat/india-fno-readonly-probe`  
**Purpose:** document what is and is not verified before implementing a Tradebit adapter.

## Verified from public documentation

- Official API documentation site and introduction: https://apidocs.tradebit.io/
- The public API reference includes login and OTP-verification routes under `/api/login` and `/api/verifyLogin`. These establish an account-authentication flow, not broker trading authorization or an order API.
- The public crypto reference documents endpoints such as `/dashboard/all-symbols`, `/list-crypto/get`, `/chart`, and `/list-crypto/market-data/{symbol}`. These are documented as crypto data endpoints and do not establish NSE/BSE cash or F&O market-data support.
- The public documentation also includes crypto wallet functions. Wallet and crypto API coverage must not be treated as proof of Indian exchange derivatives support.
- In the public documentation checked for this review, I did not verify the full NSE/BSE F&O contracts required for a safe broker integration. Treat all items in the checklist below as unverified until an official, explicit contract is found.

## Not yet verified - do not guess these contracts

Before writing a Tradebit adapter, locate explicit official documentation for each item below and record the exact path, HTTP method, required fields, authentication/signature scheme, response schema, rate limits, and supported exchange segment:

- [ ] NSE F&O and BSE F&O instrument/contract master, including expiry, strike, CE/PE, lot size and tick size
- [ ] Real-time quote / market-data stream, timestamp semantics and stale-data handling
- [ ] Funds, available margin and margin preview/estimate
- [ ] Place order (including limit order, quantity units, product type and exchange-segment codes)
- [ ] Order book/status and trade/fill lookup
- [ ] Modify and cancel order
- [ ] Open positions and position close/square-off
- [ ] API key setup, authentication, request signing, OTP/session expiry and error codes

**Important:** login or OTP documentation by itself does not verify trading endpoints. Generic endpoints from another broker must not be copied into the Tradebit adapter.

## Implementation sequence

1. **Read-only contract discovery:** verify official documentation and, only with user-owned credentials stored locally, test documented read-only endpoints. Never put credentials in chat or commit them.
2. **Market data:** normalize symbol, exchange segment, instrument identity, timestamp, price and source; reject missing, stale, malformed or non-finite values. Clearly label data as unverified until source freshness and contract mapping are validated.
3. **Signal and risk plan:** produce a risk-sized order intent using a verified contract master, lot size, tick size, margin estimate and the user's configured risk limits.
4. **Review and confirmation:** display one exact order ticket; require an explicit affirmative response for that exact ticket. Any material change invalidates the confirmation.
5. **Execution adapter:** implement only against documented Tradebit contracts. Require a risk-gate PASS, fresh data, a unique idempotency key, duplicate-order protection, order-status reconciliation and a kill switch. An ambiguous timeout must be reconciled before retrying.
6. **Paper/mock tests first:** cover malformed API responses, stale data, invalid lot/tick increments, insufficient margin, rejected orders, duplicate submissions, timeout-after-submit and cancel/modify failures.
7. **Small live validation:** only after the documented adapter and tests pass, with the user explicitly enabling live mode and confirming each exact order.

## Current code boundary

`order_intent.py` is a pure risk-sizing helper. It accepts caller-supplied reference prices and deliberately returns:

- `market_data_verified: false`
- `broker_connected: false`
- `order_placed: false`
- `status: AWAITING_USER_REVIEW`

It is not a market-data client, Tradebit adapter, or live-order system. Keep those claims false until the relevant integrations are implemented and verified.

## Evidence / links

- Official Tradebit API introduction: https://apidocs.tradebit.io/
- Official authentication reference: https://apidocs.tradebit.io/api-reference/public-apis/auth
- Official crypto API reference: https://apidocs.tradebit.io/api-reference/public-apis/crypto
- Official wallet withdrawal reference (crypto wallet scope): https://apidocs.tradebit.io/api-reference/private-apis/wallet/withdraw
- Existing project order-intent helper: `trader-scanner/india_fno/order_intent.py`
- Existing read-only feasibility probe: `trader-scanner/india_fno/probe.py`

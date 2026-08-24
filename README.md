# Adaptive Intelligent Market Research Bot

Production-oriented starter project for a market-research web application covering stocks, forex, and crypto.

## Architecture

- `backend/`: FastAPI + Python 3.11+
- `frontend/`: Vite + React + TypeScript
- `backend/app/providers/`: provider adapters
- `backend/app/services/`: canonical quote service, validation and scoring
- `backend/app/api/`: HTTP endpoints
- `.env.example`: configuration template
- `docker-compose.yml`: local development

## Important

The application never treats hardcoded demo prices as live market prices.

If `TWELVE_DATA_API_KEY` is missing or the provider fails, the API returns `UNAVAILABLE` rather than silently displaying fabricated prices.

The Twelve Data integration uses the `/price` endpoint for latest price retrieval. Provider credentials remain backend-only.

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
copy ..\.env.example .env
# Edit .env and add TWELVE_DATA_API_KEY

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8000` in `frontend/.env.local` if needed.

## API

- `GET /health`
- `GET /api/market/quote/{symbol}`
- `GET /api/market/quotes?symbols=BTC/USD,ETH/USD,EUR/USD,NVDA,SPY`
- `GET /api/market/status`
- `GET /api/providers/status`
- `GET /api/market/scanner`

## Production rules

1. Never put provider API keys in frontend code.
2. Never use a stale/demo price as a live fallback.
3. Every quote includes `timestamp`, `source`, `status`, and `market_open` where available.
4. Add caching before increasing polling frequency.
5. Add Alpha Vantage/Finnhub adapters only behind the same `MarketDataProvider` interface.
6. Keep research/scoring dependent on validated canonical market snapshots.

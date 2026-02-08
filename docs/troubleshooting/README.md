# Troubleshooting

## Activity feed is blank / frontend API calls fail

**Symptoms**
- Activity feed shows no items.
- The browser console/network tab shows failed requests to `/api/v1/*`.

**Cause**
- `NEXT_PUBLIC_API_URL` is missing/blank/incorrect. The frontend uses this variable to build API URLs.

**Fix**
- Local dev: set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.
- Docker Compose (self-host): set `NEXT_PUBLIC_API_URL=http://localhost:8000` in the root `.env` used by compose (or update it to match your actual backend host/port).

Notes:
- `NEXT_PUBLIC_API_URL` must be reachable from the browser. If you're using Docker Compose, don't set it to an internal service name like `http://backend:8000` unless the browser can resolve it.

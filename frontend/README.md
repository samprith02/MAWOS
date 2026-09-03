# MAWOS React frontend

The frontend is a Vite React application using React Router, Tailwind CSS,
Lucide, Recharts, and a centralized `/api` client. The Vite development
server proxies `/api` to FastAPI at `http://127.0.0.1:8000`.

```bash
cd frontend
npm install
npm run dev
```

For production, run `npm run build`; FastAPI serves `frontend/dist` and uses
an SPA fallback for client routes. Existing `frontend/static/` files are kept
as the legacy rollback frontend and remain available under `/static`.

## Deliberately unavailable presentation areas

`src/data/mockAdapter.js` contains the only presentation placeholders. The
current FastAPI contract has no endpoints for library records, event check-in,
user/permission administration, backup/redeploy controls, or infrastructure
metrics. The UI labels these as unavailable instead of sending invented API
requests or simulating state-changing operations.

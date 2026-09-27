# Carewise frontend

Next.js 16 (App Router) + TypeScript + Tailwind v4. See the root [README](../README.md) for the full picture.

```bash
pnpm install
pnpm dev            # http://localhost:3100 (expects the API on :8000; NEXT_PUBLIC_API_URL overrides)
pnpm gen:api        # regenerate src/lib/api/schema.d.ts from ../backend/openapi.json
pnpm typecheck && pnpm lint && pnpm build
pnpm test:e2e       # Playwright + axe; starts the backend in MOCK mode itself (zero API calls)
```

| Route | What |
|---|---|
| `/` | Landing |
| `/chat` | The conversation: progress ring, editable summary, recommendation |
| `/trace/[id]` | Developer Decision Trace: workflow, Jev probabilities, policy overrides, timeline |

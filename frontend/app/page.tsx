/**
 * Milestone F0 — trivial connectivity check.
 *
 * `cache: 'no-store'` forces this fetch (and this page) to be dynamic —
 * without it, Next.js can pick up an unauthenticated `fetch` with no
 * cache option during `next build` and bake a stale result into a
 * prerendered static page, which would defeat the point of a live
 * connectivity check. See the Next.js 16 caching docs bundled in
 * node_modules/next/dist/docs/ (this project doesn't have Cache
 * Components enabled, so the "previous model" applies: fetch is
 * uncached by default, but the route itself can still be statically
 * prerendered unless something forces it dynamic).
 *
 * This is intentionally a raw fetch, not routed through a shared API
 * client — that layer is Milestone F1's job. Every other page from F1
 * onward should go through it instead of calling fetch directly.
 */

type HealthResponse = {
  status: string;
  database: string;
  environment: string;
};

type HealthCheckResult = { ok: true; data: HealthResponse } | { ok: false; error: string };

async function checkBackendHealth(): Promise<HealthCheckResult> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    return { ok: false, error: 'NEXT_PUBLIC_API_BASE_URL is not set' };
  }

  try {
    const response = await fetch(`${baseUrl}/health`, { cache: 'no-store' });
    if (!response.ok) {
      return { ok: false, error: `Backend responded with HTTP ${response.status}` };
    }
    const data = (await response.json()) as HealthResponse;
    return { ok: true, data };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, error: `Could not reach ${baseUrl}: ${message}` };
  }
}

export default async function Home() {
  const result = await checkBackendHealth();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-8 font-sans">
      <main className="flex w-full max-w-md flex-col gap-4 rounded-lg border border-border bg-card p-8">
        <h1 className="text-xl font-semibold text-foreground">Field Service Platform</h1>
        <p className="text-sm text-muted-foreground">Backend connectivity check</p>

        {result.ok ? (
          <div className="flex flex-col gap-1 rounded-md border border-green-200 bg-green-50 p-4 dark:border-green-900 dark:bg-green-950">
            <p className="font-medium text-green-800 dark:text-green-300">Backend reachable</p>
            <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm text-green-700 dark:text-green-400">
              <dt className="font-medium">status</dt>
              <dd>{result.data.status}</dd>
              <dt className="font-medium">database</dt>
              <dd>{result.data.database}</dd>
              <dt className="font-medium">environment</dt>
              <dd>{result.data.environment}</dd>
            </dl>
          </div>
        ) : (
          <div className="flex flex-col gap-1 rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950">
            <p className="font-medium text-red-800 dark:text-red-300">Backend unreachable</p>
            <p className="text-sm text-red-700 dark:text-red-400">{result.error}</p>
          </div>
        )}
      </main>
    </div>
  );
}

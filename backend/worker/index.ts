// Thin Cloudflare Worker shim in front of the Python backend container.
//
// Cloudflare Containers are request-routed (a Durable Object wakes the
// container to answer a fetch, then lets it sleep) — there is no equivalent
// of `python -m app.worker`'s long-lived polling loop. So this Worker does
// two things:
//   1. Proxies ordinary API traffic straight through to the container.
//   2. Drives the pipeline by calling POST /internal/worker/tick on a timer,
//      via a self-perpetuating Durable Object alarm (the idiomatic Cloudflare
//      pattern for periodic background work — see
//      https://developers.cloudflare.com/durable-objects/api/alarms/).
//
// One singleton container instance (fixed Durable Object name) runs the
// whole pipeline; the alarm keeps it awake roughly every TICK_INTERVAL_MS
// regardless of API traffic, and `run_once()` in app/worker.py is a no-op
// (processed: 0) when the job queue is empty, so over-ticking is harmless.
import { Container } from "@cloudflare/containers";

interface Env {
  BACKEND: DurableObjectNamespace<Backend>;
  WORKER_TICK_SECRET: string;
  DATABASE_URL: string;
  SECRET_KEY: string;
  STORAGE_BACKEND: string;
  S3_BUCKET: string;
  S3_REGION: string;
  S3_ENDPOINT_URL: string;
  AWS_ACCESS_KEY_ID: string;
  AWS_SECRET_ACCESS_KEY: string;
  APP_ENV: string;
  ANALYSIS_PROVIDER: string;
  WORKERS_AI_ACCOUNT_ID: string;
  WORKERS_AI_API_TOKEN: string;
  WORKERS_AI_MODEL: string;
  CORS_ORIGINS: string;
}

const TICK_INTERVAL_MS = 30_000;
// Fixed name, not per-request — every request and every alarm must land on
// the same Durable Object instance for the alarm loop to mean anything.
const SINGLETON_NAME = "pipeline-worker";

export class Backend extends Container<Env> {
  defaultPort = 8000;
  // Cloudflare's own floor is ~10 minutes and it cannot be disabled; the
  // alarm below re-wakes the container well before that anyway.
  sleepAfter = "10m";

  constructor(ctx: DurableObjectState<{}>, env: Env) {
    super(ctx, env);

    // Forwarded into the container's process environment — this is how
    // app/core/config.py's Settings actually sees them (it reads os.environ,
    // not Wrangler bindings). Same names as .env.example, sourced from
    // Worker vars/secrets instead of a .env file that never ships.
    this.envVars = {
      DATABASE_URL: env.DATABASE_URL,
      SECRET_KEY: env.SECRET_KEY,
      WORKER_TICK_SECRET: env.WORKER_TICK_SECRET,
      STORAGE_BACKEND: env.STORAGE_BACKEND,
      S3_BUCKET: env.S3_BUCKET,
      S3_REGION: env.S3_REGION,
      S3_ENDPOINT_URL: env.S3_ENDPOINT_URL,
      AWS_ACCESS_KEY_ID: env.AWS_ACCESS_KEY_ID,
      AWS_SECRET_ACCESS_KEY: env.AWS_SECRET_ACCESS_KEY,
      APP_ENV: env.APP_ENV,
      ANALYSIS_PROVIDER: env.ANALYSIS_PROVIDER,
      WORKERS_AI_ACCOUNT_ID: env.WORKERS_AI_ACCOUNT_ID,
      WORKERS_AI_API_TOKEN: env.WORKERS_AI_API_TOKEN,
      WORKERS_AI_MODEL: env.WORKERS_AI_MODEL,
      CORS_ORIGINS: env.CORS_ORIGINS,
    };

    // Async work can't happen directly in a constructor — block the DO's
    // first request until the initial alarm is scheduled.
    ctx.blockConcurrencyWhile(async () => {
      const existing = await ctx.storage.getAlarm();
      if (existing === null) {
        await ctx.storage.setAlarm(Date.now() + TICK_INTERVAL_MS);
      }
    });
  }

  override onStart() {
    console.log("backend container started");
  }

  override onStop() {
    console.log("backend container stopped");
  }

  async alarm(): Promise<void> {
    try {
      const res = await this.containerFetch("/internal/worker/tick", {
        method: "POST",
        headers: { Authorization: `Bearer ${this.env.WORKER_TICK_SECRET}` },
      });
      if (!res.ok) {
        console.error(`worker tick returned ${res.status}`);
      }
    } catch (err) {
      // A transient failure (container mid-restart, DB hiccup) shouldn't
      // break the loop — just try again next tick.
      console.error("worker tick failed", err);
    }
    await this.ctx.storage.setAlarm(Date.now() + TICK_INTERVAL_MS);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const id = env.BACKEND.idFromName(SINGLETON_NAME);
    const container = env.BACKEND.get(id);
    return container.fetch(request);
  },
};

---
status: accepted
---

# Run the API on Cloud Run behind a Firebase Hosting rewrite, on a single instance

The Angular build is served from Firebase Hosting, and a rewrite sends `/api/**` to a Cloud Run service (`hr-assist-api`, `europe-west1`). The browser therefore sees a single origin. The service scales from 0 to at most 1 instance, because the per-IP and daily rate limits are counted in memory. Firebase Hosting can only forward to a publicly invokable service, and both ingress restriction and `--no-default-url` break Firebase rewrites. So the `*.run.app` URL stays public, and every protection lives inside the app rather than at the edge.

The rewrite means the static UI loads from the CDN even while the backend is cold. The production build already calls a relative `/api` path, so production needs no CORS.

Raising max-instances above 1 requires moving the rate-limit counters into a shared store first, such as Redis or Firestore. Otherwise each instance enforces its own limits and the effective limit multiplies. Firebase also caps proxied requests at 60 seconds, which rules out long-running endpoints, including streaming replies that run past it.

## Considered options

- **One container serving both the UI and the API**: simplest, but a cold start blocks the page from loading at all.
- **Split hosting with cross-origin calls**: works, but needs CORS and a preflight request on every call. It gains nothing over the rewrite.
- **HTTPS load balancer + Cloud Armor, with ingress restricted to the load balancer**: closes the public URL and adds a WAF, but costs roughly $18+/month and replaces Firebase rewrites.
- **Firebase App Check**: rejects scripted calls on any URL. Deferred to Stage 5. Until then, a bot can use up the daily quota but can't exceed the OpenAI hard limit.
- **min-instances=1**: no cold starts, at roughly $5–10/month for the idle instance.

---
status: accepted
---

# Deploy from GitHub Actions with a service account key, before moving to Workload Identity Federation

GitHub Actions logs in to Google Cloud with a JSON key for a dedicated deploy service account, stored as the `GCP_SA_KEY` repository secret. Both the deploy workflow and the prod ingest workflow use it. This goes against Google's recommendation, which is Workload Identity Federation (WIF): GitHub's OIDC token is exchanged for short-lived credentials, and no key exists. We chose the key because it is a few minutes of setup instead of a pool, a provider and an attribute condition. The project owner is new to cloud deployment and wants a working pipeline first.

The key never expires on its own. Anyone holding it can deploy to, and read secrets in, the `hr-assist-demo-512120` project until it is deleted. We limit the damage:

- The deploy account has only the roles it needs: Cloud Run admin, Artifact Registry writer, Firebase Hosting admin, Secret Manager accessor, and permission to act as the runtime service account. It has roles in this project and nowhere else.
- The key lives only in the GitHub secret, saved as one line so GitHub can hide it in logs. The local file is deleted after upload.
- The key is rotated every 90 days.

## Moving to WIF later

Create a workload identity pool and a GitHub provider restricted to `NaveenManjappa/hr-assist`. Let it act as the same deploy account. Replace `credentials_json` with `workload_identity_provider` and `service_account` in `google-github-actions/auth`, and add `id-token: write` to the workflows' permissions. Then delete the key and the secret. Nothing else in the pipeline changes. WIF becomes mandatory if the GCP account belongs to an organisation created on or after 3 May 2024, where key creation is blocked by default.

## Considered options

- **Workload Identity Federation now**: no long-lived credential, but more setup up front.
- **Cloud Build triggers**: no GitHub credential at all, but CI and CD would live in two systems.
- **Manual deploys from a laptop**: no stored credential, but deploys aren't repeatable and depend on one machine.

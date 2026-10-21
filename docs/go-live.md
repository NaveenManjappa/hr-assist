# Go live on your own subdomain (ticket #31)

This guide connects `hr-assist.naveenmanjappa.com` to the Firebase Hosting site, with the DNS records at Namecheap. It then points the Qdrant keep-alive at the new address and checks the live site answers. You do every step yourself. Each step says **what** it does, **why** we need it, and how to **check** it worked.

The hands-on part takes about 20 minutes. Then you wait for the HTTPS certificate, which usually takes a few hours and at most 24. The background is in [deployment.md](deployment.md) section 11 and decision D11.

## Before you start

- The `web.app` URL works: `curl -sS https://hr-assist-demo.web.app/api/health` prints `"status":"ok"`. If it doesn't, fix that first (deployment.md section 13).
- The prod Corpus is loaded. If you haven't run **Actions → Ingest (prod)** yet, do it now, or step 6 will fail.
- You can log in to the Firebase console and to Namecheap, and `gh auth status` says you're logged in.

## Step 0: Choose the subdomain and set the variables

The subdomain is `hr-assist.naveenmanjappa.com`. Everything below uses it, and the follow-up agent ticket reads it from issue #31 at the end.

```sh
# The variable block: run this again whenever you open a new terminal.
SUBDOMAIN=hr-assist.naveenmanjappa.com
SITE_URL=https://$SUBDOMAIN
echo "$SUBDOMAIN / $SITE_URL"
```

**Check:** the `echo` shows `hr-assist.naveenmanjappa.com / https://hr-assist.naveenmanjappa.com`.

## Step 1: Check that Namecheap runs your domain's DNS

**What:** confirm the DNS records for your domain are edited at Namecheap, not at your website's host.

**Why:** only the company running your domain's nameservers can change its records. If your website's host manages them, records added at Namecheap are ignored.

1. Open <https://ap.www.namecheap.com/domains/list/> and click **Manage** next to `naveenmanjappa.com`.
2. On the **Domain** tab, find **Nameservers**.

**Check:** it says **Namecheap BasicDNS** (or **PremiumDNS**). If it says **Custom DNS**, the records belong with whoever those nameservers point to. Add them there in step 3 instead, using the same values.

## Step 2: Add the custom domain in Firebase

**What:** tell Firebase Hosting to serve the `hr-assist-demo` site at your subdomain.

**Why:** Firebase then gives you the DNS record that points the subdomain at Firebase. It also issues the HTTPS certificate for free.

1. Open <https://console.firebase.google.com/project/hr-assist-demo-512120/hosting/sites/hr-assist-demo>.
2. Click **Add custom domain** and enter `hr-assist.naveenmanjappa.com`.
3. In the **Setup mode** switch at the top of the dialog, pick **Quick setup**. (**Advanced** is for moving a site that's already live without downtime, and it hides the address until a later stage.)
4. Firebase lists one record:

   | Record type | Domain name | Value |
   | --- | --- | --- |
   | CNAME | `hr-assist.naveenmanjappa.com` | `hr-assist-demo.web.app` |

**Check:** the domain appears in the Hosting domains list. Keep the dialog open for step 3, or reopen it later by clicking the domain.

## Step 3: Add the CNAME record at Namecheap

**What:** create the record Firebase asked for, and remove any that would get in the way.

**Why:** the CNAME sends visitors of `hr-assist.naveenmanjappa.com` to the Firebase site. DNS doesn't let a CNAME share its Host with any other record, so anything else on `hr-assist` blocks it.

1. Back at Namecheap, open the **Advanced DNS** tab for `naveenmanjappa.com`.
2. Under **Host Records**, delete every record whose Host is `hr-assist` (any `A`, `AAAA`, `TXT` or other `CNAME` record) with the bin icon. Leave records for other hosts, such as `@` and `www`, alone: they serve your website.
3. Click **Add New Record** → **CNAME Record**:
   - **Host:** `hr-assist` only. Namecheap adds your domain itself, so typing the full name would create `hr-assist.naveenmanjappa.com.naveenmanjappa.com`.
   - **Target:** `hr-assist-demo.web.app`.
   - **TTL:** Automatic.
4. Click the green tick (**Save all changes**).

**Leave the CNAME record in place for good.** Removing it takes the site down.

**Check** (Namecheap usually publishes changes within 30 minutes, so this may be empty at first):

```sh
dig +short CNAME $SUBDOMAIN @8.8.8.8   # hr-assist-demo.web.app.
```

## Step 4: Verify in Firebase and wait for the certificate

**What:** let Firebase confirm the record, then issue the HTTPS certificate.

**Why:** until the certificate exists, browsers show a security warning on your subdomain.

1. In the Firebase dialog, click **Verify**. If it says the record isn't found yet, wait 30 minutes and click again.
2. Once verified, the status moves through **Minting certificate** to **Connected**. That usually takes a few hours, and at most 24. You can close everything and come back.

**Check:** both of these work:

```sh
curl -I $SITE_URL/api/health                     # first line: HTTP/2 200, no certificate error
curl -sS $SITE_URL/api/health                    # "status":"ok" and "qdrant":"up"
curl -sS https://hr-assist-demo.web.app/api/health   # the web.app URL still works
```

A certificate error from the first command means the certificate isn't ready yet. If it's still there after 24 hours, check that `hr-assist` has only the one CNAME record at Namecheap (step 3).

## Step 5: Point the Qdrant keep-alive at the public site

**What:** set the `API_URL` repository variable, then run the keep-alive workflow once by hand.

**Why:** the keep-alive pings `/api/health` twice a week so the free Qdrant cluster isn't suspended. Until `API_URL` is set it does nothing. Using the public URL means the ping goes through the Firebase rewrite, so it tests the same path a visitor uses.

```sh
gh variable set API_URL --body "$SITE_URL"
gh workflow run qdrant-keep-alive.yml
# Wait a few seconds for the run to appear, then watch it.
gh run list --workflow qdrant-keep-alive.yml --limit 1
gh run watch <run-id from the list> --exit-status
```

**Check:** `gh variable get API_URL` prints your `$SITE_URL`, and the run finishes green. If it fails with "could not reach Qdrant", check the cluster in the Qdrant Cloud console. Its log shows the health response: `gh run view <run-id> --log-failed`.

## Step 6: Ask the smoke question on the live site

**What:** use the site the way a visitor would.

**Why:** the health check proves the backend and Qdrant are up. Only a real question proves the prod Corpus, OpenAI and the rewrite all work together.

1. Open <https://hr-assist.naveenmanjappa.com> in a browser.
2. Ask: **How much annual leave do I get after 4 years?**

**Check:** you get an Answer with Citations to the leave policy. A `503`, or "Searching the policy index failed.", means the prod Corpus isn't loaded: run **Actions → Ingest (prod)** and ask again.

## Step 7: Record the subdomain on the ticket

**What:** leave the final subdomain in a comment on issue #31.

**Why:** the follow-up agent ticket reads the subdomain from there.

```sh
gh issue comment 31 --body "Final subdomain: \`$SUBDOMAIN\` (live at $SITE_URL)."
```

**Check:** the comment shows on <https://github.com/NaveenManjappa/hr-assist/issues/31>.

## Final checklist (matches #31's acceptance criteria)

- [ ] `curl -I https://hr-assist.naveenmanjappa.com/api/health` returns 200 with a valid certificate (step 4).
- [ ] The `web.app` URL still works (step 4).
- [ ] `API_URL` is set, and a manual run of the Qdrant keep-alive workflow passes (step 5).
- [ ] On the live site, "How much annual leave do I get after 4 years?" returns an Answer with Citations from the prod Corpus (step 6).
- [ ] The final subdomain is recorded in a comment on issue #31 (step 7).

## If something goes wrong

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Firebase says the record isn't found | DNS hasn't updated yet, or the Host has the full domain in it | Wait 30 minutes. Run the `dig` check in step 3. In Namecheap, the Host should be only `hr-assist`. |
| `dig` shows nothing hours later | Namecheap isn't running the domain's DNS | Step 1: if the nameservers are Custom DNS, add the CNAME at that provider |
| Certificate error after 24 hours | Another record on `hr-assist` besides the CNAME | Delete it at Namecheap (step 3), then wait again |
| Subdomain loads but `/api/health` returns 404 | The Firebase rewrite to Cloud Run isn't deployed | Check `firebase.json` and the latest Deploy run |
| Keep-alive passes but says nothing was pinged | `API_URL` isn't set | `gh variable get API_URL` (step 5) |

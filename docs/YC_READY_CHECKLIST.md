# YC Readiness Checklist (Insurance Evidence Wedge)

## 1) Wedge clarity (30–60 days)
- Define a single ICP: claims adjusters + SIU teams at insurers/TPAs.
- Nail the promise: tamper-evident evidence capture that reduces review time.
- Lock a measurable KPI: claim review time, fraud investigation hours, or dispute rate.

## 2) Product outcomes that unlock pilots
- Evidence capture flow with metadata, hashes, and chain-of-custody log.
- One-click provenance export (PDF + raw evidence + hashes).
- Audit trail view for adjusters and managers.
- Admin tools for onboarding, approvals, and access controls.

## 3) Pilot and traction targets
- 2–3 paid pilots or LOIs.
- 5–10 claims processed with before/after time metrics.
- 2–3 reference quotes from real users.

## 4) Distribution and go-to-market
- Start with adjuster networks and TPAs.
- Add integrations with claims platforms as a second channel.
- Pricing experiments: per-claim or per-adjuster monthly.

## 5) YC application readiness
- Clear one-sentence pitch.
- 60–90 second demo video (capture → provenance → export).
- Metrics dashboard showing KPI improvements.

## 6) Risk mitigation checklist
- Production configuration set (`TRUTHSIG_ENV=production`, `JWT_SECRET`, `TRUTHSIG_ADMIN_API_KEY`).
- CORS and trusted hosts configured to match deployed domains.
- Evidence storage and retention policy defined.
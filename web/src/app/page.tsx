"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ShieldCheck,
  Sparkles,
  FileSearch,
  Lock,
  BadgeCheck,
  ArrowRight,
  Shield,
  Gauge,
  CheckCircle2,
  Fingerprint,
  Globe,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { apiFetch } from "@/lib/api";
import { getToken } from "@/lib/auth";

type AnalysisResult = {
  filename: string;
  media_type: string;
  sha256: string;
  bytes: number;
  provenance_state: string;
  summary: string;
  ai_disclosure?: any;
  transformations?: any;
  findings?: Array<{ title: string; severity: string; detail?: string }>;
  c2pa?: any;
  metadata?: any;
  ffprobe?: any;
};

function prettyBytes(n: number) {
  if (!n && n !== 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let x = n;
  let i = 0;
  while (x >= 1024 && i < units.length - 1) {
    x = x / 1024;
    i++;
  }
  return `${x.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function HomePage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const stateBadge = useMemo(() => {
    const s = result?.provenance_state || "";
    if (s === "VERIFIED_ORIGINAL") return { label: "Verified (C2PA)", cls: "border-emerald-200 bg-emerald-50 text-emerald-800" };
    if (s === "ALTERED_OR_BROKEN_PROVENANCE") return { label: "Altered / Broken provenance", cls: "border-amber-200 bg-amber-50 text-amber-900" };
    if (s === "UNVERIFIABLE_NO_PROVENANCE") return { label: "No provenance (unverifiable)", cls: "border-slate-200 bg-slate-100 text-slate-800" };
    return { label: s || "—", cls: "border-slate-200 bg-slate-100 text-slate-800" };
  }, [result?.provenance_state]);


  async function quickScan() {
    if (!file) return;
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiFetch("/analyze", { method: "POST", body: fd });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(t || "Analyze failed");
      }
      const raw = await res.json();

      // Map backend response -> UI contract (AnalysisResult)
      const data: AnalysisResult = {
        filename: raw.filename ?? file.name,
        media_type: raw.media_type ?? raw.mime_type ?? "",
        sha256: raw.sha256 ?? "",
        bytes: raw.bytes ?? raw.size ?? file.size,

        // support nested provenance shape too
        provenance_state: raw.provenance_state ?? raw.provenance?.state ?? "",
        summary: raw.summary ?? raw.provenance?.summary ?? raw.one_line_rationale ?? "",

        // optional sections: accept either flat or nested keys
        ai_disclosure: raw.ai_disclosure ?? raw.provenance?.ai_disclosure ?? raw.ai ?? undefined,
        transformations: raw.transformations ?? raw.provenance?.transformations ?? undefined,
        findings: raw.findings ?? raw.provenance?.findings ?? raw.flags ?? undefined,
        c2pa: raw.c2pa ?? raw.c2pa_summary ?? raw.provenance?.c2pa ?? raw.provenance?.c2pa_summary ?? undefined,
        metadata: raw.metadata ?? raw.provenance?.metadata ?? undefined,
        ffprobe: raw.ffprobe ?? raw.media?.ffprobe ?? raw.provenance?.ffprobe ?? undefined,
      };

      setResult(data);
    } catch (e: any) {
      setErr(e?.message || "Failed");
    } finally {
      setBusy(false);
    }
  }

  function goLogin() {
    router.push("/login");
  }

  return (
    <div className="min-h-screen bg-white text-slate-900">
      {/* Decorative background */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-40 left-1/2 h-[520px] w-[520px] -translate-x-1/2 rounded-full bg-blue-200/60 blur-3xl animate-pulse" />
        <div className="absolute top-40 -left-40 h-[520px] w-[520px] rounded-full bg-sky-200/50 blur-3xl animate-pulse [animation-delay:250ms]" />
        <div className="absolute bottom-0 right-0 h-[520px] w-[520px] rounded-full bg-blue-100/70 blur-3xl animate-pulse [animation-delay:600ms]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.14),_transparent_60%)]" />
        <div className="absolute inset-0 bg-gradient-to-b from-white via-white to-blue-50" />
      </div>

      <header className="sticky top-0 z-20 border-b border-white/60 bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <Link href="/" className="flex items-center gap-2">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold text-slate-900">TruthSig</div>
              <div className="text-[11px] text-slate-500">Provenance • Evidence • Trust</div>
            </div>
          </Link>

          <div className="flex items-center gap-2">
            <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs text-slate-600 md:flex">
              <Shield className="h-3.5 w-3.5 text-blue-600" />
              Trusted by newsrooms + fact-checkers
            </div>
            <Button asChild variant="ghost" className="hidden md:inline-flex text-slate-700">
              <Link href="/register">Request access</Link>
            </Button>
            <Button asChild variant="outline" className="hidden md:inline-flex">
              <Link href="/login">Log in</Link>
            </Button>
            <Button asChild className="bg-blue-600 hover:bg-blue-700">
              <Link href="/app">
                Open workspace <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-10">
        <section className="grid gap-10 lg:grid-cols-2 lg:items-center">
          <div className="space-y-6">
            <Badge className="gap-2 rounded-full border border-blue-200/60 bg-blue-50/70 px-4 py-1 text-blue-700">
              <Sparkles className="h-4 w-4" />
              Evidence-grade provenance for the newsroom era
            </Badge>

            <h1 className="text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">
              Trust every frame with{" "}
              <span className="bg-gradient-to-r from-blue-700 to-sky-600 bg-clip-text text-transparent">cryptographic proof</span>.
            </h1>
            <p className="max-w-xl text-base text-slate-600">
              TruthSig turns media into newsroom-ready evidence. Capture provenance signals, detect edits, and generate a
              publish-ready report in minutes. Built for journalists, fact-checkers, and investigations teams that can’t afford
              uncertainty.
            </p>

            <div className="flex flex-wrap gap-3">
              <Button
                onClick={() => document.getElementById("quick-scan")?.scrollIntoView({ behavior: "smooth" })}
                className="bg-blue-600 hover:bg-blue-700"
              >
                Try Quick Scan
              </Button>
              <Button variant="outline" onClick={goLogin}>
                Generate PDF (login)
              </Button>
              <Button variant="ghost" asChild className="text-slate-700">
                <Link href="/register">
                  Request access <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {[
                { icon: BadgeCheck, label: "C2PA verified", copy: "Cryptographically-backed manifests and chain." },
                { icon: Fingerprint, label: "Tamper signals", copy: "Editing traces, metadata anomalies, timeline gaps." },
                { icon: Lock, label: "Case-ready", copy: "Chain-of-custody events and signed reports." },
              ].map((item) => (
                <div key={item.label} className="rounded-2xl border border-slate-200 bg-white/70 p-4">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-900">
                    <item.icon className="h-4 w-4 text-blue-600" /> {item.label}
                  </div>
                  <p className="mt-1 text-xs text-slate-600">{item.copy}</p>
                </div>
                ))}
            </div>

            <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white/70 p-5 sm:grid-cols-3">
              {[
                { label: "Scans run", value: "1,200+" },
                { label: "Evidence PDFs", value: "320+" },
                { label: "Avg. verification time", value: "↓ 42%" },
              ].map((stat) => (
                <div key={stat.label}>
                  <div className="text-sm text-slate-500">{stat.label}</div>
                  <div className="text-xl font-semibold text-slate-900">{stat.value}</div>
                </div>
                ))}
            </div>
          </div>

          <div className="relative">
            <div className="absolute inset-0 -z-10 rounded-3xl bg-gradient-to-br from-blue-600/15 to-sky-500/10 blur-xl" />
            <Card className="rounded-3xl">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>Quick Scan</span>
                  <span className="text-xs font-normal text-slate-500">Public • No login</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4" id="quick-scan">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="space-y-1">
                      <div className="text-sm font-medium text-slate-900">Upload an image or video</div>
                      <div className="text-xs text-slate-600">
                        We extract provenance signals. If a file is created/edited by tools that disclose it, we will show it.
                      </div>
                    </div>
                    <Button disabled={!file || busy} onClick={quickScan} className="bg-blue-600 hover:bg-blue-700">
                      {busy ? "Scanning…" : "Scan"}
                    </Button>
                  </div>

                  <div className="mt-4">
                    <input
                      type="file"
                      className="block w-full text-sm text-slate-700 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                    />
                    {file ? <div className="mt-2 text-xs text-slate-500">Selected: {file.name}</div> : null}
                  </div>

                  {err ? (
                    <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{err}</div>
                  ) : null}
                </div>

                {result ? (
                  <div className="space-y-3">
                    <div className={`rounded-xl border p-4 ${stateBadge.cls}`}>
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold">{stateBadge.label}</div>
                        <div className="text-xs opacity-80">{prettyBytes(result.bytes)}</div>
                      </div>
                      <div className="mt-2 text-sm">{result.summary}</div>
                    </div>

                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <div className="text-xs text-slate-500">SHA-256</div>
                        <div className="mt-1 break-all text-xs font-mono text-slate-800">{result.sha256}</div>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <div className="text-xs text-slate-500">Media</div>
                        <div className="mt-1 text-sm font-medium text-slate-900">{result.media_type}</div>
                        <div className="mt-1 text-xs text-slate-500">{result.filename}</div>
                      </div>
                    </div>

                    <Separator />

                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4">
                      <div>
                        <div className="text-sm font-medium text-slate-900">Need detailed PDF report?</div>
                        <div className="text-xs text-slate-600">Log in to generate a signed report and store it in a case.</div>
                      </div>
                      <div className="flex gap-2">
                        <Button variant="outline" asChild>
                          <Link href="/register">Request access</Link>
                        </Button>
                        <Button asChild className="bg-blue-600 hover:bg-blue-700">
                          <Link href="/login">Log in</Link>
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border border-slate-200 bg-white/70 p-4 text-sm text-slate-600">
                    Upload a file to see provenance signals here.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </section>

        <section className="mt-16 grid gap-6 md:grid-cols-3">
          {[
            {
              icon: Gauge,
              title: "Newsroom workspace",
              desc: "Create cases, attach media, track chain-of-custody events, and keep investigations organized.",
            },
            {
              icon: FileSearch,
              title: "Provenance-first",
              desc: "C2PA manifests are treated as cryptographic evidence — not probability.",
            },
            {
              icon: Globe,
              title: "API-ready",
              desc: "Designed to become an API: seal provenance at capture-time inside other apps and CMS tools.",
            },
          ].map((x) => (
            <div key={x.title} className="rounded-2xl border border-slate-200 bg-white/70 p-6">
              <div className="flex items-center gap-2 text-base font-semibold text-slate-900">
                <x.icon className="h-4 w-4 text-blue-600" />
                {x.title}
              </div>
              <p className="mt-2 text-sm text-slate-600">{x.desc}</p>
            </div>
          ))}
        </section>

        <section className="mt-14 grid gap-6 rounded-3xl border border-slate-200 bg-white/80 p-8 lg:grid-cols-[1.2fr_1fr]">
          <div className="space-y-4">
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">Chain-of-custody</div>
            <h2 className="text-2xl font-semibold text-slate-900">Every artifact, every action, logged.</h2>
            <p className="text-sm text-slate-600">
              Generate defensible evidence packets with a verifiable trail of who uploaded, who reviewed, and what changed. Built
              for newsrooms, investigations, and fact-checking teams.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                "Immutable hash chain for uploads",
                "Timestamped reviewer approvals",
                "Secure provenance PDF export",
                "Audit-ready evidence timeline",
              ].map((item) => (
                <div key={item} className="flex items-center gap-2 text-sm text-slate-700">
                  <CheckCircle2 className="h-4 w-4 text-blue-600" />
                  {item}
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-900 to-slate-800 p-6 text-white shadow-lg">
            <div className="text-xs uppercase tracking-[0.2em] text-blue-200">Evidence packet</div>
            <div className="mt-3 space-y-4">
              {[
                { label: "Story ID", value: "TS-1084" },
                { label: "Uploaded by", value: "Avery M., Reporter" },
                { label: "Integrity score", value: "Verified" },
                { label: "Timeline", value: "4 events • 18 mins" },
              ].map((row) => (
                <div key={row.label} className="flex items-center justify-between text-sm">
                  <span className="text-blue-100/80">{row.label}</span>
                  <span className="font-medium text-white">{row.value}</span>
                </div>
              ))}
              <div className="rounded-xl border border-white/10 bg-white/10 p-3 text-xs text-blue-100">
                Generated report includes hashes, manifest summary, and chain-of-custody attestation.
              </div>
            </div>
          </div>
        </section>

        <section className="mt-16 grid gap-6 lg:grid-cols-2">
          <div className="rounded-3xl border border-slate-200 bg-white/70 p-8">
            <div className="flex items-center gap-2 text-sm font-semibold text-blue-600">
              <Users className="h-4 w-4" />
              Teams who trust TruthSig
            </div>
            <div className="mt-4 space-y-4">
              {[
                {
                  quote:
                    "We cut verification time in half by attaching evidence packets to every high-risk submission.",
                  name: "Investigations Editor, National Newsroom",
                },
                {
                  quote:
                    "TruthSig gave our fact-checkers a reliable chain-of-custody in minutes instead of days.",
                  name: "Fact-Checking Lead, Regional Desk",
                },
              ].map((item) => (
                <div key={item.name} className="rounded-2xl border border-slate-200 bg-white p-5">
                  <p className="text-sm text-slate-700">“{item.quote}”</p>
                  <div className="mt-3 text-xs font-semibold text-slate-500">{item.name}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white/70 p-8">
            <div className="text-sm font-semibold text-blue-600">How it works</div>
            <ol className="mt-4 space-y-4 text-sm text-slate-700">
              {[
                {
                  title: "Capture evidence",
                  copy: "Upload media from the field with metadata and device attestation.",
                },
                {
                  title: "Verify provenance",
                  copy: "Analyze C2PA manifests, metadata, and editing signals in seconds.",
                },
                {
                  title: "Generate reports",
                  copy: "Create signed evidence packets with chain-of-custody and integrity hashes.",
                },
              ].map((step, index) => (
                <li key={step.title} className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
                    {index + 1}
                  </div>
                  <div>
                    <div className="font-medium text-slate-900">{step.title}</div>
                    <div className="text-xs text-slate-600">{step.copy}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <footer className="mt-16 border-t border-slate-200 py-10 text-sm text-slate-600">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>© {new Date().getFullYear()} TruthSig</div>
            <div className="flex gap-4">
              <Link href="/login" className="hover:text-slate-900">
                Log in
              </Link>
              <Link href="/register" className="hover:text-slate-900">
                Request access
              </Link>
              <Link href="/app" className="hover:text-slate-900">
                Workpsace
              </Link>
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
}

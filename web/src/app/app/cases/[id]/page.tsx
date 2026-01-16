"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

import { apiFetch, apiJson } from "@/lib/api";

type Case = {
  id: string;
  title: string;
  description?: string | null;
  status?: string | null;
  created_at?: string | null;
};

type Evidence = {
  id: string;
  case_id: string;
  filename: string;
  sha256: string;
  created_at?: string | null;
  summary?: string | null;
  provenance_state?: string | null;
};

type Event = {
  id: string;
  case_id: string;
  event_type: string;
  actor?: string | null;
  created_at?: string | null;
};

function asStringParam(v: unknown): string {
  if (typeof v === "string") return v;
  if (Array.isArray(v) && typeof v[0] === "string") return v[0];
  return "";
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function CasePage() {
  const params = useParams<{ id: string }>();
  const caseId = useMemo(() => asStringParam(params?.id), [params]);

  const [caze, setCase] = useState<Case | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [file, setFile] = useState<File | null>(null);

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function refreshAll() {
    if (!caseId) return;
    setErr(null);

    try {
      const [c, ev, logs] = await Promise.all([
        apiJson(`/cases/${caseId}`),
        apiJson(`/cases/${caseId}/evidence`),
        apiJson(`/cases/${caseId}/events`),
      ]);

      setCase(c as Case);
      setEvidence((ev as Evidence[]) || []);
      setEvents((logs as Event[]) || []);
    } catch (e: any) {
      setErr(e?.message || "Failed to load case");
    }
  }

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  async function uploadAndAnalyze() {
    if (!caseId) {
      setErr("Missing case id in URL.");
      return;
    }
    if (!file) {
      setErr("Please select a file first.");
      return;
    }

    setBusy(true);
    setErr(null);

    try {
      const fd = new FormData();
      fd.append("file", file);

      // Backend expects multipart/form-data to /cases/{case_id}/evidence with field name "file"
      const res = await apiFetch(`/cases/${caseId}/evidence`, {
        method: "POST",
        body: fd,
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || "Upload failed");
      }

      setFile(null);
      await refreshAll();
    } catch (e: any) {
      setErr(e?.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function generateReport() {
    if (!caseId) {
      setErr("Missing case id in URL.");
      return;
    }

    setBusy(true);
    setErr(null);

    try {
      // IMPORTANT:
      // POST /report expects JSON: { case_id: "..." }
      // It may return:
      //   - application/pdf (if you implement PDF in backend), OR
      //   - application/json with { markdown: "..." } (current backend behavior)
      const res = await apiFetch(`/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: caseId }),
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || "Report generation failed");
      }

      const ct = (res.headers.get("content-type") || "").toLowerCase();

      // If backend returns a real PDF
      if (ct.includes("application/pdf")) {
        const blob = await res.blob();
        downloadBlob(blob, `truthsig-report-${caseId}.pdf`);
        return;
      }

      // If backend returns JSON markdown (current backend/main.py)
      if (ct.includes("application/json")) {
        const data = await res.json().catch(() => null);
        const md = data?.markdown;

        if (typeof md === "string" && md.trim().length > 0) {
          const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
          downloadBlob(blob, `truthsig-report-${caseId}.md`);
          // Optional: show message
          setErr("Backend returned MARKDOWN (not PDF). Downloaded as .md. If you want PDF, backend must return application/pdf.");
          return;
        }

        // JSON but not expected shape
        const raw = JSON.stringify(data ?? {}, null, 2);
        const blob = new Blob([raw], { type: "application/json;charset=utf-8" });
        downloadBlob(blob, `truthsig-report-${caseId}.json`);
        setErr("Backend returned JSON (not PDF). Downloaded as .json.");
        return;
      }

      // Fallback: download whatever it is (text/html, etc.)
      const raw = await res.text();
      const blob = new Blob([raw], { type: ct || "text/plain;charset=utf-8" });
      downloadBlob(blob, `truthsig-report-${caseId}.txt`);
      setErr(`Backend did not return a PDF. Downloaded as .txt (content-type: ${ct || "unknown"}).`);
    } catch (e: any) {
      setErr(e?.message || "Report failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-blue-50">
      <header className="border-b border-slate-200 bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <Link href="/app" className="text-sm font-semibold text-slate-900">
            TruthSig
          </Link>
          <Button variant="outline" asChild>
            <Link href="/app">Back to cases</Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-10">
        {err ? (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {err}
          </div>
        ) : null}

        <div className="grid gap-6 md:grid-cols-3">
          <div className="space-y-6 md:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle>{caze ? caze.title : "Loading…"}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">Case</Badge>
                  {caze?.status ? <Badge>{caze.status}</Badge> : null}
                  {caze?.created_at ? (
                    <span className="text-xs text-slate-500">
                      Created {new Date(caze.created_at).toLocaleString()}
                    </span>
                  ) : null}
                </div>
                {caze?.description ? (
                  <p className="mt-3 text-sm text-slate-700">{caze.description}</p>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Evidence</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-3">
                  {evidence.length === 0 ? (
                    <div className="text-sm text-slate-600">
                      No evidence yet. Upload a file to begin.
                    </div>
                  ) : (
                    evidence.map((e) => (
                      <div key={e.id} className="rounded-lg border border-slate-200 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-slate-900">
                              {e.filename}
                            </div>
                            <div className="mt-1 break-all text-xs text-slate-600">
                              SHA-256: {e.sha256}
                            </div>
                            {e.summary ? (
                              <div className="mt-2 text-sm text-slate-700">
                                {e.summary}
                              </div>
                            ) : null}
                          </div>
                          <div className="flex flex-col items-end gap-2">
                            {e.provenance_state ? <Badge>{e.provenance_state}</Badge> : null}
                            {e.created_at ? (
                              <div className="text-xs text-slate-500">
                                {new Date(e.created_at).toLocaleString()}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Upload</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1">
                  <label className="text-sm text-slate-700">Select file (image or video)</label>
                  <Input
                    type="file"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                </div>

                <div className="grid gap-2">
                  <Button
                    disabled={!file || busy}
                    onClick={uploadAndAnalyze}
                    className="bg-blue-600 hover:bg-blue-700"
                  >
                    {busy ? "Working…" : "Add to case + Analyze"}
                  </Button>

                  <Button disabled={busy} onClick={generateReport} variant="outline">
                    Generate Report
                  </Button>
                </div>

                <p className="text-xs text-slate-500">
                  Note: Your current backend returns MARKDOWN for <code>/report</code>. If you
                  want a real PDF, backend must return <code>application/pdf</code>.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Chain of custody</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {events.length === 0 ? (
                    <div className="text-sm text-slate-600">No events yet.</div>
                  ) : (
                    events.map((ev) => (
                      <div
                        key={ev.id}
                        className="flex items-start justify-between gap-2 rounded-md border border-slate-200 p-2"
                      >
                        <div>
                          <div className="text-sm font-medium text-slate-900">
                            {ev.event_type}
                          </div>
                          <div className="text-xs text-slate-600">
                            {ev.actor || "user"}
                          </div>
                        </div>
                        <div className="text-xs text-slate-500">
                          {ev.created_at ? new Date(ev.created_at).toLocaleString() : ""}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}

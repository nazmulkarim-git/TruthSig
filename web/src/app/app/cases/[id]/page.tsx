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
  analysis_json?: any;
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
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);

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

  useEffect(() => {
    if (!evidence.length) return;
    if (!selectedEvidenceId || !evidence.find((item) => item.id === selectedEvidenceId)) {
      setSelectedEvidenceId(evidence[0].id);
    }
  }, [evidence, selectedEvidenceId]);


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

  async function generateEvidenceReport() {
  if (!caseId || !selectedEvidenceId) {
    setErr("Select evidence before creating a report.");
    return;
  }

  setBusy(true);
  setErr(null);

  try {
    const res = await apiFetch(
      `/cases/${caseId}/evidence/${selectedEvidenceId}/report`,
      { method: "POST" }
    );

    if (!res.ok) {
      const t = await res.text();
      throw new Error(t || "Report generation failed");
    }

    const blob = await res.blob();
    downloadBlob(blob, `truthsig-evidence-${selectedEvidenceId}.pdf`);
  } catch (e: any) {
    setErr(e?.message || "Report failed");
  } finally {
    setBusy(false);
  }
}

  const selectedEvidence = useMemo(
    () => evidence.find((e) => e.id === selectedEvidenceId) || evidence[0] || null,
    [evidence, selectedEvidenceId],
  );
  const analysis = selectedEvidence?.analysis_json;


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
                      <div
                        key={e.id}
                        className={`rounded-lg border p-3 ${
                          selectedEvidence?.id === e.id
                            ? "border-blue-400 bg-blue-50/40"
                            : "border-slate-200"
                        }`}
                        onClick={() => setSelectedEvidenceId(e.id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(ev) => {
                          if (ev.key === "Enter") setSelectedEvidenceId(e.id);
                        }}
                      >
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
                <CardTitle>Quick Scan</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                  <div className="text-xs uppercase text-slate-500">Latest scan</div>
                  {analysis ? (
                    <div className="mt-2 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="text-sm font-semibold text-slate-900">
                          Trust score
                        </div>
                        <Badge>{analysis.trust_score ?? "—"}</Badge>
                      </div>
                      <div className="text-xs text-slate-600">
                        {analysis.one_line_rationale || "No rationale available yet."}
                      </div>
                      {analysis.top_reasons?.length ? (
                        <ul className="list-disc space-y-1 pl-4 text-xs text-slate-600">
                          {analysis.top_reasons.slice(0, 3).map((reason: string) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : (
                    <div className="mt-2 text-xs text-slate-500">
                      Upload evidence to generate a quick scan.
                    </div>
                  )}
                </div>
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
                    {busy ? "Working…" : "Quick Scan + Add to case"}
                  </Button>
                  <Button disabled={busy || !selectedEvidence} onClick={generateEvidenceReport} variant="outline">
                    Create Evidence PDF
                  </Button>
                </div>
                {analysis?.forensics?.type === "image" ? (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-slate-700">ELA heatmap</div>
                    <img
                      src={`/cases/${caseId}/evidence/${selectedEvidence?.id}/artifact?kind=heatmap`}
                      alt="ELA heatmap"
                      className="w-full rounded-md border border-slate-200"
                    />
                  </div>
                ) : null}

                {analysis?.forensics?.type === "video" && analysis?.forensics?.results?.flagged_frames?.length ? (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-slate-700">Flagged frames</div>
                    <div className="grid grid-cols-3 gap-2">
                      {analysis.forensics.results.flagged_frames.slice(0, 3).map((frame: any) => (
                        <img
                          key={frame.index}
                          src={`/cases/${caseId}/evidence/${selectedEvidence?.id}/artifact?kind=frame&index=${frame.index}`}
                          alt={`Frame ${frame.index}`}
                          className="rounded-md border border-slate-200"
                        />
                      ))}
                    </div>
                  </div>
                ) : null}
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

                        
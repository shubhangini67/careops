// lib/exportRun.ts
// P6-A30 -- extracted from two near-identical copies (app/dashboard/page.tsx's
// old success view and components/data/RunHistorySection.tsx) into one shared
// helper, while relocating the "just-completed-run" export UI to /planning.

import { getAuthToken } from "@/lib/auth-cookies";
import { getApiBaseUrl } from "@/lib/apiBase";

export async function downloadRunFile(url: string, filename: string): Promise<void> {
  const token = getAuthToken();
  const base  = getApiBaseUrl();
  const res   = await fetch(`${base}${url}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = href;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(href);
}

export async function downloadRunPdf(runId: number, scenario: string): Promise<void> {
  await downloadRunFile(
    `/api/v1/runs/${runId}/export`,
    `careops-${scenario.replace(/_/g, "-")}-${runId}.pdf`,
  );
}

export async function downloadRunExcel(runId: number, scenario: string): Promise<void> {
  await downloadRunFile(
    `/api/v1/runs/${runId}/export/excel`,
    `careops-${scenario.replace(/_/g, "-")}-${runId}.xlsx`,
  );
}

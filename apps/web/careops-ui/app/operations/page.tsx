"use client";

// P6-A26 — /operations was merged into /dashboard's success view, then
// P6-A30 split that success view out again into /planning (agent cards,
// forecast chart, critic banner render there now; /dashboard is overview-
// only). This route stays only to redirect old bookmarks/links (including
// ?run=<id> deep links) rather than 404ing.

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function OperationsRedirect() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const run = searchParams.get("run");
    router.replace(run ? `/planning?run=${run}` : "/dashboard");
  }, [router, searchParams]);

  return null;
}

export default function OperationsPage() {
  return (
    <Suspense fallback={null}>
      <OperationsRedirect />
    </Suspense>
  );
}

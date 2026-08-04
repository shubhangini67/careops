"use client";

// P6-A28 -- /runs was merged into /data (Run History section lives there
// now). This route stays only to redirect old bookmarks/links rather than
// showing stale content or 404ing.

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function RunsRedirect() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const run = searchParams.get("run");
    router.replace(run ? `/data?run=${run}` : "/data");
  }, [router, searchParams]);

  return null;
}

export default function RunsPage() {
  return (
    <Suspense fallback={null}>
      <RunsRedirect />
    </Suspense>
  );
}

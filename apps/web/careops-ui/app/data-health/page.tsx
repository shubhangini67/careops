"use client";

// P6-A28 -- /data-health was merged into /data (Data Health section lives
// there now). This route stays only to redirect old bookmarks/links rather
// than showing stale content or 404ing.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DataHealthPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/data");
  }, [router]);

  return null;
}

"use client";

// P6-A28 -- fixes the long-standing /runs/{id} 404: this dynamic route never
// existed before (run selection was pure React state, never a URL segment),
// so visiting /runs/<id> directly always 404'd on Next's default (unstyled)
// not-found page. Now it redirects to the merged /data page's ?run=<id>
// deep-link (same convention /dashboard uses).

import { Suspense, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

function RunRedirect() {
  const router = useRouter();
  const params = useParams();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;

  useEffect(() => {
    router.replace(id ? `/data?run=${id}` : "/data");
  }, [router, id]);

  return null;
}

export default function RunDetailPage() {
  return (
    <Suspense fallback={null}>
      <RunRedirect />
    </Suspense>
  );
}

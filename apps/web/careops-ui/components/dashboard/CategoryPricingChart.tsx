"use client";

import type { ReactNode } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, LabelList } from "recharts";
import { MarketCategoryPricing } from "@/lib/api";

export default function CategoryPricingChart({ data }: { data: MarketCategoryPricing[] }) {
  if (data.length === 0) return null;

  const chartData = data.map((c) => ({
    category: c.category.charAt(0).toUpperCase() + c.category.slice(1),
    "Your avg": c.your_avg,
    "Area avg": c.area_avg,
    diffPct: c.diff_pct,
  }));

  const height = Math.max(160, chartData.length * 52);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[9px] uppercase tracking-widest text-[var(--color-text-ghost)]">
          Category pricing — you vs area
        </p>
        <div className="flex items-center gap-3 text-[10px] text-[var(--color-text-faint)]">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: "#e8c48f" }} /> Area avg</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: "#efa345" }} /> Your avg</span>
        </div>
      </div>
      <BarChart
        width={480}
        height={height}
        data={chartData}
        layout="vertical"
        margin={{ top: 4, right: 40, left: 8, bottom: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 9, fill: "#7C93B3" }} axisLine={false} tickLine={false} />
        <YAxis
          type="category"
          dataKey="category"
          tick={{ fontSize: 11, fill: "#7C93B3" }}
          axisLine={false}
          tickLine={false}
          width={72}
        />
        <Tooltip
          contentStyle={{ background: "#0b1020", border: "1px solid rgba(230,137,42,0.2)", borderRadius: 10, fontSize: 12, color: "#f8fafc" }}
          formatter={(value: unknown) => [`₹${value}`, ""]}
        />
        <Bar dataKey="Area avg" fill="#e8c48f" radius={[0, 3, 3, 0]} barSize={12}>
          <LabelList dataKey="Area avg" position="right" style={{ fontSize: 10, fill: "#a8926f" }} formatter={(v?: ReactNode) => (v != null ? `₹${v}` : "")} />
        </Bar>
        <Bar dataKey="Your avg" fill="#efa345" radius={[0, 3, 3, 0]} barSize={12}>
          <LabelList dataKey="Your avg" position="right" style={{ fontSize: 10, fill: "#efa345" }} formatter={(v?: ReactNode) => (v != null ? `₹${v}` : "")} />
        </Bar>
      </BarChart>
    </div>
  );
}

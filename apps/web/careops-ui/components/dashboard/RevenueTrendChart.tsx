"use client";

import { Line, LineChart, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { BusinessDailyPoint } from "@/lib/api";

export default function RevenueTrendChart({ data }: { data: BusinessDailyPoint[] }) {
  if (data.length === 0) return null;

  const chartData = data.map((d) => ({
    ...d,
    label: new Date(d.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
  }));

  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-soft)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#6b7280" }} axisLine={false} tickLine={false} />
          <YAxis width={48} tick={{ fontSize: 9, fill: "#6b7280" }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{ background: "var(--color-surface-raised)", border: "1px solid var(--color-border-default)", borderRadius: 8, fontSize: 12 }}
            formatter={(value: unknown, name: unknown) => [`₹${Number(value).toLocaleString("en-IN")}`, String(name)]}
          />
          <Legend verticalAlign="top" align="right" height={28} wrapperStyle={{ fontSize: 11 }} />
          <Line type="monotone" dataKey="profit" name="Cost efficiency" stroke="#efa345" strokeWidth={2.5} dot={false} />
          <Line type="monotone" dataKey="revenue" name="Admissions revenue" stroke="#818cf8" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

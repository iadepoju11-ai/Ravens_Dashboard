import type { ReactNode } from "react";

interface Props {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "good" | "bad" | "warning";
}

export function KpiCard({ label, value, hint, tone = "default" }: Props) {
  return (
    <div className={`kpi-card kpi-card--${tone}`}>
      <div className="kpi-card__label">{label}</div>
      <div className="kpi-card__value">{value}</div>
      {hint ? <div className="kpi-card__hint">{hint}</div> : null}
    </div>
  );
}

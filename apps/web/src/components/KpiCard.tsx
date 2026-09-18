import type { ReactNode } from "react";

interface Props {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "good" | "bad" | "warning";
  icon?: ReactNode;
  accent?: "blue" | "green" | "purple" | "amber" | "teal";
}

export function KpiCard({ label, value, hint, tone = "default", icon, accent = "blue" }: Props) {
  return (
    <div className={`kpi-card kpi-card--${tone} kpi-card--accent-${accent}`}>
      {icon ? <div className="kpi-card__icon">{icon}</div> : null}
      <div className="kpi-card__label">{label}</div>
      <div className="kpi-card__value">{value}</div>
      {hint ? <div className="kpi-card__hint">{hint}</div> : null}
    </div>
  );
}

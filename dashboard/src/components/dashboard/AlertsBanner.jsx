import React from 'react';
import { AlertTriangle, AlertCircle, Info } from 'lucide-react';

const SEVERITY_STYLE = {
  critical: { bg: 'var(--color-danger-muted)', fg: 'var(--color-danger)', Icon: AlertTriangle },
  warning: { bg: 'var(--color-warning-muted)', fg: 'var(--color-warning)', Icon: AlertCircle },
  info: { bg: 'var(--color-accent-muted)', fg: 'var(--color-accent)', Icon: Info },
};

export default function AlertsBanner({ alerts }) {
  if (!alerts || alerts.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      {alerts.map((alert, i) => {
        const style = SEVERITY_STYLE[alert.severity] ?? SEVERITY_STYLE.info;
        const Icon = style.Icon;
        return (
          <div
            key={i}
            className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-sm"
            style={{ background: style.bg, color: style.fg }}
          >
            <Icon className="w-4 h-4 shrink-0" />
            <span>{alert.message}</span>
          </div>
        );
      })}
    </div>
  );
}

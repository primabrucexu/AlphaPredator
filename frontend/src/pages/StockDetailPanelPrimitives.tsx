import {type ReactNode} from 'react';

const GRID_LEFT = '70px';

export function InfoRow({ items }: { items: { label: string; value: string; color?: string }[] }) {
  return (
    <div style={{fontSize: 13, lineHeight: 1.85}}>
      {items.map(({ label, value, color }) => (
        <span key={label} style={{marginRight: 16}}>
          <span style={{ color: '#888' }}>{label}: </span>
          <span style={{ color: color ?? '#333', fontWeight: 500 }}>{value}</span>
        </span>
      ))}
    </div>
  );
}

export function PanelFloatCard({
  top,
  title,
  children,
}: {
  top: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        position: 'absolute',
        top: `calc(${top} + 4px)`,
        left: GRID_LEFT,
        zIndex: 16,
        pointerEvents: 'none',
        background: 'rgba(255,255,255,0.86)',
        border: '1px solid rgba(0,0,0,0.18)',
        borderRadius: 8,
        padding: '8px 12px',
        backdropFilter: 'blur(3px)',
      }}
    >
      <div style={{color: '#555', fontSize: 13, fontWeight: 700, marginBottom: 4}}>{title}</div>
      {children}
    </div>
  );
}


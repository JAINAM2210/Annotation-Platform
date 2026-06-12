import { Loader2 } from 'lucide-react';

export function LoadingScreen({ label }: { label: string }) {
  return (
    <main className="route-loading">
      <div className="loading-card">
        <Loader2 aria-hidden="true" className="spin" size={18} />
        <span>{label}</span>
      </div>
    </main>
  );
}

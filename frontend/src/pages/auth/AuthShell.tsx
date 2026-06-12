import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { FileText, Moon, ShieldCheck, Sun, Users, Workflow } from 'lucide-react';
import type { Message } from '../../lib/status';
import { useTheme } from '../../theme/ThemeContext';
import { Button, MessageBanner } from '../../ui/Primitives';

type Props = {
  eyebrow?: string;
  title: string;
  summary: string;
  children: ReactNode;
  message?: Message | null;
};

export function AuthShell({ eyebrow = 'Low Temperature Plasma', title, summary, children, message }: Props) {
  const { theme, toggleTheme } = useTheme();
  const ThemeIcon = theme === 'light' ? Moon : Sun;

  return (
    <main className="public-shell">
      <div className="public-actions">
        <Button variant="secondary" size="compact" icon={ThemeIcon} onClick={toggleTheme}>
          {theme === 'light' ? 'Dark mode' : 'Light mode'}
        </Button>
      </div>
      <section className="public-brand">
        <Link className="brand-mark" to="/signin">
          <span className="brand-mark__logo">AP</span>
          <span>Annotation Platform</span>
        </Link>
        <div className="public-brand__main">
          <p className="eyebrow">{eyebrow}</p>
          <h1>Relation Annotation Platform</h1>
          <p className="public-brand__copy">A secure workspace for paper annotation, reviewer approval, and export-ready relation data.</p>
          <div className="public-feature-grid" aria-label="Platform capabilities">
            <span><FileText aria-hidden="true" size={16} /> Paper-first annotation</span>
            <span><Workflow aria-hidden="true" size={16} /> Review workflow</span>
            <span><Users aria-hidden="true" size={16} /> Role-based access</span>
            <span><ShieldCheck aria-hidden="true" size={16} /> Firebase identity</span>
          </div>
        </div>
      </section>
      <section className="auth-card" aria-labelledby="auth-card-title">
        <div className="auth-card__header">
          <h2 id="auth-card-title">{title}</h2>
          <p>{summary}</p>
        </div>
        {message?.text ? <MessageBanner type={message.type} text={message.text} /> : null}
        {children}
      </section>
    </main>
  );
}

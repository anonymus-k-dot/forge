import type { RefObject } from "react";

interface SiteHeaderProps {
  readonly shortcutsOpen: boolean;
  readonly onShowShortcuts: () => void;
  readonly showShortcutsButton: boolean;
  readonly triggerRef: RefObject<HTMLButtonElement | null>;
}

export function SiteHeader(props: SiteHeaderProps) {
  const { shortcutsOpen, onShowShortcuts, showShortcutsButton, triggerRef } = props;
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <span className="brand">FORGE</span>
        <span className="divider" aria-hidden="true" />
        <span className="brand-sub">Prompt engine</span>
        {showShortcutsButton && (
          <>
            <span className="divider" aria-hidden="true" />
            <button
              type="button"
              ref={triggerRef}
              className="shortcuts-trigger"
              aria-haspopup="dialog"
              aria-controls="shortcuts-dialog"
              aria-expanded={shortcutsOpen}
              onClick={onShowShortcuts}
            >
              <kbd className="key" aria-hidden="true">
                ?
              </kbd>
              <span>Shortcuts</span>
            </button>
          </>
        )}
      </div>
    </header>
  );
}

export function Hero() {
  return (
    <div className="hero">
      <p className="eyebrow">Architectural prompting</p>
      <h1 className="hero-title">
        Elevate your <em>Vision</em>
      </h1>
      <p className="hero-text">
        A precision-engineered workspace that refines and structures raw prompts into
        high-performance AI directions.
      </p>
    </div>
  );
}

export function SiteFooter() {
  return (
    <>
      <p className="wordmark" aria-hidden="true">
        FORGE
      </p>
      <footer className="site-footer">
        <div>
          <p className="brand">FORGE</p>
          <p className="footer-meta">© {new Date().getFullYear()} FORGE</p>
        </div>
        <a className="footer-link" href="/">
          Classic interface
        </a>
      </footer>
    </>
  );
}

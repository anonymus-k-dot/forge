import { Component } from "react";
import type { ReactNode } from "react";

interface ErrorBoundaryState {
  readonly failed: boolean;
}

/** Last line of defence: a rendering bug shows a recoverable message, not a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  override render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="boot" role="alert">
        <p className="boot-brand">FORGE</p>
        <p className="boot-text">
          Something went wrong in the interface. Reload the page to continue, or use the{" "}
          <a href="/">classic interface</a>.
        </p>
      </div>
    );
  }
}

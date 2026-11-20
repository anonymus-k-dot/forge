import { useLayoutEffect, useRef } from "react";
import type { KeyboardEvent, RefObject } from "react";
import { Icon } from "./Icon.tsx";

interface ShortcutsDialogProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly modKey: string;
  /** Receives focus on close when nothing else had focus before the dialog opened. */
  readonly fallbackFocusRef: RefObject<HTMLElement | null>;
}

/**
 * A native <dialog> opened with showModal(): the browser makes the rest of the page inert
 * (keyboard and assistive technology) and turns Escape into "close". Every way of closing
 * (Escape, the close button, a click on the backdrop) ends in the dialog's close event,
 * which returns focus to where it was before the dialog opened.
 */
export function ShortcutsDialog({ open, onClose, modKey, fallbackFocusRef }: ShortcutsDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const pressedBackdrop = useRef(false);

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      const previous = document.activeElement;
      returnFocusRef.current =
        previous instanceof HTMLElement && previous !== document.body ? previous : null;
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", ""); // very old browsers: non-modal fallback
      closeRef.current?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const handleClose = () => {
    const target = returnFocusRef.current?.isConnected
      ? returnFocusRef.current
      : fallbackFocusRef.current;
    returnFocusRef.current = null;
    onClose();
    target?.focus();
  };

  const close = () => dialogRef.current?.close();

  // Tab and Shift+Tab wrap within the dialog. (The page behind is inert either way; this
  // also keeps focus from leaving for the browser's own toolbar.)
  const onKeyDown = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>("button, [href], [tabindex]:not([tabindex='-1'])"),
    ).filter((element) => !element.hasAttribute("disabled"));
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const current = document.activeElement;
    if (event.shiftKey ? current === first : current === last) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
  };

  return (
    <dialog
      ref={dialogRef}
      id="shortcuts-dialog"
      className="shortcuts-dialog"
      aria-labelledby="shortcuts-title"
      onClose={handleClose}
      onKeyDown={onKeyDown}
      onPointerDown={(event) => {
        pressedBackdrop.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        // Only a press and release both on the backdrop (not a text selection that ends there).
        if (event.target === event.currentTarget && pressedBackdrop.current) close();
        pressedBackdrop.current = false;
      }}
    >
      <div className="shortcuts-panel">
        <div className="shortcuts-head">
          <h2 id="shortcuts-title" className="shortcuts-title">
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            ref={closeRef}
            className="icon-btn"
            aria-label="Close keyboard shortcuts"
            onClick={close}
          >
            <Icon name="close" size={20} />
          </button>
        </div>
        <dl className="shortcut-list">
          <div className="shortcut-row">
            <dt>Enhance the prompt (in the editor)</dt>
            <dd>
              <kbd className="key">{modKey}</kbd>
              <kbd className="key">Enter</kbd>
            </dd>
          </div>
          <div className="shortcut-row">
            <dt>Show these shortcuts</dt>
            <dd>
              <kbd className="key">?</kbd>
            </dd>
          </div>
          <div className="shortcut-row">
            <dt>Move to the prompt</dt>
            <dd>
              <kbd className="key">/</kbd>
            </dd>
          </div>
          <div className="shortcut-row">
            <dt>Close a dialog or menu</dt>
            <dd>
              <kbd className="key">Esc</kbd>
            </dd>
          </div>
        </dl>
      </div>
    </dialog>
  );
}

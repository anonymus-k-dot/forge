import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { CopyFormat } from "../utils/copy.ts";
import { Icon } from "./Icon.tsx";
import type { IconName } from "./Icon.tsx";

const ITEMS: readonly { format: CopyFormat; label: string; icon: IconName }[] = [
  { format: "text", label: "Copy text", icon: "text" },
  { format: "json", label: "Copy as JSON", icon: "braces" },
];

interface CopyMenuProps {
  readonly disabled: boolean;
  /** Show "Copied" on the button (briefly, after a successful copy). */
  readonly copied: boolean;
  /** Called synchronously from the click or key press (clipboard access needs one). */
  readonly onCopy: (format: CopyFormat) => void;
}

/**
 * Menu button (WAI-ARIA APG pattern): Enter, Space or ↓ opens on the first item, ↑ on the
 * last; ↑/↓ move (wrapping), Home/End jump, Escape closes and returns focus to the
 * button, Tab closes and moves on, a click outside closes.
 */
export function CopyMenu({ disabled, copied, onCopy }: CopyMenuProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const count = ITEMS.length;
  const isOpen = open && !disabled;

  // The menu is shown with the `hidden` attribute, so an item can take focus at once.
  useLayoutEffect(() => {
    if (isOpen) itemRefs.current[active]?.focus();
  }, [isOpen, active]);

  // Disabled (a request started) closes it for good, so it never reopens by itself later.
  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [isOpen]);

  const openAt = (index: number) => {
    if (disabled) return;
    setActive((index + count) % count);
    setOpen(true);
  };

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  };

  const onButtonKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openAt(event.key === "ArrowDown" ? 0 : count - 1);
    }
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = {
      ArrowDown: active + 1,
      ArrowUp: active - 1,
      Home: 0,
      End: count - 1,
    };
    const next = moves[event.key];
    if (next !== undefined) {
      event.preventDefault();
      setActive((next + count) % count);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  };

  const choose = (format: CopyFormat) => {
    close(true);
    onCopy(format);
  };

  return (
    <div
      className="copy-menu"
      ref={rootRef}
      onBlur={(event) => {
        // Focus moved elsewhere (a shortcut, a click, Tab): the menu closes.
        if (!rootRef.current?.contains(event.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <button
        type="button"
        id="copy-btn"
        ref={buttonRef}
        className="copy-btn"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls="copy-menu-list"
        disabled={disabled}
        onClick={() => (isOpen ? close(false) : openAt(0))}
        onKeyDown={onButtonKeyDown}
      >
        <Icon name={copied ? "check" : "copy"} size={14} />
        <span>{copied ? "Copied" : "Copy"}</span>
        <Icon name="chevronDown" size={14} />
      </button>
      <div
        id="copy-menu-list"
        className="copy-menu-list"
        role="menu"
        aria-labelledby="copy-btn"
        hidden={!isOpen}
        onKeyDown={onMenuKeyDown}
      >
        {ITEMS.map((item, index) => (
          <button
            key={item.format}
            type="button"
            role="menuitem"
            tabIndex={-1}
            className="copy-menu-item"
            ref={(element) => {
              itemRefs.current[index] = element;
            }}
            onFocus={() => setActive(index)}
            onClick={() => choose(item.format)}
          >
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

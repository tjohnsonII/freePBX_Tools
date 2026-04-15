import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';

// ── Public handle exposed via ref ─────────────────────────────────────────

export type TerminalHandle = {
  /** Write raw text (may include ANSI escape sequences) to the terminal. */
  write: (data: string) => void;
  /** Reset/clear the terminal screen and scrollback. */
  clear: () => void;
};

// ── Component ─────────────────────────────────────────────────────────────

type Props = {
  /** Optional extra CSS class on the outermost wrapper div. */
  className?: string;
};

/**
 * TerminalPanel — a real xterm.js terminal emulator.
 *
 * Designed for rendering raw output from freepbx-callflows which:
 *  - Uses 220-char-wide ASCII box-drawing art
 *  - Outputs ANSI color codes (since the SSH shell has a PTY)
 *  - Uses Unicode box-drawing characters (╔═╦═╗ etc.)
 *
 * cols=222 matches the tool's target terminal width.  The wrapper div
 * has overflow-x:auto so users can scroll horizontally on narrow viewports.
 */
const TerminalPanel = forwardRef<TerminalHandle, Props>(function TerminalPanel(
  { className },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);

  // ── Mount / unmount terminal ──────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const term = new Terminal({
      fontFamily:
        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Courier New", monospace',
      fontSize: 12,
      lineHeight: 1.5,
      theme: {
        background: '#0f1929',
        foreground: '#e2e8f0',
        black:   '#1e2030',
        red:     '#f87171',
        green:   '#4ade80',
        yellow:  '#fbbf24',
        blue:    '#60a5fa',
        magenta: '#c084fc',
        cyan:    '#22d3ee',
        white:   '#e2e8f0',
        brightBlack:   '#475569',
        brightRed:     '#fca5a5',
        brightGreen:   '#86efac',
        brightYellow:  '#fde68a',
        brightBlue:    '#93c5fd',
        brightMagenta: '#d8b4fe',
        brightCyan:    '#67e8f9',
        brightWhite:   '#f8fafc',
        cursor: '#4ade80',
        cursorAccent: '#0f1929',
      },
      // 222 cols matches the tool's 220-char layout with 2 chars margin.
      // Lines will NOT wrap at the container edge; the wrapper scrolls horizontally.
      cols: 222,
      rows: 44,
      scrollback: 5000,
      // Automatically convert bare \n to \r\n so lines advance correctly.
      convertEol: true,
      // The panel is output-only; disable cursor blinking and stdin.
      disableStdin: true,
      cursorBlink: false,
    });

    term.open(containerRef.current);
    termRef.current = term;

    return () => {
      term.dispose();
      termRef.current = null;
    };
  }, []);

  // ── Expose write / clear ──────────────────────────────────────────────
  useImperativeHandle(ref, () => ({
    write(data: string) {
      termRef.current?.write(data);
    },
    clear() {
      termRef.current?.reset();
    },
  }));

  return (
    <div className={`diag-terminal-outer${className ? ' ' + className : ''}`}>
      <div ref={containerRef} className="diag-terminal-inner" />
    </div>
  );
});

export default TerminalPanel;

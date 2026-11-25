// Dev-only page at `/?test=drag` (Phase 5, Group 1). It tries three ways to drag
// a card by mouse and by finger and logs the raw events each one receives, so the
// mechanism for stopwatch/timer/task reordering is picked from evidence.
// Touches nothing real: dummy cards only, no backend calls.
import { useCallback, useRef, useState } from "react";
import { GripVertical } from "lucide-react";

type Log = (who: string, what: string) => void;

const range = (n: number, prefix: string) =>
  Array.from({ length: n }, (_, i) => `${prefix}${i + 1}`);

// Moves `from` to the slot where `to` currently is (same splice rule the task list uses).
function moveItem(list: string[], from: string, to: string): string[] {
  const next = [...list];
  const si = next.indexOf(from);
  const ti = next.indexOf(to);
  if (si < 0 || ti < 0 || si === ti) return list;
  const [item] = next.splice(si, 1);
  next.splice(ti, 0, item);
  return next;
}

const CARD: React.CSSProperties = {
  width: 120, height: 64, borderRadius: 10, background: "#0d1628",
  border: "1px solid rgba(61,110,234,0.35)", color: "#d8e4f8",
  display: "flex", alignItems: "center", gap: 6, padding: "0 8px", userSelect: "none",
};
const HANDLE: React.CSSProperties = {
  width: 36, height: 48, display: "flex", alignItems: "center",
  justifyContent: "center", color: "#6f8fe0", background: "rgba(61,110,234,0.12)", borderRadius: 6,
};

// ── Variant A: native HTML5 drag, started from the handle ──
function VariantA({ log }: { log: Log }) {
  const [order, setOrder] = useState(() => range(6, "A"));
  const [over, setOver] = useState<string | null>(null);
  const dragId = useRef<string | null>(null);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {order.map(id => (
        <div
          key={id}
          style={{ ...CARD, outline: over === id ? "2px solid #3d6eea" : "none", opacity: dragId.current === id ? 0.4 : 1 }}
          onDragOver={e => { e.preventDefault(); setOver(id); log("A", "dragover(card)"); }}
          onDrop={() => {
            if (dragId.current) setOrder(o => moveItem(o, dragId.current!, id));
            log("A", `drop on ${id}`); setOver(null);
          }}
        >
          <div
            draggable
            style={{ ...HANDLE, touchAction: "auto" }}
            onPointerDown={e => log("A", `pointerdown(${e.pointerType})`)}
            onPointerCancel={e => log("A", `pointercancel(${e.pointerType}) <- browser took the gesture`)}
            onTouchStart={() => log("A", "touchstart")}
            onTouchMove={() => log("A", "touchmove")}
            onDragStart={e => {
              dragId.current = id;
              const card = (e.currentTarget.parentElement as HTMLElement);
              e.dataTransfer.setDragImage(card, 20, 20);
              e.dataTransfer.effectAllowed = "move";
              log("A", `dragstart ${id}`);
            }}
            onDragEnd={() => { dragId.current = null; setOver(null); log("A", "dragend"); }}
          >
            <GripVertical size={22} />
          </div>
          <b>{id}</b>
        </div>
      ))}
    </div>
  );
}

// ── Variant B: hand-written pointer events, captured on the handle ──
function VariantB({ log }: { log: Log }) {
  const [order, setOrder] = useState(() => range(6, "B"));
  const [drag, setDrag] = useState<{ id: string; x: number; y: number } | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const overRef = useRef<string | null>(null);

  // Card under the pointer, found by position (the handle keeps capture, so e.target is useless).
  const cardAt = (x: number, y: number) =>
    (document.elementFromPoint(x, y)?.closest("[data-bcard]") as HTMLElement | null)?.dataset.bcard ?? null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {order.map(id => (
        <div
          key={id}
          data-bcard={id}
          style={{ ...CARD, outline: over === id && drag?.id !== id ? "2px solid #3d6eea" : "none", opacity: drag?.id === id ? 0.4 : 1 }}
        >
          <div
            style={{ ...HANDLE, touchAction: "none" }}
            onPointerDown={e => {
              e.currentTarget.setPointerCapture(e.pointerId);
              setDrag({ id, x: e.clientX, y: e.clientY });
              log("B", `pointerdown(${e.pointerType}) ${id}`);
            }}
            onPointerMove={e => {
              if (!drag || drag.id !== id) return;
              const t = cardAt(e.clientX, e.clientY);
              overRef.current = t; setOver(t);
              setDrag({ id, x: e.clientX, y: e.clientY });
              log("B", "pointermove");
            }}
            onPointerUp={e => {
              const t = cardAt(e.clientX, e.clientY);
              if (drag && t) setOrder(o => moveItem(o, drag.id, t));
              log("B", `pointerup -> drop on ${t ?? "nothing"}`);
              setDrag(null); setOver(null);
            }}
            onPointerCancel={e => { log("B", `pointercancel(${e.pointerType}) <- browser took the gesture`); setDrag(null); setOver(null); }}
          >
            <GripVertical size={22} />
          </div>
          <b>{id}</b>
        </div>
      ))}
      {drag && (
        <div style={{ ...CARD, position: "fixed", left: drag.x - 20, top: drag.y - 20, width: 90, height: 40, pointerEvents: "none", background: "#3d6eea", zIndex: 50 }}>
          {drag.id}
        </div>
      )}
    </div>
  );
}

// ── Variant C: replica of today's task rows (whole row draggable, native, scrolling list) ──
function VariantC({ log }: { log: Log }) {
  const [order, setOrder] = useState(() => range(12, "Task "));
  const [over, setOver] = useState<string | null>(null);
  const dragId = useRef<string | null>(null);
  return (
    <div
      onScroll={() => log("C", "list scrolled")}
      style={{ height: 230, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4, padding: 4, border: "1px dashed #2a3e6a" }}
    >
      {order.map(id => (
        <div
          key={id}
          draggable
          onPointerDown={e => log("C", `pointerdown(${e.pointerType})`)}
          onPointerCancel={e => log("C", `pointercancel(${e.pointerType}) <- browser took the gesture`)}
          onTouchStart={() => log("C", "touchstart")}
          onDragStart={() => { dragId.current = id; log("C", `dragstart ${id}`); }}
          onDragOver={e => { e.preventDefault(); setOver(id); }}
          onDrop={() => { if (dragId.current) setOrder(o => moveItem(o, dragId.current!, id)); log("C", `drop on ${id}`); setOver(null); }}
          onDragEnd={() => { dragId.current = null; setOver(null); log("C", "dragend"); }}
          style={{
            display: "flex", alignItems: "center", gap: 6, padding: "8px", borderRadius: 8, flexShrink: 0,
            background: over === id ? "rgba(61,110,234,0.2)" : "#0d1628", border: "1px solid rgba(61,110,234,0.2)",
            color: "#d8e4f8", cursor: "grab", fontSize: 14,
          }}
        >
          <GripVertical size={11} style={{ color: "#2a3e6a" }} /> {id}
        </div>
      ))}
    </div>
  );
}

export default function DragProbe() {
  const [lines, setLines] = useState<{ t: string; n: number }[]>([]);
  // Floods (pointermove, dragover, scroll) are folded into "×N" on one line so the log stays readable.
  const log = useCallback<Log>((who, what) => {
    const t = `${who}: ${what}`;
    setLines(prev => {
      const last = prev[prev.length - 1];
      if (last && last.t === t) return [...prev.slice(0, -1), { t, n: last.n + 1 }];
      return [...prev, { t, n: 1 }].slice(-40);
    });
  }, []);

  return (
    <div style={{ padding: 10, fontFamily: "sans-serif", color: "#d8e4f8", background: "#050a18", minHeight: "100vh", fontSize: 13 }}>
      <div style={{ display: "flex", gap: 14 }}>
        <div style={{ flex: "0 0 400px" }}>
          <b>A — native drag from handle</b>
          <VariantA log={log} />
          <div style={{ height: 14 }} />
          <b>B — pointer events on handle</b>
          <VariantB log={log} />
        </div>
        <div style={{ flex: "0 0 230px" }}>
          <b>C — today's task rows (whole row, native)</b>
          <VariantC log={log} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <b>Event log (last 40) </b>
          <button onClick={() => setLines([])} style={{ marginLeft: 6, padding: "2px 10px" }}>clear</button>
          <pre style={{ margin: "6px 0 0", height: 330, overflow: "auto", fontSize: 11, background: "#0d1628", padding: 6 }}>
            {lines.map(l => (l.n > 1 ? `${l.t}  ×${l.n}` : l.t)).join("\n")}
          </pre>
        </div>
      </div>
    </div>
  );
}

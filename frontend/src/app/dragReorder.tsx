// Drag-to-reorder for the dashboard's lists (Phase 5, Group 3): the one drag
// implementation shared by stopwatch/timer cards and task rows. It is hand-written
// pointer events on a grip handle — chosen in Group 1 because native HTML5 drag
// does not fire from a finger on the touchscreen (the task-reorder bug, 5j).
import { useRef, useState } from "react";
import type { CSSProperties, PointerEvent, ReactNode } from "react";

/** Moves `fromId` to the slot where `toId` is now; returns the same array if nothing changes. */
export function moveId(ids: number[], fromId: number, toId: number): number[] {
  const from = ids.indexOf(fromId);
  const to = ids.indexOf(toId);
  if (from < 0 || to < 0 || from === to) return ids;
  const next = [...ids];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

type DragState = { id: number; label: string; x: number; y: number };

/**
 * Drag state and props for one reorderable list.
 *
 * `group` names the list (items of other groups are never drop targets);
 * `ids` is the list in its current display order; `onReorder` receives the full
 * id list in the new order when a drag ends on a different item. Spread
 * `handleProps(id, label)` on the grip handle and `itemProps(id)` on the whole
 * card/row, and render `ghost` once anywhere.
 */
export function useDragReorder(
  group: string,
  ids: number[],
  onReorder: (order: number[]) => void,
) {
  const [drag, setDrag] = useState<DragState | null>(null);
  const [overId, setOverId] = useState<number | null>(null);

  // Handlers read the newest ids/callback through refs so a drag that spans
  // re-renders (the 1 Hz tick, a state load) never works from a stale list.
  const latest = useRef({ ids, onReorder });
  latest.current = { ids, onReorder };
  const dragId = useRef<number | null>(null);

  // The handle keeps pointer capture, so `e.target` is always the handle; the
  // item under the finger has to be found by position instead.
  const itemAt = (x: number, y: number): number | null => {
    const el = document.elementFromPoint(x, y)?.closest(`[data-drag-group="${group}"]`) as HTMLElement | null;
    return el ? Number(el.dataset.dragId) : null;
  };

  const finish = () => { dragId.current = null; setDrag(null); setOverId(null); };

  const handleProps = (id: number, label: string) => ({
    // touch-action none: without it the browser scrolls the page/list instead
    // of delivering the finger's moves to us.
    style: { touchAction: "none", cursor: "grab" } as CSSProperties,
    onPointerDown: (e: PointerEvent<HTMLElement>) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation(); // a card's own click (dismiss alert) must not see the grab
      e.currentTarget.setPointerCapture(e.pointerId);
      dragId.current = id;
      setDrag({ id, label, x: e.clientX, y: e.clientY });
    },
    onPointerMove: (e: PointerEvent<HTMLElement>) => {
      if (dragId.current !== id) return;
      setDrag({ id, label, x: e.clientX, y: e.clientY });
      setOverId(itemAt(e.clientX, e.clientY));
    },
    onPointerUp: (e: PointerEvent<HTMLElement>) => {
      if (dragId.current !== id) return;
      const target = itemAt(e.clientX, e.clientY);
      const { ids: current, onReorder: apply } = latest.current;
      finish();
      if (target === null || target === id) return;
      const next = moveId(current, id, target);
      if (next !== current) apply(next);
    },
    // The browser took the gesture (or capture was lost): abandon, change nothing.
    onPointerCancel: finish,
    // A long press would otherwise open the browser's context menu mid-drag.
    onContextMenu: (e: React.MouseEvent) => e.preventDefault(),
    onClick: (e: React.MouseEvent) => e.stopPropagation(),
  });

  const itemProps = (id: number) => ({ "data-drag-group": group, "data-drag-id": id });

  // Floating copy under the finger; pointer-events none so elementFromPoint sees through it.
  const ghost: ReactNode = drag && (
    <div
      style={{
        position: "fixed", left: drag.x - 24, top: drag.y - 24, zIndex: 100,
        pointerEvents: "none", maxWidth: 200, padding: "8px 14px", borderRadius: 10,
        background: "#2250c4", color: "white", fontSize: 14, opacity: 0.92,
        boxShadow: "0 6px 20px rgba(0,0,0,0.5)", whiteSpace: "nowrap",
        overflow: "hidden", textOverflow: "ellipsis",
      }}
    >
      {drag.label}
    </div>
  );

  return { dragId: drag?.id ?? null, overId, handleProps, itemProps, ghost };
}

// Derived display order for events and tasks (Phase 5, Group 4: 5f, 5g).
// Pure helpers used by App.tsx at render time; nothing here is stored — the saved
// order (`pos`) only changes when the user drags.

/** Events soonest-first by ring time (ties by id so the order is stable). */
export function sortEventsByRingTime<T extends { id: number; ringTime: Date }>(events: T[]): T[] {
  return [...events].sort((a, b) => a.ringTime.getTime() - b.ringTime.getTime() || a.id - b.id);
}

/** Stable partition: incomplete tasks first, completed last, each keeping its saved order. */
export function incompleteFirst<T extends { completed: boolean }>(tasks: T[]): T[] {
  return [...tasks.filter(t => !t.completed), ...tasks.filter(t => t.completed)];
}

/**
 * Turns a drag's result on the *visible* list back into a full saved order.
 *
 * `full` is every task id in saved (`pos`) order; `visible` is the same ids in the
 * new display order after the drop; `isDone(id)` says whether a task is completed.
 * Incomplete ids take the slots incomplete tasks held in `full`, in their new
 * relative order; completed ids likewise. So completed tasks keep their hidden
 * place, and un-completing one later returns it to its slot.
 */
export function mergeVisibleOrder(full: number[], visible: number[], isDone: (id: number) => boolean): number[] {
  const open = visible.filter(id => !isDone(id));
  const done = visible.filter(id => isDone(id));
  let o = 0;
  let d = 0;
  // Ids missing from `visible` (shouldn't happen) keep their old slot.
  return full.map(id => (isDone(id) ? (done[d++] ?? id) : (open[o++] ?? id)));
}

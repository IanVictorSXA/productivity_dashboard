import { useState, useEffect, useRef, useCallback } from "react";
import {
  Play,
  Pause,
  X,
  Plus,
  Check,
  Clock,
  CheckSquare,
  GripVertical,
  Pencil,
} from "lucide-react";
import { ImageWithFallback } from "@/app/components/figma/ImageWithFallback";
import avatarImg from "@/imports/bloodsport_pfp.jpg";

// ─── Config ───────────────────────────────────────────────────────────────────
const API_ENDPOINT = "http://localhost:8080/api";

// Only these three stopwatches are mutually exclusive
const MUTEX_LABELS = ["Work", "Misc", "Waste"];

// ─── API ─────────────────────────────────────────────────────────────────────
async function sendMessage(payload: object): Promise<void> {
  console.log("[API →]", JSON.stringify(payload, null, 2));
  try {
    await fetch(API_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // backend unreachable — logged to console only
  }
}

async function fetchState(): Promise<ApiState | null> {
  try {
    const res = await fetch(API_ENDPOINT);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ─── Backend shape ────────────────────────────────────────────────────────────
// GET /api → ApiState
type ApiDuration = {
  id: number;
  label: string;
  subtype: "timer" | "stopwatch";
  total_ms: number;
  accumulated_ms: number;
  started_at: number | null; // epoch ms when last resumed; null = paused
  alerting: boolean;
};
type ApiEvent = { id: number; label: string; ring_time: string; alerting: boolean };
type ApiTask  = { id: number; label: string; completed: boolean };
type ApiState = { events?: ApiEvent[]; durations?: ApiDuration[]; tasks?: ApiTask[] };

// ─── Frontend types ───────────────────────────────────────────────────────────
type EventCard = { id: number; label: string; ringTime: Date; alerting: boolean; completed: boolean };

/**
 * Timer state is timestamp-based so display values are always computed from
 * the moment of resume rather than a stale counter.
 *
 *   elapsed  = accumulatedMs + (running ? Date.now() - startedAt : 0)
 *   display  = subtype === "timer" ? max(0, totalMs - elapsed) : elapsed
 */
type DurationCard = {
  id: number;
  label: string;
  subtype: "timer" | "stopwatch";
  totalMs: number;          // timer: countdown target; stopwatch: ignored
  accumulatedMs: number;    // ms elapsed before the last resume
  startedAt: number | null; // Date.now() when last resumed; null = paused
  alerting: boolean;
};

type Task = { id: number; label: string; completed: boolean };

// ─── ID generator ─────────────────────────────────────────────────────────────
let _nextId = 1000; // start above likely backend IDs
const genId = () => ++_nextId;

// ─── Pure time helpers ────────────────────────────────────────────────────────
function nowTimeStr() {
  return new Date().toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function fmtMs(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function parseHhMmSs(hh: string, mm: string, ss: string): number {
  return ((parseInt(hh) || 0) * 3600 + (parseInt(mm) || 0) * 60 + (parseInt(ss) || 0)) * 1000;
}

function msToHhMmSs(ms: number): { hh: string; mm: string; ss: string } {
  const total = Math.max(0, Math.floor(ms / 1000));
  return {
    hh: String(Math.floor(total / 3600)).padStart(2, "0"),
    mm: String(Math.floor((total % 3600) / 60)).padStart(2, "0"),
    ss: String(total % 60).padStart(2, "0"),
  };
}

function parseRingTime(hh: string, mm: string, ampm: "AM" | "PM"): Date {
  let h = parseInt(hh, 10) || 0;
  const m = parseInt(mm, 10) || 0;
  if (ampm === "AM" && h === 12) h = 0;
  if (ampm === "PM" && h !== 12) h += 12;
  const now = new Date();
  const ring = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m, 0);
  if (ring <= now) ring.setDate(ring.getDate() + 1);
  return ring;
}

function msToRingInputs(d: Date): { hh: string; mm: string; ampm: "AM" | "PM" } {
  let h = d.getHours();
  const m = d.getMinutes();
  const ampm: "AM" | "PM" = h >= 12 ? "PM" : "AM";
  if (h > 12) h -= 12;
  if (h === 0) h = 12;
  return { hh: String(h).padStart(2, "0"), mm: String(m).padStart(2, "0"), ampm };
}

function msUntil(d: Date): number {
  return Math.max(0, d.getTime() - Date.now());
}

/** Elapsed ms for a duration card at a given wall-clock instant. */
function getElapsedMs(card: DurationCard, now: number): number {
  return card.accumulatedMs + (card.startedAt !== null ? now - card.startedAt : 0);
}

/**
 * Value to display on the card face.
 * Uses Date.now() — never the stale `tick` value — so pause/resume never
 * produces a momentary backward jump.
 */
function getDisplayMs(card: DurationCard): number {
  const now = Date.now();
  const elapsed = getElapsedMs(card, now);
  return card.subtype === "stopwatch" ? elapsed : Math.max(0, card.totalMs - elapsed);
}

// ─── Modal state ──────────────────────────────────────────────────────────────
type ModalMode     = "duration" | "event";
type TimeInputMode = "total" | "ring";

type ModalState = {
  open: boolean;
  // Creation vs edit
  isNewCard: boolean;
  editId: number | null;
  editWasRunning: boolean; // timer only: was it running when we opened the edit modal?
  // Which section this modal is for
  mode: ModalMode;
  subtype: "timer" | "stopwatch"; // duration only
  timeMode: TimeInputMode;
  label: string;
  // hh/mm/ss meaning:
  //   new duration timer  → total countdown time
  //   edit duration timer → remaining time  (read from paused card, written back on save)
  //   new/edit event with timeMode=total → duration until ring
  //   (stopwatch and ring-time modes don't use these)
  hh: string; mm: string; ss: string;
  // ring-time fields (events and ring-time timer creation)
  rhh: string; rmm: string; ampm: "AM" | "PM";
};

const defaultModal = (): ModalState => ({
  open: false,
  isNewCard: true,
  editId: null,
  editWasRunning: false,
  mode: "duration",
  subtype: "timer",
  timeMode: "total",
  label: "",
  hh: "00", mm: "00", ss: "00",
  rhh: "00", rmm: "00", ampm: "AM",
});

// ─── App ──────────────────────────────────────────────────────────────────────
export default function App() {
  // `tick` is only used to schedule re-renders every second.
  // It is NOT passed into any time calculation — getDisplayMs uses Date.now().
  const [tick, setTick] = useState(0);

  const [events,    setEvents]    = useState<EventCard[]>([]);
  const [durations, setDurations] = useState<DurationCard[]>([]);
  const [tasks,     setTasks]     = useState<Task[]>([]);
  const [modal,     setModal]     = useState<ModalState>(defaultModal());
  const [loading,   setLoading]   = useState(true);
  const [editingTask, setEditingTask] = useState<number | null>(null);
  const [dragOver,    setDragOver]   = useState<number | null>(null);
  const dragItem = useRef<number | null>(null);

  // ── 1 Hz re-render trigger ──
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  // ── Boot: fetch state, ensure Work/Misc/Waste exist ──
  useEffect(() => {
    (async () => {
      const state = await fetchState();

      let loadedDurations: DurationCard[] = [];
      let loadedEvents:    EventCard[]    = [];
      let loadedTasks:     Task[]         = [];

      if (state) {
        loadedDurations = (state.durations ?? []).map(d => ({
          id: d.id, label: d.label, subtype: d.subtype,
          totalMs: d.total_ms, accumulatedMs: d.accumulated_ms,
          startedAt: d.started_at, alerting: d.alerting,
        }));
        loadedEvents = (state.events ?? []).map(e => ({
          id: e.id, label: e.label, ringTime: new Date(e.ring_time), alerting: e.alerting, completed: false,
        }));
        loadedTasks = (state.tasks ?? []).map(t => ({
          id: t.id, label: t.label, completed: t.completed,
        }));
      }

      if (loadedTasks.length === 0) {
        loadedTasks = [
          { id: genId(), label: "Read book for 30 min", completed: true },
          { id: genId(), label: "Code", completed: false },
          { id: genId(), label: "Vacuum", completed: false },
        ];
      }

      // Ensure Work / Misc / Waste stopwatches exist
      const toCreate: DurationCard[] = [];
      for (const name of MUTEX_LABELS) {
        if (!loadedDurations.some(d => d.label === name)) {
          const card: DurationCard = {
            id: genId(), label: name, subtype: "stopwatch",
            totalMs: 0, accumulatedMs: 0, startedAt: null, alerting: false,
          };
          toCreate.push(card);
          sendMessage({ id: card.id, type: "duration", type_duration: "stopwatch", task: name, current_time: nowTimeStr(), command: "create" });
        }
      }

      setDurations([...loadedDurations, ...toCreate]);
      setEvents(loadedEvents);
      setTasks(loadedTasks);
      setLoading(false);
    })();
  }, []);

  // ── Alert check: event countdown hits zero ──
  useEffect(() => {
    const id = setInterval(() => {
      setEvents(prev => prev.map(e => {
        if (!e.alerting && !e.completed && msUntil(e.ringTime) <= 0) {
          sendMessage({ id: e.id, type: "event", command: "ring", task: e.label });
          return { ...e, alerting: true };
        }
        return e;
      }));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Alert check: countdown timer hits zero ──
  useEffect(() => {
    const id = setInterval(() => {
      setDurations(prev => prev.map(d => {
        if (d.subtype !== "timer" || d.alerting || d.startedAt === null) return d;
        if (getDisplayMs(d) <= 0) {
          sendMessage({ id: d.id, command: "complete" });
          return { ...d, startedAt: null, alerting: true };
        }
        return d;
      }));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Toggle running ──────────────────────────────────────────────────────────
  //
  // Pause/resume correctness:
  //   On PAUSE: snapshot elapsed = accumulatedMs + (Date.now() - startedAt)
  //             store in accumulatedMs; set startedAt = null
  //   On RESUME: set startedAt = Date.now()
  //              display = accumulatedMs + (Date.now() - startedAt) ≈ accumulatedMs (just resumed)
  //
  //   Because getDisplayMs always calls Date.now() (not a stale tick), the
  //   first render after resume shows accumulatedMs + ~0ms — never negative.
  const toggleRunning = useCallback((id: number) => {
    const now = Date.now();
    setDurations(prev => {
      const card = prev.find(d => d.id === id);
      if (!card) return prev;
      const willRun = card.startedAt === null;

      return prev.map(d => {
        if (d.id === id) {
          if (willRun) {
            sendMessage({ id: d.id, current_time: nowTimeStr(), command: "resume" });
            // startedAt = now; accumulatedMs unchanged — display = accumulated + 0
            return { ...d, startedAt: now };
          } else {
            // Freeze elapsed into accumulatedMs before clearing startedAt
            const elapsed = getElapsedMs(d, now);
            if (d.subtype === "timer") {
              sendMessage({ id: d.id, remaining_time: fmtMs(Math.max(0, d.totalMs - elapsed)), command: "pause" });
            } else {
              sendMessage({ id: d.id, command: "pause" });
            }
            return { ...d, accumulatedMs: elapsed, startedAt: null };
          }
        }

        // Mutex: starting a mutex stopwatch pauses all other running mutex stopwatches
        if (willRun && MUTEX_LABELS.includes(card.label) && MUTEX_LABELS.includes(d.label) && d.startedAt !== null) {
          const elapsed = getElapsedMs(d, now);
          sendMessage({ id: d.id, command: "pause" });
          return { ...d, accumulatedMs: elapsed, startedAt: null };
        }

        return d;
      });
    });
  }, []);

  // ── Delete duration card ──
  const deleteDuration = useCallback((id: number) => {
    setDurations(prev => {
      const card = prev.find(d => d.id === id);
      if (card) {
        const elapsed  = getElapsedMs(card, Date.now());
        const payload: Record<string, unknown> = { id, command: "delete" };
        if (card.subtype === "timer") payload.remaining_time = fmtMs(Math.max(0, card.totalMs - elapsed));
        sendMessage(payload);
      }
      return prev.filter(d => d.id !== id);
    });
  }, []);

  // ── Delete event ──
  const deleteEvent = useCallback((id: number) => {
    sendMessage({ id, type: "event", command: "delete" });
    setEvents(prev => prev.filter(e => e.id !== id));
  }, []);

  // ── Tasks ──
  const addTask = () => {
    const id = genId();
    setTasks(prev => [...prev, { id, label: "New Task", completed: false }]);
    setEditingTask(id);
    sendMessage({ id, type: "task", task: "New Task", command: "create" });
  };

  const toggleTask = (id: number) => {
    setTasks(prev => prev.map(t => {
      if (t.id !== id) return t;
      const completed = !t.completed;
      sendMessage({ id, type: "task", completed, command: "update" });
      return { ...t, completed };
    }));
  };

  const deleteTask = (id: number) => {
    setTasks(prev => prev.filter(t => t.id !== id));
    sendMessage({ id, type: "task", command: "delete" });
  };

  const updateTaskLabel = (id: number, label: string) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, label } : t));
    sendMessage({ id, type: "task", task: label, command: "update" });
  };

  // ── Drag-reorder tasks ──
  const onDragStart = (id: number) => { dragItem.current = id; };
  const onDragOver  = (e: React.DragEvent, id: number) => { e.preventDefault(); setDragOver(id); };
  const onDrop      = (targetId: number) => {
    const sourceId = dragItem.current;
    if (sourceId === null || sourceId === targetId) { setDragOver(null); return; }
    setTasks(prev => {
      const arr = [...prev];
      const si = arr.findIndex(t => t.id === sourceId);
      const ti = arr.findIndex(t => t.id === targetId);
      const [item] = arr.splice(si, 1);
      arr.splice(ti, 0, item);
      sendMessage({ type: "task", command: "reorder", order: arr.map(t => t.id) });
      return arr;
    });
    dragItem.current = null;
    setDragOver(null);
  };

  // ── Open create modal ──
  const openCreateModal = () => setModal({ ...defaultModal(), open: true });

  // ── Open edit modal for Duration card ──
  //
  // Stopwatch: only label editable; timing state is never touched.
  // Timer:     auto-pause, pre-fill remaining time; will auto-resume on save.
  const openEditDuration = useCallback((card: DurationCard) => {
    if (card.subtype === "stopwatch") {
      // No time fields for stopwatch edit
      setModal({
        ...defaultModal(),
        open: true, isNewCard: false, editId: card.id,
        mode: "duration", subtype: "stopwatch",
        label: card.label,
      });
      return;
    }

    // Timer: pause if running, then open modal with remaining time
    const now = Date.now();
    let pausedCard = card;
    const wasRunning = card.startedAt !== null;

    if (wasRunning) {
      const elapsed = getElapsedMs(card, now);
      pausedCard = { ...card, accumulatedMs: elapsed, startedAt: null };
      setDurations(prev => prev.map(d => d.id === card.id ? pausedCard : d));
      sendMessage({ id: card.id, remaining_time: fmtMs(Math.max(0, card.totalMs - elapsed)), command: "pause" });
    }

    // Pre-fill with remaining time (floor to seconds — what the user sees)
    const remainingMs = Math.max(0, pausedCard.totalMs - pausedCard.accumulatedMs);
    const { hh, mm, ss } = msToHhMmSs(remainingMs);

    setModal({
      ...defaultModal(),
      open: true, isNewCard: false, editId: card.id, editWasRunning: wasRunning,
      mode: "duration", subtype: "timer",
      label: card.label,
      hh, mm, ss,
    });
  }, []);

  // ── Open edit modal for Event card ──
  const openEditEvent = useCallback((card: EventCard) => {
    const { hh: rhh, mm: rmm, ampm } = msToRingInputs(card.ringTime);
    const remainingMs = msUntil(card.ringTime);
    const { hh, mm, ss } = msToHhMmSs(remainingMs);
    setModal({
      ...defaultModal(),
      open: true, isNewCard: false, editId: card.id,
      mode: "event", timeMode: "ring",
      label: card.label,
      hh, mm, ss, rhh, rmm, ampm,
    });
  }, []);

  // ── Close modal (also resumes timer if edit was interrupted) ──
  const closeModal = useCallback(() => {
    const { editId, editWasRunning, mode, subtype } = modal;
    if (!modal.isNewCard && editId !== null && mode === "duration" && subtype === "timer" && editWasRunning) {
      // User cancelled edit — resume the timer
      const now = Date.now();
      setDurations(prev => prev.map(d => {
        if (d.id !== editId) return d;
        sendMessage({ id: d.id, current_time: nowTimeStr(), command: "resume" });
        return { ...d, startedAt: now };
      }));
    }
    setModal(defaultModal());
  }, [modal]);

  // ── Save card (create or edit) ──
  const saveCard = useCallback(() => {
    const { isNewCard, editId, editWasRunning, mode, subtype, timeMode, label, hh, mm, ss, rhh, rmm, ampm } = modal;
    const lbl = label.trim() || (mode === "event" ? "Event" : subtype === "stopwatch" ? "Stopwatch" : "Timer");

    // ── EDIT ──
    if (!isNewCard && editId !== null) {
      if (mode === "duration" && subtype === "stopwatch") {
        // Stopwatch edit: ONLY update the label; never touch timing state
        setDurations(prev => prev.map(d => d.id === editId ? { ...d, label: lbl } : d));
        sendMessage({ id: editId, type: "duration", type_duration: "stopwatch", task: lbl, command: "edit" });

      } else if (mode === "duration" && subtype === "timer") {
        // Timer edit: update label + remaining time; resume if it was running
        setDurations(prev => {
          const existing = prev.find(d => d.id === editId);
          if (!existing) return prev;

          // hh/mm/ss = remaining time the user sees; compute new accumulatedMs
          const newRemainingMs  = parseHhMmSs(hh, mm, ss);
          const newAccumulatedMs = Math.max(0, existing.totalMs - newRemainingMs);
          const resumeAt = editWasRunning ? Date.now() : null;

          sendMessage({
            id: editId, type: "duration", type_duration: "timer", task: lbl,
            current_time: nowTimeStr(),
            total_time: fmtMs(existing.totalMs),
            remaining_time: fmtMs(newRemainingMs),
            command: "edit",
          });
          if (resumeAt !== null) {
            sendMessage({ id: editId, current_time: nowTimeStr(), command: "resume" });
          }

          return prev.map(d => d.id === editId
            ? { ...d, label: lbl, accumulatedMs: newAccumulatedMs, startedAt: resumeAt }
            : d
          );
        });

      } else if (mode === "event") {
        let ringTime: Date;
        if (timeMode === "ring") {
          ringTime = parseRingTime(rhh, rmm, ampm);
        } else {
          const ms = parseHhMmSs(hh, mm, ss);
          ringTime = new Date(Date.now() + (ms || 3600000));
        }
        setEvents(prev => prev.map(e => e.id === editId ? { ...e, label: lbl, ringTime, alerting: false, completed: false } : e));
        sendMessage({ id: editId, type: "event", task: lbl, ring_time: ringTime.toISOString(), command: "edit" });
      }

      setModal(defaultModal());
      return;
    }

    // ── CREATE ──
    if (mode === "duration") {
      const id = genId();
      if (subtype === "stopwatch") {
        const card: DurationCard = { id, label: lbl, subtype: "stopwatch", totalMs: 0, accumulatedMs: 0, startedAt: null, alerting: false };
        setDurations(prev => [...prev, card]);
        sendMessage({ id, type: "duration", type_duration: "stopwatch", task: lbl, current_time: nowTimeStr(), command: "create" });
      } else {
        let totalMs: number;
        if (timeMode === "ring") {
          totalMs = msUntil(parseRingTime(rhh, rmm, ampm));
        } else {
          totalMs = parseHhMmSs(hh, mm, ss);
        }
        if (totalMs <= 0) totalMs = 3600000;
        const card: DurationCard = { id, label: lbl, subtype: "timer", totalMs, accumulatedMs: 0, startedAt: null, alerting: false };
        setDurations(prev => [...prev, card]);
        sendMessage({ id, type: "duration", type_duration: "timer", task: lbl, current_time: nowTimeStr(), total_time: fmtMs(totalMs), command: "create" });
      }
    } else {
      const id = genId();
      let ringTime: Date;
      if (timeMode === "ring") {
        ringTime = parseRingTime(rhh, rmm, ampm);
      } else {
        const ms = parseHhMmSs(hh, mm, ss);
        ringTime = new Date(Date.now() + (ms || 3600000));
      }
      setEvents(prev => [...prev, { id, label: lbl, ringTime, alerting: false, completed: false }]);
      sendMessage({ id, type: "event", task: lbl, ring_time: ringTime.toISOString(), command: "create" });
    }
    setModal(defaultModal());
  }, [modal]);

  // ── Dismiss alerts ──
  const dismissEvent    = (id: number) => setEvents(prev => prev.map(e => e.id === id ? { ...e, alerting: false, completed: true } : e));
  const dismissDuration = (id: number) => setDurations(prev => prev.map(d => d.id === id ? { ...d, alerting: false } : d));

  // ── Shutdown: delete all cards, then send close ──
  const handleShutdown = useCallback(async () => {
    const now = Date.now();
    const deletions: Promise<void>[] = [];

    for (const d of durations) {
      const elapsed = getElapsedMs(d, now);
      const payload: Record<string, unknown> = { id: d.id, command: "delete" };
      if (d.subtype === "timer") payload.remaining_time = fmtMs(Math.max(0, d.totalMs - elapsed));
      deletions.push(sendMessage(payload));
    }
    for (const ev of events) {
      deletions.push(sendMessage({ id: ev.id, type: "event", command: "delete" }));
    }

    await Promise.all(deletions);
    await sendMessage({ command: "close", current_time: nowTimeStr() });
  }, [durations, events]);

  // ── Clock display (only used for header) ──
  // Referencing `tick` here keeps the header updating every second.
  void tick;
  const now       = new Date();
  const dateStr   = now.toLocaleDateString("en-US", { month: "numeric", day: "numeric", year: "numeric" });
  const timeStr   = now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });

  if (loading) {
    return (
      <div className="w-full h-screen flex items-center justify-center" style={{ fontFamily: "'Jockey One', sans-serif", background: "#080c18" }}>
        <span className="text-xl" style={{ color: "#7baff0" }}>Loading…</span>
      </div>
    );
  }

  return (
    <div
      className="w-full h-screen overflow-hidden flex flex-col relative"
      style={{ fontFamily: "'Jockey One', sans-serif", background: "#080c18", color: "#e8eaf0", maxWidth: "1024px", maxHeight: "600px", margin: "0 auto" }}
    >
      {/* ── Header ── */}
      <header
        className="flex items-center px-4 py-2 gap-3"
        style={{ borderBottom: "1px solid rgba(61,110,234,0.25)", background: "#0a0e1e", minHeight: "48px" }}
      >
        <span className="text-base font-semibold tracking-wide mr-auto" style={{ color: "#7baff0" }}>
          Productivity Dashboard
        </span>
        <span className="text-sm" style={{ color: "#7baff0" }}>{dateStr}</span>
        <span className="text-xl font-bold text-white">{timeStr}</span>
        <button
          onClick={handleShutdown}
          className="w-9 h-9 rounded-full flex items-center justify-center text-white transition-opacity hover:opacity-80 active:opacity-60"
          style={{ background: "#e03555" }}
          title="Close & Save"
        >
          <X size={18} />
        </button>
      </header>

      {/* ── Body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Left 75% ── */}
        <div className="flex flex-col overflow-hidden relative" style={{ width: "75%" }}>
          <div
            className="flex-1 overflow-y-auto px-4 py-3 space-y-3 pb-20"
            style={{ scrollbarWidth: "thin", scrollbarColor: "#1e3a6e transparent" }}
          >
            {/* Events */}
            <section>
              <h2 className="text-lg mb-2" style={{ color: "#c8d8f8", letterSpacing: "0.04em" }}>Events</h2>
              <div className="flex flex-wrap gap-3">
                {events.map(ev => (
                  <EventCardView
                    key={ev.id}
                    card={ev}
                    onEdit={() => openEditEvent(ev)}
                    onDelete={() => deleteEvent(ev.id)}
                    onDismiss={() => dismissEvent(ev.id)}
                  />
                ))}
                {events.length === 0 && (
                  <span className="text-sm" style={{ color: "#4a5f8a" }}>No events — press + to add</span>
                )}
              </div>
            </section>

            <div style={{ height: "1px", background: "rgba(61,110,234,0.18)" }} />

            {/* Tasks Duration */}
            <section>
              <h2 className="text-lg mb-2" style={{ color: "#c8d8f8", letterSpacing: "0.04em" }}>Tasks Duration</h2>
              <div className="flex flex-wrap gap-3">
                {durations.map(d => (
                  <DurationCardView
                    key={d.id}
                    card={d}
                    onToggle={() => toggleRunning(d.id)}
                    onEdit={() => openEditDuration(d)}
                    onDelete={() => deleteDuration(d.id)}
                    onDismiss={() => dismissDuration(d.id)}
                  />
                ))}
                {durations.length === 0 && (
                  <span className="text-sm" style={{ color: "#4a5f8a" }}>No timers — press + to add</span>
                )}
              </div>
            </section>
          </div>

          {/* Floating controls */}
          <div className="absolute bottom-4 left-4 flex items-center gap-3">
            <button
              onClick={openCreateModal}
              className="w-14 h-14 rounded-full flex items-center justify-center text-white shadow-lg transition-transform hover:scale-105 active:scale-95"
              style={{ background: "#2250c4", boxShadow: "0 0 20px rgba(61,110,234,0.5)" }}
            >
              <Plus size={28} />
            </button>
            <div
              className="w-14 h-14 rounded-full overflow-hidden shrink-0"
              style={{ border: "2px solid rgba(61,110,234,0.5)", boxShadow: "0 0 14px rgba(61,110,234,0.3)" }}
            >
              <ImageWithFallback src={avatarImg} alt="AI Assistant" className="w-full h-full object-cover" />
            </div>
          </div>
        </div>

        {/* ── Right sidebar 25% ── */}
        <div
          className="flex flex-col overflow-hidden"
          style={{ width: "25%", borderLeft: "1px solid rgba(61,110,234,0.2)", background: "#090d1c" }}
        >
          <div className="px-3 py-2 border-b" style={{ borderColor: "rgba(61,110,234,0.2)" }}>
            <h2 className="text-lg text-center" style={{ color: "#c8d8f8", letterSpacing: "0.04em" }}>Tasks</h2>
          </div>
          <div
            className="flex-1 overflow-y-auto px-2 py-2 space-y-1"
            style={{ scrollbarWidth: "thin", scrollbarColor: "#1e3a6e transparent" }}
          >
            {tasks.map(t => (
              <div
                key={t.id}
                draggable
                onDragStart={() => onDragStart(t.id)}
                onDragOver={e => onDragOver(e, t.id)}
                onDrop={() => onDrop(t.id)}
                onDragLeave={() => setDragOver(null)}
                className="flex items-center gap-1.5 rounded-lg px-2 py-2"
                style={{
                  background: dragOver === t.id ? "rgba(61,110,234,0.2)" : "#0d1628",
                  border: "1px solid rgba(61,110,234,0.2)",
                  cursor: "grab",
                }}
              >
                <GripVertical size={11} style={{ color: "#2a3e6a" }} className="shrink-0" />
                <button
                  className="w-5 h-5 rounded-full flex items-center justify-center shrink-0"
                  style={{ border: "1.5px solid #3d6eea" }}
                  onClick={() => deleteTask(t.id)}
                >
                  <X size={9} className="text-blue-400" />
                </button>
                {editingTask === t.id ? (
                  <input
                    autoFocus
                    className="flex-1 bg-transparent text-sm text-white outline-none min-w-0"
                    style={{ fontFamily: "'Jockey One', sans-serif" }}
                    value={t.label}
                    onChange={e => setTasks(prev => prev.map(tk => tk.id === t.id ? { ...tk, label: e.target.value } : tk))}
                    onBlur={() => { updateTaskLabel(t.id, t.label); setEditingTask(null); }}
                    onKeyDown={e => { if (e.key === "Enter") { updateTaskLabel(t.id, t.label); setEditingTask(null); } }}
                  />
                ) : (
                  <span
                    className="flex-1 text-sm min-w-0 truncate cursor-text"
                    style={{ textDecoration: t.completed ? "line-through" : "none", color: t.completed ? "#4a5f8a" : "#d8e4f8" }}
                    onDoubleClick={() => setEditingTask(t.id)}
                  >
                    {t.label}
                  </span>
                )}
                <button
                  className="w-5 h-5 rounded flex items-center justify-center shrink-0"
                  style={{ border: "1.5px solid #3d6eea", background: t.completed ? "#3d6eea" : "transparent" }}
                  onClick={() => toggleTask(t.id)}
                >
                  {t.completed && <Check size={10} className="text-white" />}
                </button>
              </div>
            ))}
          </div>
          <div className="flex justify-end px-3 pb-3 pt-1">
            <button
              onClick={addTask}
              className="w-11 h-11 rounded-full flex items-center justify-center"
              style={{ background: "#1e2a44", border: "1px solid rgba(61,110,234,0.4)" }}
            >
              <Plus size={20} className="text-blue-300" />
            </button>
          </div>
        </div>
      </div>

      {/* ── Modal ── */}
      {modal.open && (
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.72)", zIndex: 50 }}
          onMouseDown={e => { if (e.target === e.currentTarget) closeModal(); }}
        >
          <CreationModal modal={modal} setModal={setModal} onSave={saveCard} onClose={closeModal} />
        </div>
      )}

      <style>{`
        @keyframes blink { 0%,100% { opacity:1 } 50% { opacity:0.35 } }
      `}</style>
    </div>
  );
}

// ─── Event card view ──────────────────────────────────────────────────────────
function EventCardView({ card, onEdit, onDelete, onDismiss }: {
  card: EventCard;
  onEdit: () => void;
  onDelete: () => void;
  onDismiss: () => void;
}) {
  // getDisplayMs uses Date.now() internally, so this is always current
  const remaining = msUntil(card.ringTime);
  return (
    <div
      className="relative rounded-xl px-4 py-2 flex flex-col min-w-[148px]"
      style={{
        background: card.alerting ? "#3a0a14" : "#0d1628",
        border: card.alerting ? "2px solid #e03555" : "1px solid rgba(61,110,234,0.3)",
        boxShadow: "0 0 12px rgba(61,110,234,0.12)",
        animation: card.alerting ? "blink 0.8s step-start infinite" : undefined,
        cursor: card.alerting ? "pointer" : "default",
      }}
      onClick={() => card.alerting && onDismiss()}
    >
      <div className="flex items-center justify-between mb-1 gap-2">
        <span className="text-sm truncate" style={{ color: "#b0c8f0" }}>{card.label}</span>
        <div className="flex items-center gap-1 shrink-0">
          <IconBtn onClick={e => { e.stopPropagation(); onEdit(); }}><Pencil size={9} className="text-blue-300" /></IconBtn>
          <IconBtn onClick={e => { e.stopPropagation(); onDelete(); }}><X size={9} className="text-blue-300" /></IconBtn>
        </div>
      </div>
      <span className="text-3xl font-bold tracking-wider text-white">
        {card.alerting ? "RING!" : fmtMs(remaining)}
      </span>
    </div>
  );
}

// ─── Duration card view ───────────────────────────────────────────────────────
function DurationCardView({ card, onToggle, onEdit, onDelete, onDismiss }: {
  card: DurationCard;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onDismiss: () => void;
}) {
  // getDisplayMs calls Date.now() — always accurate, never stale-tick-based
  const display    = getDisplayMs(card);
  const isRunning  = card.startedAt !== null;

  return (
    <div
      className="relative rounded-xl px-4 py-2 flex flex-col min-w-[160px]"
      style={{
        background: "#0d1628",
        border: card.alerting ? "2px solid #e03555" : isRunning ? "1px solid rgba(61,110,234,0.7)" : "1px solid rgba(61,110,234,0.3)",
        boxShadow: isRunning ? "0 0 16px rgba(61,110,234,0.25)" : "0 0 12px rgba(61,110,234,0.1)",
        animation: card.alerting ? "blink 0.8s step-start infinite" : undefined,
        cursor: card.alerting ? "pointer" : "default",
      }}
      onClick={() => card.alerting && onDismiss()}
    >
      <div className="flex items-center justify-between mb-1 gap-2">
        <div className="flex items-center gap-1 min-w-0">
          {card.subtype === "timer"
            ? <CheckSquare size={13} className="text-blue-400 shrink-0" />
            : <Clock       size={13} className="text-blue-400 shrink-0" />
          }
          <span className="text-sm truncate" style={{ color: "#b0c8f0" }}>{card.label}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <IconBtn onClick={e => { e.stopPropagation(); onEdit(); }}><Pencil size={9} className="text-blue-300" /></IconBtn>
          <IconBtn onClick={e => { e.stopPropagation(); onDelete(); }}><X size={9} className="text-blue-300" /></IconBtn>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-3xl font-bold tracking-wider text-white">
          {card.alerting ? "DONE!" : fmtMs(display)}
        </span>
        {!card.alerting && (
          <button
            className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
            style={{ background: isRunning ? "#1a2d6e" : "#2250c4" }}
            onClick={e => { e.stopPropagation(); onToggle(); }}
          >
            {isRunning
              ? <Pause size={16} fill="white" className="text-white" />
              : <Play  size={16} fill="white" className="text-white ml-0.5" />
            }
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Modal ────────────────────────────────────────────────────────────────────
function CreationModal({ modal, setModal, onSave, onClose }: {
  modal: ModalState;
  setModal: React.Dispatch<React.SetStateAction<ModalState>>;
  onSave: () => void;
  onClose: () => void;
}) {
  const set = <K extends keyof ModalState>(k: K, v: ModalState[K]) =>
    setModal(p => ({ ...p, [k]: v }));

  const { isNewCard, mode, subtype, timeMode } = modal;

  // What we show depends on context
  const isStopwatchEdit = !isNewCard && subtype === "stopwatch";
  const isTimerEdit     = !isNewCard && mode === "duration" && subtype === "timer";
  const isEventEdit     = !isNewCard && mode === "event";

  // Label for the time field
  const timeFieldLabel = isTimerEdit
    ? "Remaining time"
    : timeMode === "ring" ? "Ring time" : "Duration";

  // Whether to show the HH:MM:SS or ring-time input
  const showTotalInput = !isStopwatchEdit && (isTimerEdit || (isNewCard && !(mode === "duration" && subtype === "stopwatch") && timeMode === "total") || (isEventEdit && timeMode === "total"));
  const showRingInput  = !isStopwatchEdit && (timeMode === "ring") && !isTimerEdit;

  return (
    <div
      className="rounded-2xl p-5 flex flex-col gap-4"
      style={{
        background: "#0d1628",
        border: "1px solid rgba(61,110,234,0.4)",
        boxShadow: "0 0 48px rgba(61,110,234,0.2)",
        width: "360px",
        fontFamily: "'Jockey One', sans-serif",
        maxHeight: "560px",
        overflowY: "auto",
      }}
    >
      {/* Mode tabs + close — only shown for new cards */}
      <div className="flex items-center justify-between">
        {isNewCard ? (
          <div className="flex rounded-xl overflow-hidden" style={{ border: "1px solid rgba(61,110,234,0.4)" }}>
            {(["duration", "event"] as ModalMode[]).map(m => (
              <button
                key={m}
                className="px-5 py-2 text-sm capitalize transition-colors"
                style={{ background: mode === m ? "#2250c4" : "transparent", color: mode === m ? "#fff" : "#6b7fa8" }}
                onClick={() => setModal(p => ({ ...p, mode: m, subtype: "timer", timeMode: m === "event" ? "ring" : "total" }))}
              >
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
        ) : (
          <span className="text-base" style={{ color: "#7baff0" }}>
            {mode === "event" ? "Edit Event" : subtype === "timer" ? "Edit Timer" : "Edit Stopwatch"}
          </span>
        )}
        <button onClick={onClose} className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: "#1e2a44" }}>
          <X size={13} className="text-blue-300" />
        </button>
      </div>

      {/* Duration subtype toggle — new cards only */}
      {isNewCard && mode === "duration" && (
        <div className="flex gap-3">
          {(["timer", "stopwatch"] as const).map(s => (
            <button
              key={s}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm"
              style={{
                background: subtype === s ? "#2250c4" : "transparent",
                border: "1px solid rgba(61,110,234,0.4)",
                color: subtype === s ? "#fff" : "#6b7fa8",
              }}
              onClick={() => set("subtype", s)}
            >
              {s === "timer" ? <CheckSquare size={13} /> : <Clock size={13} />}
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      )}

      {/* Timer time-mode (new cards only) */}
      {isNewCard && mode === "duration" && subtype === "timer" && (
        <TimeModeToggle
          value={timeMode}
          onChange={v => set("timeMode", v)}
          options={[{ value: "total", label: "Set total time" }, { value: "ring", label: "Set ring time" }]}
        />
      )}

      {/* Event time-mode */}
      {(isNewCard && mode === "event") || isEventEdit ? (
        <TimeModeToggle
          value={timeMode}
          onChange={v => set("timeMode", v)}
          options={[{ value: "ring", label: "Set ring time" }, { value: "total", label: "Set total time" }]}
        />
      ) : null}

      {/* Label */}
      <div>
        <div className="text-sm mb-1" style={{ color: "#8aa0d0" }}>Label</div>
        <input
          className="w-full rounded-xl px-3 py-2 text-base text-white outline-none"
          style={{ background: "#162040", border: "1px solid rgba(61,110,234,0.3)", fontFamily: "'Jockey One', sans-serif" }}
          placeholder={mode === "event" ? "Lunch 12pm" : subtype === "stopwatch" ? "Work" : "AI Project"}
          value={modal.label}
          onChange={e => set("label", e.target.value)}
        />
      </div>

      {/* HH:MM:SS total/remaining time */}
      {showTotalInput && (
        <div>
          <div className="text-sm mb-2" style={{ color: "#8aa0d0" }}>{timeFieldLabel}</div>
          <div className="flex items-center gap-2">
            <TimeDigit value={modal.hh} onChange={v => set("hh", v)} max={99} />
            <Colon />
            <TimeDigit value={modal.mm} onChange={v => set("mm", v)} max={99} />
            <Colon />
            <TimeDigit value={modal.ss} onChange={v => set("ss", v)} max={99} />
          </div>
        </div>
      )}

      {/* Ring time HH:MM + AM/PM */}
      {showRingInput && (
        <div>
          <div className="text-sm mb-2" style={{ color: "#8aa0d0" }}>Ring time</div>
          <div className="flex items-center gap-2">
            <TimeDigit value={modal.rhh} onChange={v => set("rhh", v)} max={12} />
            <Colon />
            <TimeDigit value={modal.rmm} onChange={v => set("rmm", v)} max={59} />
            <AmPmToggle value={modal.ampm} onChange={v => set("ampm", v)} />
          </div>
        </div>
      )}

      <button
        onClick={onSave}
        className="w-full py-3 rounded-xl text-lg font-bold text-white transition-opacity hover:opacity-90 active:opacity-80"
        style={{ background: "#2250c4" }}
      >
        {isNewCard ? "Create" : "Save Changes"}
      </button>
    </div>
  );
}

// ─── Small reusable bits ──────────────────────────────────────────────────────
function IconBtn({ onClick, children }: { onClick: React.MouseEventHandler; children: React.ReactNode }) {
  return (
    <button
      className="w-5 h-5 rounded-full flex items-center justify-center shrink-0"
      style={{ background: "#1e2a44" }}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function TimeModeToggle({ value, onChange, options }: {
  value: TimeInputMode;
  onChange: (v: TimeInputMode) => void;
  options: { value: TimeInputMode; label: string }[];
}) {
  return (
    <div className="flex gap-3">
      {options.map(o => (
        <button
          key={o.value}
          className="text-sm px-3 py-1 rounded-lg transition-colors"
          style={{
            background: value === o.value ? "#2250c4" : "rgba(61,110,234,0.1)",
            color: value === o.value ? "#fff" : "#6b7fa8",
            border: "1px solid rgba(61,110,234,0.25)",
          }}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function TimeDigit({
  value,
  onChange,
  max,
}: {
  value: string;
  onChange: (v: string) => void;
  max: number;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const moveCaretToEnd = () => {
    requestAnimationFrame(() => {
      const input = inputRef.current;
      if (!input) return;

      const pos = input.value.length;
      input.setSelectionRange(pos, pos);
    });
  };

  return (
    <input
      ref={inputRef}
      value={value}
      className="text-center text-4xl font-bold text-white rounded-xl outline-none w-16"
      style={{
        background: "#162040",
        border: "1px solid rgba(61,110,234,0.3)",
      }}
      onFocus={moveCaretToEnd}
      onClick={moveCaretToEnd}
      onSelect={moveCaretToEnd}
      onChange={() => {}} // controlled component
      onKeyDown={(e) => {
        if (/^\d$/.test(e.key)) {
          e.preventDefault();

          const next = value.substring(1) + e.key;
          const n = Math.min(parseInt(next, 10), max);

          onChange(String(n).padStart(2, "0"));
          moveCaretToEnd();
        }

        if (e.key === "Backspace") {
          e.preventDefault();

          onChange("0" + value[0]);
          moveCaretToEnd();
        }

        // Prevent moving the caret
        if (
          e.key === "ArrowLeft" ||
          e.key === "ArrowRight" ||
          e.key === "Home" ||
          e.key === "End"
        ) {
          e.preventDefault();
        }
      }}
    />
  );
}

function Colon() {
  return <span className="text-4xl font-bold text-white select-none">:</span>;
}

function AmPmToggle({ value, onChange }: { value: "AM" | "PM"; onChange: (v: "AM" | "PM") => void }) {
  return (
    <div className="flex flex-col rounded-xl overflow-hidden ml-1" style={{ border: "1px solid rgba(61,110,234,0.4)" }}>
      {(["AM", "PM"] as const).map(ap => (
        <button
          key={ap}
          className="px-3 py-1 text-sm font-bold"
          style={{ background: value === ap ? "#2250c4" : "#162040", color: value === ap ? "#fff" : "#6b7fa8" }}
          onClick={() => onChange(ap)}
        >
          {ap}
        </button>
      ))}
    </div>
  );
}

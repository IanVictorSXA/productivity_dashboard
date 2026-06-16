import { useState, useEffect, useRef, useCallback } from "react";
import { Play, Pause, X, Plus, Check, Clock, CheckSquare, GripVertical, Pencil } from "lucide-react";
import { ImageWithFallback } from "@/app/components/figma/ImageWithFallback";
import avatarImg from "@/imports/bloodsport_pfp.jpg";

// ─── Config ───────────────────────────────────────────────────────────────────
// Change this to your backend endpoint URL
const API_ENDPOINT = "http://localhost:8080/api";

// Cards that are mutually exclusive (only one may run at a time)
const MUTEX_LABELS = ["Work", "Misc", "Waste"];

// ─── API ─────────────────────────────────────────────────────────────────────
async function sendMessage(payload: object) {
  console.log("[API →]", JSON.stringify(payload, null, 2));
  try {
    await fetch(API_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // backend unreachable — message logged to console only
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

// ─── Expected backend state shape ────────────────────────────────────────────
// GET /api → { events, durations, tasks }
// Each duration entry uses snake_case to match backend conventions.
type ApiDuration = {
  id: number;
  label: string;
  subtype: "timer" | "stopwatch";
  total_ms: number;
  accumulated_ms: number;
  started_at: number | null; // epoch ms, null if paused
  alerting: boolean;
};

type ApiEvent = {
  id: number;
  label: string;
  ring_time: string; // ISO string
  alerting: boolean;
};

type ApiTask = {
  id: number;
  label: string;
  completed: boolean;
};

type ApiState = {
  events?: ApiEvent[];
  durations?: ApiDuration[];
  tasks?: ApiTask[];
};

// ─── Frontend types ───────────────────────────────────────────────────────────
type EventCard = {
  id: number;
  label: string;
  ringTime: Date;
  alerting: boolean;
};

// Timer state uses timestamps so display is calculated from backend timestamps,
// not from a frontend counter. This allows the frontend to be stateless w.r.t. time.
type DurationCard = {
  id: number;
  label: string;
  subtype: "timer" | "stopwatch";
  totalMs: number;          // timer: countdown target; stopwatch: 0
  accumulatedMs: number;    // ms elapsed before last resume
  startedAt: number | null; // Date.now() when last started, null = paused
  alerting: boolean;
};

type Task = {
  id: number;
  label: string;
  completed: boolean;
};

// ─── ID generator ─────────────────────────────────────────────────────────────
let _nextId = 1000; // start high to avoid collisions with backend IDs
const genId = () => ++_nextId;

// ─── Time helpers ─────────────────────────────────────────────────────────────
function nowTimeStr() {
  return new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtMs(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function parseHhMmSs(hh: string, mm: string, ss: string) {
  return ((parseInt(hh) || 0) * 3600 + (parseInt(mm) || 0) * 60 + (parseInt(ss) || 0)) * 1000;
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

function msUntil(d: Date) {
  return Math.max(0, d.getTime() - Date.now());
}

function getElapsedMs(card: DurationCard, now: number) {
  return card.accumulatedMs + (card.startedAt !== null ? now - card.startedAt : 0);
}

function getDisplayMs(card: DurationCard, now: number) {
  const elapsed = getElapsedMs(card, now);
  if (card.subtype === "stopwatch") return elapsed;
  return Math.max(0, card.totalMs - elapsed);
}

// ─── Modal state ──────────────────────────────────────────────────────────────
type ModalMode = "duration" | "event";
type TimeInputMode = "total" | "ring";

type ModalState = {
  open: boolean;
  editId: number | null; // null = creating new
  mode: ModalMode;
  subtype: "timer" | "stopwatch";
  timeMode: TimeInputMode;
  label: string;
  // total time fields (HH:MM:SS)
  hh: string; mm: string; ss: string;
  // ring time fields (HH:MM + AM/PM)
  rhh: string; rmm: string; ampm: "AM" | "PM";
  // for editing stopwatch / timer: elapsed override
  ehh: string; emm: string; ess: string;
};

const defaultModal = (): ModalState => ({
  open: false, editId: null,
  mode: "duration", subtype: "timer", timeMode: "total",
  label: "",
  hh: "00", mm: "00", ss: "00",
  rhh: "12", rmm: "00", ampm: "AM",
  ehh: "00", emm: "00", ess: "00",
});

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [tick, setTick] = useState(Date.now());
  const [events, setEvents] = useState<EventCard[]>([]);
  const [durations, setDurations] = useState<DurationCard[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [modal, setModal] = useState<ModalState>(defaultModal());
  const [loading, setLoading] = useState(true);
  const [editingTask, setEditingTask] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const dragItem = useRef<number | null>(null);

  // ── 1s tick for display ──
  useEffect(() => {
    const id = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // ── Boot: fetch state then ensure default cards ──
  useEffect(() => {
    (async () => {
      const state = await fetchState();

      let loadedDurations: DurationCard[] = [];
      let loadedEvents: EventCard[] = [];
      let loadedTasks: Task[] = [];

      if (state) {
        loadedDurations = (state.durations ?? []).map(d => ({
          id: d.id,
          label: d.label,
          subtype: d.subtype,
          totalMs: d.total_ms,
          accumulatedMs: d.accumulated_ms,
          startedAt: d.started_at,
          alerting: d.alerting,
        }));
        loadedEvents = (state.events ?? []).map(e => ({
          id: e.id,
          label: e.label,
          ringTime: new Date(e.ring_time),
          alerting: e.alerting,
        }));
        loadedTasks = (state.tasks ?? []).map(t => ({
          id: t.id,
          label: t.label,
          completed: t.completed,
        }));
      }

      // Seed default tasks if backend returned none
      if (loadedTasks.length === 0) {
        loadedTasks = [
          { id: genId(), label: "Read book for 30 min", completed: true },
          { id: genId(), label: "Code", completed: false },
          { id: genId(), label: "Vacuum", completed: false },
        ];
      }

      // Ensure Work / Misc / Waste exist
      const toCreate: DurationCard[] = [];
      for (const name of MUTEX_LABELS) {
        const exists = loadedDurations.some(d => d.label === name);
        if (!exists) {
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

  // ── Alert check (events reaching zero) ──
  useEffect(() => {
    const id = setInterval(() => {
      setEvents(prev =>
        prev.map(e => {
          if (!e.alerting && msUntil(e.ringTime) <= 0) {
            sendMessage({ id: e.id, type: "event", command: "ring", task: e.label });
            return { ...e, alerting: true };
          }
          return e;
        })
      );
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Alert check (timer countdown reaching zero) ──
  useEffect(() => {
    const id = setInterval(() => {
      const now = Date.now();
      setDurations(prev =>
        prev.map(d => {
          if (d.subtype !== "timer" || d.alerting || d.startedAt === null) return d;
          if (getDisplayMs(d, now) <= 0) {
            sendMessage({ id: d.id, command: "complete" });
            return { ...d, startedAt: null, alerting: true };
          }
          return d;
        })
      );
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Toggle running (with mutex for Work/Misc/Waste) ──
  const toggleRunning = useCallback((id: number) => {
    setDurations(prev => {
      const card = prev.find(d => d.id === id);
      if (!card) return prev;
      const willRun = card.startedAt === null;
      const now = Date.now();

      return prev.map(d => {
        if (d.id === id) {
          if (willRun) {
            sendMessage({ id: d.id, current_time: nowTimeStr(), command: "resume" });
            return { ...d, startedAt: now };
          } else {
            const elapsed = getElapsedMs(d, now);
            if (d.subtype === "timer") {
              sendMessage({ id: d.id, remaining_time: fmtMs(Math.max(0, d.totalMs - elapsed)), command: "pause" });
            } else {
              sendMessage({ id: d.id, command: "pause" });
            }
            return { ...d, accumulatedMs: elapsed, startedAt: null };
          }
        }
        // Mutex: if starting a mutex card, pause other running mutex cards
        if (willRun && MUTEX_LABELS.includes(card.label) && MUTEX_LABELS.includes(d.label) && d.startedAt !== null) {
          const elapsed = getElapsedMs(d, now);
          sendMessage({ id: d.id, command: "pause" });
          return { ...d, accumulatedMs: elapsed, startedAt: null };
        }
        return d;
      });
    });
  }, []);

  // ── Delete duration ──
  const deleteDuration = useCallback((id: number) => {
    setDurations(prev => {
      const card = prev.find(d => d.id === id);
      if (card) {
        const elapsed = getElapsedMs(card, Date.now());
        const remaining = card.subtype === "timer" ? fmtMs(Math.max(0, card.totalMs - elapsed)) : undefined;
        sendMessage({ id, ...(remaining ? { remaining_time: remaining } : {}), command: "delete" });
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
    const t: Task = { id, label: "New Task", completed: false };
    setTasks(prev => [...prev, t]);
    setEditingTask(id);
    sendMessage({ id, type: "task", task: t.label, command: "create" });
  };

  const toggleTask = (id: number) => {
    setTasks(prev =>
      prev.map(t => {
        if (t.id !== id) return t;
        const completed = !t.completed;
        sendMessage({ id, type: "task", completed, command: "update" });
        return { ...t, completed };
      })
    );
  };

  const deleteTask = (id: number) => {
    setTasks(prev => prev.filter(t => t.id !== id));
    sendMessage({ id, type: "task", command: "delete" });
  };

  const updateTaskLabel = (id: number, label: string) => {
    setTasks(prev => prev.map(t => (t.id === id ? { ...t, label } : t)));
    sendMessage({ id, type: "task", task: label, command: "update" });
  };

  // ── Drag reorder tasks ──
  const onDragStart = (id: number) => { dragItem.current = id; };
  const onDragOver = (e: React.DragEvent, id: number) => { e.preventDefault(); setDragOver(id); };
  const onDrop = (targetId: number) => {
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

  // ── Open creation modal ──
  const openCreateModal = () => setModal({ ...defaultModal(), open: true });

  // ── Open edit modal for Duration card ──
  const openEditDuration = (card: DurationCard) => {
    const now = Date.now();
    const elapsed = getElapsedMs(card, now);
    const remaining = card.subtype === "timer" ? Math.max(0, card.totalMs - elapsed) : 0;

    // Parse elapsed into hh mm ss
    const es = Math.floor(elapsed / 1000);
    const ehh = String(Math.floor(es / 3600)).padStart(2, "0");
    const emm = String(Math.floor((es % 3600) / 60)).padStart(2, "0");
    const ess = String(es % 60).padStart(2, "0");

    // Parse total time (or remaining for timer)
    const rs = Math.floor((card.subtype === "timer" ? card.totalMs : elapsed) / 1000);
    const hh = String(Math.floor(rs / 3600)).padStart(2, "0");
    const mm = String(Math.floor((rs % 3600) / 60)).padStart(2, "0");
    const ss = String(rs % 60).padStart(2, "0");

    // Parse remaining into ring-style if needed
    const rem = Math.floor(remaining / 1000);
    const rhh = String(Math.floor(rem / 3600)).padStart(2, "0");
    const rmm = String(Math.floor((rem % 3600) / 60)).padStart(2, "0");

    setModal({
      open: true,
      editId: card.id,
      mode: "duration",
      subtype: card.subtype,
      timeMode: "total",
      label: card.label,
      hh, mm, ss,
      rhh, rmm, ampm: "AM",
      ehh, emm, ess,
    });
  };

  // ── Open edit modal for Event card ──
  const openEditEvent = (card: EventCard) => {
    const remaining = msUntil(card.ringTime);
    const rs = Math.floor(remaining / 1000);
    const hh = String(Math.floor(rs / 3600)).padStart(2, "0");
    const mm = String(Math.floor((rs % 3600) / 60)).padStart(2, "0");
    const ss = String(rs % 60).padStart(2, "0");
    const { hh: rhh, mm: rmm, ampm } = msToRingInputs(card.ringTime);

    setModal({
      open: true,
      editId: card.id,
      mode: "event",
      subtype: "timer",
      timeMode: "ring",
      label: card.label,
      hh, mm, ss,
      rhh, rmm, ampm,
      ehh: "00", emm: "00", ess: "00",
    });
  };

  // ── Close modal ──
  const closeModal = () => setModal(defaultModal());

  // ── Create or save card ──
  const saveCard = () => {
    const { editId, mode, subtype, timeMode, label, hh, mm, ss, rhh, rmm, ampm, ehh, emm, ess } = modal;
    const lbl = label.trim() || (mode === "event" ? "Event" : subtype === "stopwatch" ? "Stopwatch" : "Timer");
    const isEdit = editId !== null;

    if (mode === "duration") {
      if (subtype === "stopwatch") {
        const elapsedMs = parseHhMmSs(ehh, emm, ess);
        if (isEdit) {
          setDurations(prev => prev.map(d => d.id === editId
            ? { ...d, label: lbl, subtype: "stopwatch", totalMs: 0, accumulatedMs: elapsedMs }
            : d
          ));
          sendMessage({ id: editId, type: "duration", type_duration: "stopwatch", task: lbl, accumulated_ms: elapsedMs, current_time: nowTimeStr(), command: "edit" });
        } else {
          const id = genId();
          const card: DurationCard = { id, label: lbl, subtype: "stopwatch", totalMs: 0, accumulatedMs: elapsedMs, startedAt: null, alerting: false };
          setDurations(prev => [...prev, card]);
          sendMessage({ id, type: "duration", type_duration: "stopwatch", task: lbl, current_time: nowTimeStr(), command: "create" });
        }
      } else {
        // Timer
        let totalMs: number;
        if (timeMode === "ring") {
          totalMs = msUntil(parseRingTime(rhh, rmm, ampm));
        } else {
          totalMs = parseHhMmSs(hh, mm, ss);
        }
        if (totalMs <= 0) totalMs = 3600000;
        const elapsedMs = parseHhMmSs(ehh, emm, ess);
        const safeElapsed = Math.min(elapsedMs, totalMs);

        if (isEdit) {
          setDurations(prev => prev.map(d => d.id === editId
            ? { ...d, label: lbl, subtype: "timer", totalMs, accumulatedMs: safeElapsed, startedAt: d.startedAt }
            : d
          ));
          sendMessage({
            id: editId, type: "duration", type_duration: "timer", task: lbl,
            current_time: nowTimeStr(), total_time: fmtMs(totalMs),
            remaining_time: fmtMs(totalMs - safeElapsed),
            command: "edit",
          });
        } else {
          const id = genId();
          const card: DurationCard = { id, label: lbl, subtype: "timer", totalMs, accumulatedMs: 0, startedAt: null, alerting: false };
          setDurations(prev => [...prev, card]);
          sendMessage({ id, type: "duration", type_duration: "timer", task: lbl, current_time: nowTimeStr(), total_time: fmtMs(totalMs), command: "create" });
        }
      }
    } else {
      // Event
      let ringTime: Date;
      if (timeMode === "ring") {
        ringTime = parseRingTime(rhh, rmm, ampm);
      } else {
        const ms = parseHhMmSs(hh, mm, ss);
        ringTime = new Date(Date.now() + (ms || 3600000));
      }

      if (isEdit) {
        setEvents(prev => prev.map(e => e.id === editId ? { ...e, label: lbl, ringTime } : e));
        sendMessage({ id: editId, type: "event", task: lbl, ring_time: ringTime.toISOString(), command: "edit" });
      } else {
        const id = genId();
        setEvents(prev => [...prev, { id, label: lbl, ringTime, alerting: false }]);
        sendMessage({ id, type: "event", task: lbl, ring_time: ringTime.toISOString(), command: "create" });
      }
    }
    closeModal();
  };

  // ── Dismiss alerts ──
  const dismissEvent = (id: number) => setEvents(prev => prev.map(e => e.id === id ? { ...e, alerting: false } : e));
  const dismissDuration = (id: number) => setDurations(prev => prev.map(d => d.id === id ? { ...d, alerting: false } : d));

  // ── Date/time display ──
  const now = new Date(tick);
  const dateStr = now.toLocaleDateString("en-US", { month: "numeric", day: "numeric", year: "numeric" });
  const timeStr = now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });

  if (loading) {
    return (
      <div className="w-full h-screen flex items-center justify-center" style={{ fontFamily: "'Jockey One', sans-serif", background: "#080c18" }}>
        <span className="text-blue-300 text-xl">Loading…</span>
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
        className="flex items-center px-4 py-2"
        style={{ borderBottom: "1px solid rgba(61,110,234,0.25)", background: "#0a0e1e", minHeight: "48px", gap: "0" }}
      >
        <span className="text-base font-semibold tracking-wide text-blue-300 mr-auto">Productivity Dashboard</span>
        <span className="text-base text-blue-200 mr-3">{dateStr}</span>
        <span className="text-xl font-bold text-white mr-3">{timeStr}</span>
        <button
          onClick={() => sendMessage({ command: "close", current_time: nowTimeStr() })}
          className="w-9 h-9 rounded-full flex items-center justify-center text-white transition-opacity hover:opacity-80"
          style={{ background: "#e03555" }}
          title="Close & Save"
        >
          <X size={18} />
        </button>
      </header>

      {/* ── Body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Left area 75% ── */}
        <div className="flex flex-col overflow-hidden relative" style={{ width: "75%" }}>
          <div
            className="flex-1 overflow-y-auto px-4 py-3 space-y-3 pb-20"
            style={{ scrollbarWidth: "thin", scrollbarColor: "#1e3a6e transparent" }}
          >

            {/* Events */}
            <section>
              <h2 className="text-lg mb-2" style={{ color: "#c8d8f8", letterSpacing: "0.04em" }}>Events</h2>
              <div className="flex flex-wrap gap-3">
                {events.map(ev => {
                  const remaining = msUntil(ev.ringTime);
                  return (
                    <div
                      key={ev.id}
                      className="relative rounded-xl px-4 py-2 flex flex-col min-w-[148px]"
                      style={{
                        background: ev.alerting ? "#3a0a14" : "#0d1628",
                        border: ev.alerting ? "2px solid #e03555" : "1px solid rgba(61,110,234,0.3)",
                        boxShadow: "0 0 12px rgba(61,110,234,0.12)",
                        animation: ev.alerting ? "blink 0.8s step-start infinite" : undefined,
                      }}
                      onClick={() => ev.alerting && dismissEvent(ev.id)}
                    >
                      <div className="flex items-center justify-between mb-1 gap-2">
                        <span className="text-sm text-blue-200 truncate">{ev.label}</span>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            className="w-5 h-5 rounded-full flex items-center justify-center"
                            style={{ background: "#1e2a44" }}
                            onClick={e => { e.stopPropagation(); openEditEvent(ev); }}
                          >
                            <Pencil size={9} className="text-blue-300" />
                          </button>
                          <button
                            className="w-5 h-5 rounded-full flex items-center justify-center"
                            style={{ background: "#1e2a44" }}
                            onClick={e => { e.stopPropagation(); deleteEvent(ev.id); }}
                          >
                            <X size={9} className="text-blue-300" />
                          </button>
                        </div>
                      </div>
                      <span className="text-3xl font-bold tracking-wider text-white">
                        {ev.alerting ? "RING!" : fmtMs(remaining)}
                      </span>
                    </div>
                  );
                })}
                {events.length === 0 && (
                  <span className="text-sm" style={{ color: "#4a5f8a" }}>No events — press + to add one</span>
                )}
              </div>
            </section>

            {/* Divider */}
            <div style={{ height: "1px", background: "rgba(61,110,234,0.18)" }} />

            {/* Tasks Duration */}
            <section>
              <h2 className="text-lg mb-2" style={{ color: "#c8d8f8", letterSpacing: "0.04em" }}>Tasks Duration</h2>
              <div className="flex flex-wrap gap-3">
                {durations.map(d => {
                  const display = getDisplayMs(d, tick);
                  const isRunning = d.startedAt !== null;
                  return (
                    <div
                      key={d.id}
                      className="relative rounded-xl px-4 py-2 flex flex-col min-w-[160px]"
                      style={{
                        background: "#0d1628",
                        border: d.alerting ? "2px solid #e03555" : isRunning ? "1px solid rgba(61,110,234,0.7)" : "1px solid rgba(61,110,234,0.3)",
                        boxShadow: isRunning ? "0 0 16px rgba(61,110,234,0.25)" : "0 0 12px rgba(61,110,234,0.1)",
                        animation: d.alerting ? "blink 0.8s step-start infinite" : undefined,
                      }}
                      onClick={() => d.alerting && dismissDuration(d.id)}
                    >
                      <div className="flex items-center justify-between mb-1 gap-2">
                        <div className="flex items-center gap-1 min-w-0">
                          {d.subtype === "timer"
                            ? <CheckSquare size={13} className="text-blue-400 shrink-0" />
                            : <Clock size={13} className="text-blue-400 shrink-0" />
                          }
                          <span className="text-sm text-blue-200 truncate">{d.label}</span>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            className="w-5 h-5 rounded-full flex items-center justify-center"
                            style={{ background: "#1e2a44" }}
                            onClick={e => { e.stopPropagation(); openEditDuration(d); }}
                          >
                            <Pencil size={9} className="text-blue-300" />
                          </button>
                          <button
                            className="w-5 h-5 rounded-full flex items-center justify-center"
                            style={{ background: "#1e2a44" }}
                            onClick={e => { e.stopPropagation(); deleteDuration(d.id); }}
                          >
                            <X size={9} className="text-blue-300" />
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-3xl font-bold tracking-wider text-white">
                          {d.alerting ? "DONE!" : fmtMs(display)}
                        </span>
                        {!d.alerting && (
                          <button
                            className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
                            style={{ background: isRunning ? "#1a2d6e" : "#2250c4" }}
                            onClick={e => { e.stopPropagation(); toggleRunning(d.id); }}
                          >
                            {isRunning
                              ? <Pause size={16} fill="white" className="text-white" />
                              : <Play size={16} fill="white" className="text-white ml-0.5" />
                            }
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
                {durations.length === 0 && (
                  <span className="text-sm" style={{ color: "#4a5f8a" }}>No timers — press + to add one</span>
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
              className="w-14 h-14 rounded-full overflow-hidden"
              style={{ border: "2px solid rgba(61,110,234,0.6)", boxShadow: "0 0 14px rgba(61,110,234,0.3)" }}
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
                onDragOver={(e) => onDragOver(e, t.id)}
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
        <ModalOverlay onClose={closeModal}>
          <CreationModal modal={modal} setModal={setModal} onSave={saveCard} onClose={closeModal} />
        </ModalOverlay>
      )}

      <style>{`
        @keyframes blink {
          0%,100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}

// ─── Modal overlay ────────────────────────────────────────────────────────────
function ModalOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="absolute inset-0 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.72)", zIndex: 50 }}
      onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      {children}
    </div>
  );
}

// ─── Creation / Edit modal ────────────────────────────────────────────────────
function CreationModal({
  modal, setModal, onSave, onClose,
}: {
  modal: ModalState;
  setModal: React.Dispatch<React.SetStateAction<ModalState>>;
  onSave: () => void;
  onClose: () => void;
}) {
  const isEdit = modal.editId !== null;
  const set = <K extends keyof ModalState>(k: K, v: ModalState[K]) =>
    setModal(p => ({ ...p, [k]: v }));

  const showTimeInput = !(modal.mode === "duration" && modal.subtype === "stopwatch");
  const showElapsed = modal.subtype === "stopwatch" || (modal.mode === "duration" && modal.subtype === "timer");

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
      {/* Mode tabs + close */}
      <div className="flex items-center justify-between">
        <div className="flex rounded-xl overflow-hidden" style={{ border: "1px solid rgba(61,110,234,0.4)" }}>
          {(["duration", "event"] as ModalMode[]).map(m => (
            <button
              key={m}
              className="px-5 py-2 text-sm capitalize transition-colors"
              style={{ background: modal.mode === m ? "#2250c4" : "transparent", color: modal.mode === m ? "#fff" : "#6b7fa8" }}
              onClick={() => setModal(p => ({ ...p, mode: m, subtype: "timer", timeMode: m === "event" ? "ring" : "total" }))}
            >
              {m.charAt(0).toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>
        <button onClick={onClose} className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: "#1e2a44" }}>
          <X size={13} className="text-blue-300" />
        </button>
      </div>

      {/* Duration subtype */}
      {modal.mode === "duration" && (
        <div className="flex gap-3">
          {(["timer", "stopwatch"] as const).map(s => (
            <button
              key={s}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm"
              style={{
                background: modal.subtype === s ? "#2250c4" : "transparent",
                border: "1px solid rgba(61,110,234,0.4)",
                color: modal.subtype === s ? "#fff" : "#6b7fa8",
              }}
              onClick={() => set("subtype", s)}
            >
              {s === "timer" ? <CheckSquare size={13} /> : <Clock size={13} />}
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      )}

      {/* Timer time-mode toggle */}
      {modal.mode === "duration" && modal.subtype === "timer" && (
        <TimeModeToggle
          value={modal.timeMode}
          onChange={v => set("timeMode", v)}
          options={[{ value: "total", label: "Set total time" }, { value: "ring", label: "Set ring time" }]}
        />
      )}

      {/* Event time-mode toggle */}
      {modal.mode === "event" && (
        <TimeModeToggle
          value={modal.timeMode}
          onChange={v => set("timeMode", v)}
          options={[{ value: "ring", label: "Set ring time" }, { value: "total", label: "Set total time" }]}
        />
      )}

      {/* Label */}
      <div>
        <div className="text-sm mb-1" style={{ color: "#8aa0d0" }}>Label</div>
        <input
          className="w-full rounded-xl px-3 py-2 text-base text-white outline-none"
          style={{ background: "#162040", border: "1px solid rgba(61,110,234,0.3)", fontFamily: "'Jockey One', sans-serif" }}
          placeholder={modal.mode === "event" ? "Lunch 12pm" : modal.subtype === "stopwatch" ? "Work" : "AI Project"}
          value={modal.label}
          onChange={e => set("label", e.target.value)}
        />
      </div>

      {/* Main time input */}
      {showTimeInput && (
        <div>
          <div className="text-sm mb-2" style={{ color: "#8aa0d0" }}>
            {modal.timeMode === "ring" ? "Ring time" : "Duration"}
          </div>
          {modal.timeMode === "ring" ? (
            <div className="flex items-center gap-2">
              <TimeDigit value={modal.rhh} onChange={v => set("rhh", v)} max={12} />
              <Colon />
              <TimeDigit value={modal.rmm} onChange={v => set("rmm", v)} max={59} />
              <AmPmToggle value={modal.ampm} onChange={v => set("ampm", v)} />
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <TimeDigit value={modal.hh} onChange={v => set("hh", v)} max={23} />
              <Colon />
              <TimeDigit value={modal.mm} onChange={v => set("mm", v)} max={59} />
              <Colon />
              <TimeDigit value={modal.ss} onChange={v => set("ss", v)} max={59} />
            </div>
          )}
        </div>
      )}

      {/* Elapsed time (edit mode only) */}
      {isEdit && showElapsed && (
        <div>
          <div className="text-sm mb-2" style={{ color: "#8aa0d0" }}>
            {modal.subtype === "stopwatch" ? "Elapsed time" : "Elapsed (override)"}
          </div>
          <div className="flex items-center gap-2">
            <TimeDigit value={modal.ehh} onChange={v => set("ehh", v)} max={99} />
            <Colon />
            <TimeDigit value={modal.emm} onChange={v => set("emm", v)} max={59} />
            <Colon />
            <TimeDigit value={modal.ess} onChange={v => set("ess", v)} max={59} />
          </div>
        </div>
      )}

      {/* Save / Create button */}
      <button
        onClick={onSave}
        className="w-full py-3 rounded-xl text-lg font-bold text-white transition-opacity hover:opacity-90 active:opacity-80"
        style={{ background: "#2250c4" }}
      >
        {isEdit ? "Save Changes" : "Create"}
      </button>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function TimeModeToggle({
  value, onChange, options,
}: {
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

function TimeDigit({ value, onChange, max }: { value: string; onChange: (v: string) => void; max: number }) {
  return (
    <input
      className="text-center text-4xl font-bold text-white rounded-xl outline-none w-16"
      style={{ background: "#162040", border: "1px solid rgba(61,110,234,0.3)", fontFamily: "'Jockey One', sans-serif" }}
      value={value}
      onChange={e => {
        const raw = e.target.value.replace(/\D/g, "").slice(-2);
        const n = Math.min(parseInt(raw || "0", 10), max);
        onChange(String(n).padStart(2, "0"));
      }}
      maxLength={2}
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
          style={{
            background: value === ap ? "#2250c4" : "#162040",
            color: value === ap ? "#fff" : "#6b7fa8",
          }}
          onClick={() => onChange(ap)}
        >
          {ap}
        </button>
      ))}
    </div>
  );
}

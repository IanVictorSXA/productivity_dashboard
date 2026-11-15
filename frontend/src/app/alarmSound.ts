import { useEffect, useRef } from "react";
import alarmUrl from "@/assets/alarm.wav";

// The one place the alarm's Audio settings live. The dashboard (useAlarmSound
// below) and the `?test=alarm` dev page both call this, so the dev page
// proves exactly the playback path the dashboard uses.
export function createAlarmAudio(): HTMLAudioElement {
  const audio = new Audio(alarmUrl);
  audio.loop = true;
  return audio;
}

// One shared alarm loop for the whole dashboard (Phase 4 § Overlapping alarms).
// `ringing` is "at least one timer or event is alerting"; the effect only
// reacts when that flips, so a second alarm starting mid-ring neither restarts
// nor layers the sound, and the loop stops only when the last one is dismissed.
export function useAlarmSound(ringing: boolean): void {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!ringing) return;
    const audio = (audioRef.current ??= createAlarmAudio());
    // play() rejects if the browser blocks it, or with AbortError if we pause
    // before it starts; neither should surface as an unhandled rejection.
    audio.play().catch(err => console.warn("alarm sound not played:", err));
    return () => {
      audio.pause();
      audio.currentTime = 0; // next ring starts from the top, not mid-loop
    };
  }, [ringing]);
}

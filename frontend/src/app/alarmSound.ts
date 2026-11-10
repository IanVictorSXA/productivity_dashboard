import alarmUrl from "@/assets/alarm.wav";

// The one place the alarm's Audio settings live. The real alarm (Phase 4
// Group 3) and the `?test=alarm` dev page both call this, so the dev page
// proves exactly the playback path the dashboard will use.
export function createAlarmAudio(): HTMLAudioElement {
  const audio = new Audio(alarmUrl);
  audio.loop = true;
  return audio;
}

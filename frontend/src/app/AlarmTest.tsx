import { useEffect, useRef, useState } from "react";
import { createAlarmAudio } from "@/app/alarmSound";

const PLAY_MS = 5000;

// Dev-only page, reached at `/?test=alarm`. It tries to play the alarm on
// load with no tap first, which is the same situation as a real ring on a
// freshly booted kiosk, and shows whether the browser allowed it.
export default function AlarmTest() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopTimer = useRef<number | undefined>(undefined);
  const [status, setStatus] = useState("Not played yet");

  const stop = () => {
    window.clearTimeout(stopTimer.current);
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
  };

  const play = async () => {
    stop();
    audioRef.current ??= createAlarmAudio();
    try {
      await audioRef.current.play();
      setStatus(`Playing for ${PLAY_MS / 1000}s (loop on)`);
      stopTimer.current = window.setTimeout(() => {
        stop();
        setStatus("Finished — the browser allowed playback");
      }, PLAY_MS);
    } catch (err) {
      setStatus(`Blocked: ${(err as Error).name} — ${(err as Error).message}`);
    }
  };

  useEffect(() => {
    play();
    return stop;
  }, []);

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>Alarm sound test</h1>
      <p>{status}</p>
      <button onClick={play} style={{ padding: "12px 24px", fontSize: 18 }}>
        Play again
      </button>
    </div>
  );
}

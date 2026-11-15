  import { createRoot } from "react-dom/client";
  import App from "./app/App.tsx";
  import AlarmTest from "./app/AlarmTest.tsx";
  import "./styles/index.css";

  // `/?test=alarm` shows the sound test page instead of the dashboard.
  const isAlarmTest = new URLSearchParams(window.location.search).get("test") === "alarm";

  createRoot(document.getElementById("root")!).render(isAlarmTest ? <AlarmTest /> : <App />);

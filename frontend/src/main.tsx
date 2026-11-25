  import { createRoot } from "react-dom/client";
  import App from "./app/App.tsx";
  import AlarmTest from "./app/AlarmTest.tsx";
  import DragProbe from "./app/DragProbe.tsx";
  import "./styles/index.css";

  // `/?test=alarm` and `/?test=drag` show dev test pages instead of the dashboard.
  const testPage = new URLSearchParams(window.location.search).get("test");

  createRoot(document.getElementById("root")!).render(
    testPage === "alarm" ? <AlarmTest /> : testPage === "drag" ? <DragProbe /> : <App />,
  );

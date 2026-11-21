import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ActiveTopologyProvider } from "./state/activeTopology";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ActiveTopologyProvider>
        <App />
      </ActiveTopologyProvider>
    </BrowserRouter>
  </StrictMode>,
);

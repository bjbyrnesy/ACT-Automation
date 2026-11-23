import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ActiveTopologyProvider } from "./state/activeTopology";
import { CreateWizardProvider } from "./state/createWizard";
import { ThemeProvider } from "./theme/ThemeProvider";
import { applyTheme, readStoredThemeId } from "./theme/themes";
import "./index.css";

applyTheme(readStoredThemeId());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <ActiveTopologyProvider>
          <CreateWizardProvider>
            <App />
          </CreateWizardProvider>
        </ActiveTopologyProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);

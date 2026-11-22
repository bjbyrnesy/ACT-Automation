import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { LabWorkspace } from "./layout/LabWorkspace";
import { AttachPage } from "./pages/AttachPage";
import { CreatePage } from "./pages/CreatePage";
import { DeployPage } from "./pages/DeployPage";
import { ExtendPage } from "./pages/ExtendPage";
import { LibraryPage } from "./pages/LibraryPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LibraryPage />} />
        <Route path="new" element={<CreatePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="labs/:labId" element={<LabWorkspace />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="grow" element={<ExtendPage />} />
          <Route path="hosts" element={<AttachPage />} />
          <Route path="deploy" element={<DeployPage />} />
        </Route>
        <Route path="labs" element={<Navigate to="/" replace />} />
        <Route path="create" element={<Navigate to="/new" replace />} />
        <Route path="show" element={<Navigate to="/" replace />} />
        <Route path="extend" element={<Navigate to="/" replace />} />
        <Route path="attach" element={<Navigate to="/" replace />} />
        <Route path="clab" element={<Navigate to="/" replace />} />
        <Route path="act" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

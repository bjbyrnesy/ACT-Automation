import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { ActPage } from "./pages/ActPage";
import { AttachPage } from "./pages/AttachPage";
import { ClabPage } from "./pages/ClabPage";
import { CreatePage } from "./pages/CreatePage";
import { ExtendPage } from "./pages/ExtendPage";
import { LabsPage } from "./pages/LabsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ShowPage } from "./pages/ShowPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/labs" replace />} />
        <Route path="labs" element={<LabsPage />} />
        <Route path="create" element={<CreatePage />} />
        <Route path="extend" element={<ExtendPage />} />
        <Route path="clab" element={<ClabPage />} />
        <Route path="act" element={<ActPage />} />
        <Route path="attach" element={<AttachPage />} />
        <Route path="show" element={<ShowPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

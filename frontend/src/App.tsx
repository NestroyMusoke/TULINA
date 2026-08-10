import { Navigate, Route, Routes } from "react-router-dom";

import { Shell } from "./components/Shell";
import { AuditPage } from "./pages/AuditPage";
import { DistrictPage } from "./pages/DistrictPage";
import { FacilityPage } from "./pages/FacilityPage";
import { JudgePage } from "./pages/JudgePage";
import { NetworkPage } from "./pages/NetworkPage";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/judge" replace />} />
        <Route path="judge" element={<JudgePage />} />
        <Route path="district" element={<DistrictPage />} />
        <Route path="network" element={<NetworkPage />} />
        <Route path="facility" element={<FacilityPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/judge" replace />} />
      </Route>
    </Routes>
  );
}

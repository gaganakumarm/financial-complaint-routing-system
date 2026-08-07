import { Navigate, Outlet, useLocation } from "react-router-dom";
import { LoadingState } from "../../components/common/States";
import { useAuth } from "./useAuth";

export function ProtectedRoute() {
  const { user, isRestoring } = useAuth();
  const location = useLocation();
  if (isRestoring) return <LoadingState label="Restoring your session" fullScreen />;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return <Outlet />;
}

import { AccessDenied } from "../../../components/common/States";
import { useAuth } from "../../auth/useAuth";
import { PlaceholderPage } from "../../../pages/PlaceholderPage";
import { MyComplaintsPage } from "./MyComplaintsPage";

export function ComplaintsIndexPage() {
  const { user } = useAuth();
  if (user?.role_name === "customer") return <MyComplaintsPage />;
  if (user?.role_name === "reviewer") return <PlaceholderPage title="Complaints" />;
  return <AccessDenied />;
}

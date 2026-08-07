import { EmptyState } from "../components/common/States";

export function PlaceholderPage({ title }: { title: string }) {
  return <section><h2 className="mb-5 text-xl font-semibold">{title}</h2><EmptyState title={`${title} is coming next`} message="This foundation includes navigation only; business functionality has not been implemented." /></section>;
}

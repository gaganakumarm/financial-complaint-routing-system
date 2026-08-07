import { Link, useNavigate } from "react-router-dom";
import { ComplaintForm } from "../components/ComplaintForm";
import { useCreateComplaint } from "../hooks";
import type { ComplaintFormValues } from "../schemas";

export function CreateComplaintPage() {
  const mutation = useCreateComplaint();
  const navigate = useNavigate();
  const submit = async (values: ComplaintFormValues) => {
    const complaint = await mutation.mutateAsync(values);
    navigate(`/complaints/${complaint.id}`, { replace: true });
  };
  return <section className="max-w-3xl"><Link to="/complaints" className="text-sm font-semibold text-teal-700 hover:underline dark:text-teal-400">← Back to complaints</Link><div className="mt-5 rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-8"><h2 className="text-xl font-semibold">Create complaint</h2><p className="mt-1 text-sm text-slate-600 dark:text-slate-400">Provide a clear summary of the financial issue you experienced.</p><div className="mt-7"><ComplaintForm onSubmit={submit} isPending={mutation.isPending} serverError={mutation.error} /></div></div></section>;
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { Button } from "../../../components/ui/Button";
import { getApiErrorMessage } from "../../../lib/api";
import { complaintFormSchema, type ComplaintFormValues } from "../schemas";

const fieldClass = "mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm shadow-sm dark:border-slate-700 dark:bg-slate-950";

export function ComplaintForm({ onSubmit, serverError, isPending }: { onSubmit: (values: ComplaintFormValues) => Promise<void>; serverError?: unknown; isPending: boolean }) {
  const { register, handleSubmit, formState: { errors } } = useForm<ComplaintFormValues>({ resolver: zodResolver(complaintFormSchema), defaultValues: { title: "", description: "" } });
  return <form className="space-y-6" noValidate onSubmit={handleSubmit(onSubmit)}>
    {serverError !== undefined && <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">{getApiErrorMessage(serverError, "Unable to create the complaint. Please try again.")}</div>}
    <div><label htmlFor="title" className="text-sm font-medium">Title</label><input id="title" maxLength={200} className={fieldClass} aria-invalid={Boolean(errors.title)} {...register("title")} />{errors.title && <p className="mt-1 text-sm text-red-700">{errors.title.message}</p>}</div>
    <div><label htmlFor="description" className="text-sm font-medium">Description</label><p className="mt-1 text-sm text-slate-500">Describe the issue and include relevant dates or transaction context. Do not include passwords or PINs.</p><textarea id="description" rows={8} maxLength={10_000} className={fieldClass} aria-invalid={Boolean(errors.description)} {...register("description")} />{errors.description && <p className="mt-1 text-sm text-red-700">{errors.description.message}</p>}</div>
    <div className="flex items-center gap-3"><Button type="submit" disabled={isPending}>{isPending ? "Submitting…" : "Submit complaint"}</Button><Link to="/complaints" className="rounded-md px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">Cancel</Link></div>
  </form>;
}

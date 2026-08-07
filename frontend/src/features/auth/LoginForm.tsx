import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { getApiErrorMessage } from "../../lib/api";
import { loginSchema, type LoginFormValues } from "./schema";
import { useAuth } from "./useAuth";

const fieldClass = "mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-teal-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

export function LoginForm() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string>();
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  const submit = async (values: LoginFormValues) => {
    setServerError(undefined);
    try {
      await login(values);
      navigate("/", { replace: true });
    } catch (error) {
      setServerError(getApiErrorMessage(error, "Unable to sign in. Check your credentials and try again."));
    }
  };

  return <form className="space-y-5" onSubmit={handleSubmit(submit)} noValidate>
    {serverError && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">{serverError}</div>}
    <div><label className="text-sm font-medium" htmlFor="email">Email address</label><input id="email" type="email" autoComplete="username" className={fieldClass} aria-invalid={Boolean(errors.email)} {...register("email")} />{errors.email && <p className="mt-1 text-sm text-red-700">{errors.email.message}</p>}</div>
    <div><label className="text-sm font-medium" htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" className={fieldClass} aria-invalid={Boolean(errors.password)} {...register("password")} />{errors.password && <p className="mt-1 text-sm text-red-700">{errors.password.message}</p>}</div>
    <Button className="w-full" disabled={isSubmitting} type="submit">{isSubmitting ? "Signing in…" : "Sign in"}</Button>
  </form>;
}

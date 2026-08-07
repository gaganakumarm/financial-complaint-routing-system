import { z } from "zod";

export const complaintFormSchema = z.object({
  title: z.string().trim().min(1, "Title is required.").max(200, "Title must be 200 characters or fewer."),
  description: z.string().trim().min(1, "Description is required.").max(10_000, "Description must be 10,000 characters or fewer."),
});

export type ComplaintFormValues = z.infer<typeof complaintFormSchema>;

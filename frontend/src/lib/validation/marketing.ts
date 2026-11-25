// Client-side validation for the public marketing forms.
// There is no public submission backend in V1, so these schemas power
// inline field validation only — nothing is ever transmitted anywhere.

import { z } from "zod";

const REQUIRED_MESSAGE = "This field is required";
const EMAIL_MESSAGE = "Enter a valid email";
const email = z
  .string()
  .trim()
  .min(1, REQUIRED_MESSAGE)
  .check(z.email({ error: EMAIL_MESSAGE }));

export const contactFormSchema = z.object({
  fullName: z.string().trim().min(1, REQUIRED_MESSAGE),
  businessEmail: email,
  companyName: z.string().trim().min(1, REQUIRED_MESSAGE),
  inquiryType: z.string().trim().min(1, REQUIRED_MESSAGE),
  message: z.string().trim().min(1, REQUIRED_MESSAGE),
});

export const demoFormSchema = z.object({
  name: z.string().trim().min(1, REQUIRED_MESSAGE),
  workEmail: email,
  company: z.string().trim().min(1, REQUIRED_MESSAGE),
  teamSize: z.string().trim().min(1, REQUIRED_MESSAGE),
  useCase: z.string().trim().min(1, REQUIRED_MESSAGE),
  challenge: z.string().trim().min(1, REQUIRED_MESSAGE),
  contactWindow: z
    .string()
    .trim()
    .optional()
    .transform((value) => (value ? value : undefined)),
});

export type ContactFormValues = z.infer<typeof contactFormSchema>;
export type DemoFormValues = z.infer<typeof demoFormSchema>;

export type FormErrors = Record<string, string | undefined>;

export function validateForm(schema: z.ZodType, values: unknown): FormErrors {
  const result = schema.safeParse(values);
  if (result.success) return {};
  const errors: FormErrors = {};
  for (const issue of result.error.issues) {
    const key = String(issue.path[0] ?? "");
    if (!(key in errors)) errors[key] = issue.message;
  }
  return errors;
}

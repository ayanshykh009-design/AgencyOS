// Contact page (Sheet 2A screen 02): inquiry form and "other ways to
// reach us" panel. There is no safe public submission backend in V1, so
// the form validates locally but never transmits data anywhere; the
// submit control stays disabled and no success state is ever shown.
"use client";

import { useState } from "react";

import { Field, SelectInput, TextAreaInput, TextInput } from "@/components/marketing/form-fields";
import { UnavailableNote } from "@/components/marketing/unavailable-note";
import {
  CONTACT_HEADLINE,
  CONTACT_INQUIRY_TYPES,
  CONTACT_INTRO_LINES,
  CONTACT_REACH_ITEMS,
} from "@/lib/marketing";
import { contactFormSchema, validateForm, type FormErrors } from "@/lib/validation/marketing";

const REACH_ICONS: Record<(typeof CONTACT_REACH_ITEMS)[number]["icon"], React.ReactNode> = {
  mail: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1.5" y="3" width="13" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
      <path d="m2 4 6 5 6-5" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  ),
  clock: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.2" />
      <path d="M8 4.5V8l2.5 1.5" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  ),
  social: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M2 8a6 6 0 0 1 12 0 6 6 0 0 1-12 0Z" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="M2.5 6.5h11M2.5 9.5h11M8 2a10 10 0 0 0 0 12M8 2a10 10 0 0 1 0 12"
        stroke="currentColor"
        strokeWidth="1"
      />
    </svg>
  ),
};

export default function ContactPage() {
  const [values, setValues] = useState({
    fullName: "",
    businessEmail: "",
    companyName: "",
    inquiryType: CONTACT_INQUIRY_TYPES[0],
    message: "",
  });
  const [errors, setErrors] = useState<FormErrors>({});

  function setField(field: keyof typeof values) {
    return (value: string) => {
      setValues((current) => ({ ...current, [field]: value }));
      // Clear the field-level error as soon as the visitor edits the field.
      if (errors[field]) {
        setErrors((current) => ({ ...current, [field]: undefined }));
      }
    };
  }

  // Inline validation only. Nothing is submitted: no public backend
  // exists, the /webhooks/leads shared secret must never reach the
  // browser, and success states must never be faked.
  function handleBlur(field: keyof typeof values) {
    return () => {
      const fieldErrors = validateForm(contactFormSchema, values);
      setErrors((current) => ({ ...current, [field]: fieldErrors[field] }));
    };
  }

  return (
    <div className="mx-auto max-w-6xl px-4 pb-20 pt-14 sm:px-6">
      <header className="max-w-2xl">
        <h1 className="font-display text-4xl font-semibold tracking-tight text-off-white sm:text-5xl">
          {CONTACT_HEADLINE}
        </h1>
        {CONTACT_INTRO_LINES.map((line) => (
          <p key={line} className="mt-3 text-sm text-soft-gray">
            {line}
          </p>
        ))}
      </header>

      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_320px]">
        {/* Form card */}
        <section
          aria-labelledby="contact-form-heading"
          className="rounded-xl border border-line bg-graphite p-6 sm:p-8"
        >
          <h2 id="contact-form-heading" className="sr-only">
            Contact form
          </h2>
          <form noValidate onSubmit={(event) => event.preventDefault()}>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Full name" id="contact-name" error={errors.fullName}>
                <TextInput
                  id="contact-name"
                  name="fullName"
                  autoComplete="name"
                  value={values.fullName}
                  onChange={(event) => setField("fullName")(event.target.value)}
                  onBlur={handleBlur("fullName")}
                  invalid={Boolean(errors.fullName)}
                  placeholder="Full name"
                />
              </Field>

              <Field label="Business email" id="contact-email" error={errors.businessEmail}>
                <TextInput
                  id="contact-email"
                  name="businessEmail"
                  type="email"
                  autoComplete="email"
                  value={values.businessEmail}
                  onChange={(event) => setField("businessEmail")(event.target.value)}
                  onBlur={handleBlur("businessEmail")}
                  invalid={Boolean(errors.businessEmail)}
                  placeholder="Business email"
                />
              </Field>

              <Field label="Company name" id="contact-company" error={errors.companyName}>
                <TextInput
                  id="contact-company"
                  name="companyName"
                  autoComplete="organization"
                  value={values.companyName}
                  onChange={(event) => setField("companyName")(event.target.value)}
                  onBlur={handleBlur("companyName")}
                  invalid={Boolean(errors.companyName)}
                  placeholder="Company name"
                />
              </Field>

              <Field label="Inquiry type" id="contact-inquiry" error={errors.inquiryType}>
                <SelectInput
                  id="contact-inquiry"
                  name="inquiryType"
                  value={values.inquiryType}
                  onChange={(event) => setField("inquiryType")(event.target.value)}
                >
                  {CONTACT_INQUIRY_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </SelectInput>
              </Field>

              <Field
                label="Message"
                id="contact-message"
                error={errors.message}
                className="sm:col-span-2"
              >
                <TextAreaInput
                  id="contact-message"
                  name="message"
                  value={values.message}
                  onChange={(event) => setField("message")(event.target.value)}
                  onBlur={handleBlur("message")}
                  invalid={Boolean(errors.message)}
                  placeholder="Tell us about your business and what you want AgencyOS to run…"
                />
              </Field>
            </div>

            <div className="mt-6 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <button
                type="button"
                disabled
                aria-disabled="true"
                className="rounded-lg bg-off-white px-5 py-2.5 text-sm font-medium text-obsidian opacity-50"
              >
                Send message
              </button>
              <UnavailableNote className="sm:ml-2 sm:flex-1">
                Submission is unavailable: no public backend yet.
              </UnavailableNote>
            </div>
          </form>
        </section>

        {/* Other ways to reach us */}
        <aside
          aria-labelledby="contact-reach-heading"
          className="rounded-xl border border-line bg-graphite p-6"
        >
          <h2
            id="contact-reach-heading"
            className="font-display text-base font-semibold text-off-white"
          >
            Other ways to reach us
          </h2>
          <ul className="mt-4 flex flex-col gap-4">
            {CONTACT_REACH_ITEMS.map((item) => (
              <li key={item.label} className="flex items-start gap-3">
                <span className="mt-0.5 text-muted">{REACH_ICONS[item.icon]}</span>
                <div>
                  <p className="text-sm text-soft-gray">{item.label}:</p>
                  <p className="text-sm text-muted">{item.value}</p>
                </div>
              </li>
            ))}
          </ul>
          <UnavailableNote className="mt-6">
            Contact details are owner-supplied and will be published once confirmed.
          </UnavailableNote>
        </aside>
      </div>
    </div>
  );
}

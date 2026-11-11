// Demo request page (Sheet 2A screen 03): walkthrough request form,
// small decorative Core Orbit and "What happens next" steps.
// There is no demo-request backend in V1, so the form validates locally
// and the submit control stays disabled — nothing is transmitted and no
// success state is ever shown. No calendar booking is implied.
"use client";

import { useState } from "react";

import { CoreOrbit } from "@/components/marketing/core-orbit";
import { Field, SelectInput, TextAreaInput, TextInput } from "@/components/marketing/form-fields";
import { UnavailableNote } from "@/components/marketing/unavailable-note";
import {
  DEMO_CONTACT_WINDOWS,
  DEMO_HEADLINE,
  DEMO_INTRO,
  DEMO_NEXT_STEPS,
  DEMO_TEAM_SIZES,
  DEMO_USE_CASES,
} from "@/lib/marketing";
import { demoFormSchema, validateForm, type FormErrors } from "@/lib/validation/marketing";

export default function DemoPage() {
  const [values, setValues] = useState({
    name: "",
    workEmail: "",
    company: "",
    teamSize: DEMO_TEAM_SIZES[1],
    useCase: DEMO_USE_CASES[0],
    challenge: "",
    contactWindow: DEMO_CONTACT_WINDOWS[0],
  });
  const [errors, setErrors] = useState<FormErrors>({});

  function setField(field: keyof typeof values) {
    return (value: string) => {
      setValues((current) => ({ ...current, [field]: value }));
      if (errors[field]) {
        setErrors((current) => ({ ...current, [field]: undefined }));
      }
    };
  }

  function handleBlur(field: keyof typeof values) {
    return () => {
      const fieldErrors = validateForm(demoFormSchema, values);
      setErrors((current) => ({ ...current, [field]: fieldErrors[field] }));
    };
  }

  return (
    <div className="mx-auto max-w-6xl px-4 pb-20 pt-14 sm:px-6">
      <header className="max-w-2xl">
        <h1 className="font-display text-4xl font-semibold tracking-tight text-off-white sm:text-5xl">
          {DEMO_HEADLINE}
        </h1>
        <p className="mt-3 text-sm text-soft-gray">{DEMO_INTRO}</p>
      </header>

      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_300px]">
        {/* Form card */}
        <section aria-labelledby="demo-form-heading" className="rounded-xl border border-line bg-graphite p-6 sm:p-8">
          <h2 id="demo-form-heading" className="sr-only">
            Demo request form
          </h2>
          <form noValidate onSubmit={(event) => event.preventDefault()}>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Name" id="demo-name" error={errors.name}>
                <TextInput
                  id="demo-name"
                  name="name"
                  autoComplete="name"
                  value={values.name}
                  onChange={(event) => setField("name")(event.target.value)}
                  onBlur={handleBlur("name")}
                  invalid={Boolean(errors.name)}
                  placeholder="Name"
                />
              </Field>

              <Field label="Work email" id="demo-email" error={errors.workEmail}>
                <TextInput
                  id="demo-email"
                  name="workEmail"
                  type="email"
                  autoComplete="email"
                  value={values.workEmail}
                  onChange={(event) => setField("workEmail")(event.target.value)}
                  onBlur={handleBlur("workEmail")}
                  invalid={Boolean(errors.workEmail)}
                  placeholder="Work email"
                />
              </Field>

              <Field label="Company" id="demo-company" error={errors.company}>
                <TextInput
                  id="demo-company"
                  name="company"
                  autoComplete="organization"
                  value={values.company}
                  onChange={(event) => setField("company")(event.target.value)}
                  onBlur={handleBlur("company")}
                  invalid={Boolean(errors.company)}
                  placeholder="Company"
                />
              </Field>

              <Field label="Team size" id="demo-team-size" error={errors.teamSize}>
                <SelectInput
                  id="demo-team-size"
                  name="teamSize"
                  value={values.teamSize}
                  onChange={(event) => setField("teamSize")(event.target.value)}
                >
                  {DEMO_TEAM_SIZES.map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </SelectInput>
              </Field>

              <Field label="Main use case" id="demo-use-case" error={errors.useCase} className="sm:col-span-2">
                <SelectInput
                  id="demo-use-case"
                  name="useCase"
                  value={values.useCase}
                  onChange={(event) => setField("useCase")(event.target.value)}
                >
                  {DEMO_USE_CASES.map((useCase) => (
                    <option key={useCase} value={useCase}>
                      {useCase}
                    </option>
                  ))}
                </SelectInput>
              </Field>

              <Field label="Current business challenge" id="demo-challenge" error={errors.challenge} className="sm:col-span-2">
                <TextAreaInput
                  id="demo-challenge"
                  name="challenge"
                  value={values.challenge}
                  onChange={(event) => setField("challenge")(event.target.value)}
                  onBlur={handleBlur("challenge")}
                  invalid={Boolean(errors.challenge)}
                  placeholder="What is slowing your team down today?"
                />
              </Field>

              <Field
                label="Preferred contact window (optional)"
                id="demo-window"
                className="sm:col-span-2"
              >
                <SelectInput
                  id="demo-window"
                  name="contactWindow"
                  value={values.contactWindow}
                  onChange={(event) => setField("contactWindow")(event.target.value)}
                >
                  {DEMO_CONTACT_WINDOWS.map((window) => (
                    <option key={window} value={window}>
                      {window}
                    </option>
                  ))}
                </SelectInput>
              </Field>
            </div>

            <div className="mt-6 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <button
                type="button"
                disabled
                aria-disabled="true"
                className="rounded-lg bg-off-white px-5 py-2.5 text-sm font-medium text-obsidian opacity-50"
              >
                Request demo
              </button>
              <UnavailableNote className="sm:ml-2 sm:flex-1">
                Submission is unavailable: no public backend yet.
              </UnavailableNote>
            </div>
          </form>
        </section>

        {/* Decorative Core Orbit + what happens next */}
        <aside className="flex flex-col gap-6">
          <div className="flex items-center justify-center pt-6" aria-hidden="true">
            <CoreOrbit size={220} />
          </div>

          <section aria-labelledby="demo-next-heading" className="rounded-xl border border-line bg-graphite p-6">
            <h2 id="demo-next-heading" className="font-display text-base font-semibold text-off-white">
              What happens next
            </h2>
            <ol className="mt-4 flex flex-col gap-3">
              {DEMO_NEXT_STEPS.map((step, index) => (
                <li key={step} className="flex items-start gap-3">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-line bg-elevated text-[11px] text-soft-gray">
                    {index + 1}
                  </span>
                  <span className="text-sm text-soft-gray">{step}</span>
                </li>
              ))}
            </ol>
          </section>

          <UnavailableNote>No calendar booking or sales routing is implied.</UnavailableNote>
        </aside>
      </div>
    </div>
  );
}

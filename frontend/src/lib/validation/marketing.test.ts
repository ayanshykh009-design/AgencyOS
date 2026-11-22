// Validation schema tests for the public marketing forms.
import { describe, expect, it } from "vitest";

import { contactFormSchema, demoFormSchema, validateForm } from "@/lib/validation/marketing";

const VALID_CONTACT = {
  fullName: "Ayesha Khan",
  businessEmail: "ayesha@northwind.example",
  companyName: "Northwind Studio",
  inquiryType: "Sales question",
  message: "We want to centralize leads and automate follow-ups.",
};

const VALID_DEMO = {
  name: "Ayesha Khan",
  workEmail: "ayesha@northwind.example",
  company: "Northwind Studio",
  teamSize: "11 – 50",
  useCase: "Lead management and follow-up automation",
  challenge: "Leads are spread across spreadsheets and inboxes.",
  contactWindow: "Weekday mornings",
};

describe("contactFormSchema", () => {
  it("accepts the designed happy path", () => {
    expect(validateForm(contactFormSchema, VALID_CONTACT)).toEqual({});
  });

  it("rejects an invalid business email", () => {
    const errors = validateForm(contactFormSchema, {
      ...VALID_CONTACT,
      businessEmail: "bad@",
    });
    expect(errors.businessEmail).toBe("Enter a valid email");
  });

  it("rejects blank required fields", () => {
    const errors = validateForm(contactFormSchema, {
      fullName: "   ",
      businessEmail: "",
      companyName: "",
      inquiryType: "",
      message: "",
    });
    expect(errors.fullName).toBe("This field is required");
    for (const key of ["businessEmail", "companyName", "inquiryType", "message"]) {
      expect(errors[key]).toBeDefined();
    }
  });
});

describe("demoFormSchema", () => {
  it("accepts the designed happy path", () => {
    expect(validateForm(demoFormSchema, VALID_DEMO)).toEqual({});
  });

  it("treats the preferred contact window as optional", () => {
    const errors = validateForm(demoFormSchema, { ...VALID_DEMO, contactWindow: "" });
    expect(errors).toEqual({});
  });

  it("rejects an invalid work email", () => {
    const errors = validateForm(demoFormSchema, { ...VALID_DEMO, workEmail: "nope" });
    expect(errors.workEmail).toBe("Enter a valid email");
  });

  it("rejects blank required fields", () => {
    const errors = validateForm(demoFormSchema, {
      name: "",
      workEmail: "",
      company: "",
      teamSize: "",
      useCase: "",
      challenge: "",
      contactWindow: undefined,
    });
    for (const key of ["name", "workEmail", "company", "teamSize", "useCase", "challenge"]) {
      expect(errors[key]).toBeDefined();
    }
    expect(errors.contactWindow).toBeUndefined();
  });
});

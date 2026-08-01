-- lead_status: lifecycle stage of a lead inside an organization.
CREATE TYPE public.lead_status AS ENUM (
  'new',
  'researching',
  'contacted',
  'meeting_booked',
  'proposal_sent',
  'won',
  'lost'
);

-- outreach_status: lifecycle of a single outreach message / follow-up.
CREATE TYPE public.outreach_status AS ENUM (
  'queued',
  'sending',
  'sent',
  'delivered',
  'failed',
  'skipped',
  'manually_sent',
  'replied'
);

-- import_status: lifecycle of a CSV import job.
CREATE TYPE public.import_status AS ENUM (
  'pending',
  'processing',
  'completed',
  'failed',
  'cancelled'
);

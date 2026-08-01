-- outreach_channel: which channel an outreach message/attempt uses.
CREATE TYPE public.outreach_channel AS ENUM (
  'email',
  'whatsapp',
  'contact_form',
  'linkedin',
  'instagram',
  'facebook'
);

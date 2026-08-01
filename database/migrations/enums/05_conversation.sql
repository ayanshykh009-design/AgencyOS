-- conversation_sender: who authored a conversation message.
CREATE TYPE public.conversation_sender AS ENUM (
  'lead',
  'agent',
  'system'
);

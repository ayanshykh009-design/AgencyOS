-- system_settings: operator-controlled key/value settings (global, Phase 5C)
CREATE TABLE IF NOT EXISTS public.system_settings (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key                text NOT NULL UNIQUE CHECK (length(btrim(key)) > 0),
  value              jsonb NOT NULL DEFAULT '{}',
  updated_by_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_system_settings_updated_at
  BEFORE UPDATE ON public.system_settings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

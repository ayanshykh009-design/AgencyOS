// AI settings: per-org LLM provider/model overrides (stored in organizations.settings).
"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { can } from "@/lib/permissions";
import { getAISettings, updateAISettings } from "@/services/ai";
import type { OrganizationAISettings } from "@/types";

const PROVIDERS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Google Gemini" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "ollama", label: "Ollama (local)" },
  { value: "openai-compatible", label: "OpenAI-compatible" },
];

export default function AISettingsPage() {
  const session = useAuth();
  const [settings, setSettings] = useState<OrganizationAISettings | null>(null);
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canManage = !!session && can(session.user.role, "ai_manage");

  useEffect(() => {
    if (!canManage) return;
    let cancelled = false;
    getAISettings()
      .then((aiSettings) => {
        if (cancelled) return;
        setSettings(aiSettings);
        setProvider(aiSettings.provider);
        setModel(aiSettings.model);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.message : "Failed to load AI settings");
      });
    return () => {
      cancelled = true;
    };
  }, [canManage, session]);

  async function onSave() {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await updateAISettings({
        provider,
        model: model.trim() || undefined,
      });
      setSettings(updated);
      setProvider(updated.provider);
      setModel(updated.model);
      setMessage("AI settings saved.");
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to save AI settings");
    } finally {
      setBusy(false);
    }
  }

  async function onReset() {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await updateAISettings({});
      setSettings(updated);
      setProvider(updated.provider);
      setModel(updated.model);
      setMessage("Cleared org override — using defaults.");
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to reset AI settings");
    } finally {
      setBusy(false);
    }
  }

  if (!canManage) {
    return <p>You do not have permission to manage AI settings. Contact an administrator.</p>;
  }

  return (
    <div className="flex max-w-xl flex-col gap-8">
      <section>
        <h2 className="text-lg font-semibold">AI settings</h2>
        <p className="mt-1 text-sm text-gray-500">
          Per-organization LLM defaults. Leave blank to fall back to the global configuration.
        </p>

        <div className="mt-4 flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-gray-600">Provider</span>
            <select
              className="rounded-md border px-3 py-2"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              {PROVIDERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-gray-600">Default model</span>
            <input
              className="rounded-md border px-3 py-2"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={settings && !settings.overridden ? "e.g. gpt-4o-mini" : ""}
            />
          </label>

          <div className="flex items-center gap-3">
            <Button onClick={onSave} disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
            <Button onClick={onReset} disabled={busy} variant="ghost">
              Clear override
            </Button>
          </div>
        </div>

        {message ? <p className="mt-3 text-sm text-green-700">{message}</p> : null}
        {error ? <p className="mt-3 text-red-600">{error}</p> : null}
      </section>
    </div>
  );
}

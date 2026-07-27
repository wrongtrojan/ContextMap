"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { fetchSettings, saveSettings } from "../../lib/api/settings";
import {
  formToSettingsChanges,
  settingsDataToForm,
  settingsInputClass,
  type SettingsFormState,
} from "../../lib/settingsForm";

interface SettingsPaneProps {
  active: boolean;
  onSaved?: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-[11px] font-mono uppercase tracking-widest text-dracula-purple border-b border-dracula-comment/20 pb-1">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-[10px] font-mono uppercase tracking-widest text-dracula-comment">{label}</span>
      {children}
    </label>
  );
}

export default function SettingsPane({ active, onSaved }: SettingsPaneProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [configured, setConfigured] = useState(false);
  const [keyHint, setKeyHint] = useState<string | null>(null);
  const [form, setForm] = useState<SettingsFormState | null>(null);
  const [baseline, setBaseline] = useState<SettingsFormState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSettings();
      const next = settingsDataToForm(data);
      setForm(next);
      setBaseline(next);
      setConfigured(Boolean(data.llm.configured));
      setKeyHint(data.llm.hint ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "无法加载设置，请确认后端已启动");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (active) void load();
  }, [active, load]);

  const update = <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSuccess(null);
  };

  const handleSave = async () => {
    if (!form || !baseline) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const changes = formToSettingsChanges(form, baseline);
      const deepseek_api_key = form.deepseekApiKey.trim() || undefined;
      if (Object.keys(changes).length === 0 && !deepseek_api_key) {
        setError("没有可保存的变更");
        return;
      }
      const res = await saveSettings({ changes, deepseek_api_key });
      const next = settingsDataToForm(res.data);
      setForm({ ...next, deepseekApiKey: "" });
      setBaseline(next);
      setConfigured(Boolean(res.data.llm.configured));
      setKeyHint(res.data.llm.hint ?? null);
      setSuccess(`已保存到 ${res.saved_files.join(", ")}`);
      onSaved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  if (!form) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-dracula-comment gap-3 px-6 text-center">
        {loading ? (
          <>
            <Loader2 className="animate-spin" size={20} />
            <span className="text-xs font-mono">Loading settings...</span>
          </>
        ) : (
          <>
            <p className="text-xs font-mono text-dracula-red">{error ?? "无法加载设置"}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="px-3 py-1.5 text-xs font-mono bg-dracula-current/50 rounded hover:bg-dracula-current/70"
            >
              重试
            </button>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-6">
        <div className="max-w-4xl mx-auto space-y-8">
          <p className="text-[10px] font-mono text-dracula-comment">
            配置写入 configs/contextmap.yaml；API Key 写入 storage/local/secrets.env
          </p>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <Section title="LLM / API">
              <Field label="Model">
                <input className={settingsInputClass} value={form.llmModel} onChange={(e) => update("llmModel", e.target.value)} />
              </Field>
              <Field label="API URL">
                <input className={settingsInputClass} value={form.llmApiUrl} onChange={(e) => update("llmApiUrl", e.target.value)} />
              </Field>
              <Field label="Timeout (sec)">
                <input className={settingsInputClass} type="number" value={form.llmTimeout} onChange={(e) => update("llmTimeout", e.target.value)} />
              </Field>
              <Field label="DeepSeek API Key">
                <input
                  className={settingsInputClass}
                  type="password"
                  autoComplete="off"
                  placeholder={configured ? "已配置，留空则不修改" : "输入 API Key"}
                  value={form.deepseekApiKey}
                  onChange={(e) => update("deepseekApiKey", e.target.value)}
                />
                {configured && keyHint && (
                  <p className="text-[10px] text-dracula-green mt-1">已配置 {keyHint}</p>
                )}
              </Field>
            </Section>

            <Section title="Pipeline">
              {(
                [
                  ["maxConcurrentParse", "Max concurrent parse"],
                  ["maxConcurrentWhisper", "Max concurrent whisper"],
                  ["maxConcurrentOutline", "Max concurrent outline"],
                  ["maxConcurrentIngest", "Max concurrent ingest"],
                  ["maxConcurrentKg", "Max concurrent KG"],
                ] as const
              ).map(([key, label]) => (
                <Field key={key} label={label}>
                  <input className={settingsInputClass} type="number" value={form[key]} onChange={(e) => update(key, e.target.value)} />
                </Field>
              ))}
              <label className="flex items-center gap-2 text-xs font-mono text-dracula-fg">
                <input type="checkbox" checked={form.autoStartOnUpload} onChange={(e) => update("autoStartOnUpload", e.target.checked)} />
                Auto start pipeline on upload
              </label>
            </Section>

            <Section title="Knowledge Graph">
              <label className="flex items-center gap-2 text-xs font-mono text-dracula-fg">
                <input type="checkbox" checked={form.kgEnabled} onChange={(e) => update("kgEnabled", e.target.checked)} />
                KG extraction enabled
              </label>
              <label className="flex items-center gap-2 text-xs font-mono text-dracula-fg">
                <input type="checkbox" checked={form.kgFailOpen} onChange={(e) => update("kgFailOpen", e.target.checked)} />
                Fail open on KG errors
              </label>
              <Field label="Chunk max tokens">
                <input className={settingsInputClass} type="number" value={form.kgChunkMaxTokens} onChange={(e) => update("kgChunkMaxTokens", e.target.value)} />
              </Field>
              <label className="flex items-center gap-2 text-xs font-mono text-dracula-fg">
                <input type="checkbox" checked={form.retrievalGraphEnabled} onChange={(e) => update("retrievalGraphEnabled", e.target.checked)} />
                Retrieval graph channel enabled
              </label>
            </Section>

            <Section title="Retrieval & Chat">
              <Field label="Research max retries">
                <input className={settingsInputClass} type="number" value={form.chatMaxRetries} onChange={(e) => update("chatMaxRetries", e.target.value)} />
              </Field>
              <Field label="Retrieval top K default">
                <input className={settingsInputClass} type="number" value={form.retrievalTopK} onChange={(e) => update("retrievalTopK", e.target.value)} />
              </Field>
              <Field label="SSE token batch ms">
                <input className={settingsInputClass} type="number" value={form.sseBatchMs} onChange={(e) => update("sseBatchMs", e.target.value)} />
              </Field>
              <Field label="SSE token batch chars">
                <input className={settingsInputClass} type="number" value={form.sseBatchChars} onChange={(e) => update("sseBatchChars", e.target.value)} />
              </Field>
            </Section>
          </div>
        </div>
      </div>

      <div className="shrink-0 px-6 py-3 border-t border-dracula-comment/20 bg-[var(--wb-editor-bg)] space-y-2">
        {error && <p className="text-xs text-dracula-red font-mono">{error}</p>}
        {success && <p className="text-xs text-dracula-green font-mono">{success}</p>}
        <div className="flex justify-end">
          <button
            type="button"
            disabled={saving}
            onClick={() => void handleSave()}
            className="px-4 py-1.5 text-xs font-mono bg-dracula-purple/80 text-dracula-fg rounded hover:bg-dracula-purple disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

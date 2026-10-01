import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { BrandSettings, GeminiSettingsStatus, LinkedInSettingsStatus, LlmSettingsStatus, NvidiaSettingsStatus } from "../lib/types";

type Tab = "gemini" | "linkedin" | "brand";

export default function Settings() {
  const [params] = useSearchParams();
  const [tab, setTab] = useState<Tab>("gemini");
  const linkedinNotice = params.get("linkedin");

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="panel-heading text-lg">Settings</h1>
      {linkedinNotice === "connected" && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">LinkedIn account connected.</p>}
      {linkedinNotice === "error" && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">LinkedIn connection failed ({params.get("message")}). Check your client id/secret and redirect URL, then try again.</p>}

      <div className="flex gap-1 border-b border-slate-200">
        {(["gemini", "linkedin", "brand"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`border-b-2 px-4 py-2 text-sm font-medium capitalize transition-colors ${tab === t ? "border-brand-500 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            {t === "brand" ? "Brand & preferences" : t}
          </button>
        ))}
      </div>

      {tab === "gemini" && <GeminiPanel />}
      {tab === "linkedin" && <LinkedInPanel />}
      {tab === "brand" && <BrandPanel />}
    </div>
  );
}

function GeminiPanel() {
  const [status, setStatus] = useState<GeminiSettingsStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const [llm, setLlm] = useState<LlmSettingsStatus | null>(null);
  const [ollamaModel, setOllamaModel] = useState("");
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("");
  const [ollamaBusy, setOllamaBusy] = useState<string | null>(null);
  const [ollamaMessage, setOllamaMessage] = useState("");

  async function load() {
    const s = await api.get<GeminiSettingsStatus>("/api/settings/gemini");
    setStatus(s);
    setModel(s.model);
  }
  async function loadLlm() {
    const l = await api.get<LlmSettingsStatus>("/api/settings/llm");
    setLlm(l);
    setOllamaModel(l.ollama_model);
    setOllamaBaseUrl(l.ollama_base_url);
  }
  useEffect(() => {
    void load();
    void loadLlm();
  }, []);

  const [nvidia, setNvidia] = useState<NvidiaSettingsStatus | null>(null);
  const [nvidiaApiKey, setNvidiaApiKey] = useState("");
  const [nvidiaRevealed, setNvidiaRevealed] = useState(false);
  const [nvidiaModel, setNvidiaModel] = useState("");
  const [nvidiaBusy, setNvidiaBusy] = useState<string | null>(null);
  const [nvidiaMessage, setNvidiaMessage] = useState("");

  async function loadNvidia() {
    const n = await api.get<NvidiaSettingsStatus>("/api/settings/nvidia");
    setNvidia(n);
    setNvidiaModel(n.model);
  }
  useEffect(() => {
    void loadNvidia();
  }, []);

  async function saveNvidiaKey() {
    setNvidiaBusy("save");
    setNvidiaMessage("");
    try {
      await api.put("/api/settings/nvidia", { api_key: nvidiaApiKey });
      setNvidiaApiKey("");
      setNvidiaMessage("Key configured");
      await loadNvidia();
    } catch (err) {
      setNvidiaMessage(err instanceof ApiError ? err.message : "Could not save the key.");
    } finally {
      setNvidiaBusy(null);
    }
  }

  async function removeNvidiaKey() {
    setNvidiaBusy("remove");
    await api.delete("/api/settings/nvidia");
    await loadNvidia();
    setNvidiaBusy(null);
  }

  async function testNvidia() {
    setNvidiaBusy("test");
    setNvidiaMessage("");
    try {
      const res = await api.post<{ ok: boolean; message: string }>("/api/settings/nvidia/test");
      setNvidiaMessage(res.message);
    } catch (err) {
      setNvidiaMessage(err instanceof ApiError ? err.message : "Test failed.");
    } finally {
      setNvidiaBusy(null);
    }
  }

  async function saveNvidiaModel(next: string) {
    setNvidiaModel(next);
    await api.put("/api/settings/nvidia/model", { model: next });
  }

  async function setProvider(provider: "gemini" | "ollama" | "nvidia") {
    await api.put("/api/settings/brand", { llm_provider: provider });
    await loadLlm();
  }

  async function saveOllamaConfig() {
    setOllamaBusy("save");
    await api.put("/api/settings/brand", { ollama_model: ollamaModel, ollama_base_url: ollamaBaseUrl });
    await loadLlm();
    setOllamaBusy(null);
  }

  async function testOllama() {
    setOllamaBusy("test");
    setOllamaMessage("");
    try {
      const res = await api.post<{ ok: boolean; message: string }>("/api/settings/ollama/test");
      setOllamaMessage(res.message);
    } catch (err) {
      setOllamaMessage(err instanceof ApiError ? err.message : "Test failed.");
    } finally {
      setOllamaBusy(null);
    }
  }

  async function save() {
    setBusy("save");
    setMessage("");
    try {
      await api.put("/api/settings/gemini", { api_key: apiKey });
      setApiKey("");
      setMessage("Key configured");
      await load();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Could not save the key.");
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    setBusy("remove");
    await api.delete("/api/settings/gemini");
    await load();
    setBusy(null);
  }

  async function test() {
    setBusy("test");
    setMessage("");
    try {
      const res = await api.post<{ ok: boolean; message: string }>("/api/settings/gemini/test");
      setMessage(res.message);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Test failed.");
    } finally {
      setBusy(null);
    }
  }

  async function saveModel(next: string) {
    setModel(next);
    await api.put("/api/settings/gemini/model", { model: next });
  }

  if (!status || !llm || !nvidia) return null;

  return (
    <div className="space-y-6">
      <div className="card space-y-3">
        <p className="text-sm font-medium text-slate-700">Content generation provider</p>
        <p className="text-xs text-slate-500">Gemini and NVIDIA NIM are hosted APIs that need a key and a connection. Ollama runs a model locally — free, offline, no key required — but needs the Ollama app running on this machine.</p>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => void setProvider("gemini")} className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${llm.provider === "gemini" ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}>
            Gemini API
          </button>
          <button onClick={() => void setProvider("nvidia")} className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${llm.provider === "nvidia" ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}>
            NVIDIA NIM
          </button>
          <button onClick={() => void setProvider("ollama")} className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${llm.provider === "ollama" ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}>
            Local model (Ollama)
          </button>
        </div>

        {llm.provider === "ollama" && (
          <div className="mt-3 space-y-3 border-t border-slate-100 pt-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="ollama-model" className="field-label">
                  Model
                </label>
                <select id="ollama-model" value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} className="field-input mt-1">
                  {llm.ollama_supported_models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                  {!llm.ollama_supported_models.includes(ollamaModel) && <option value={ollamaModel}>{ollamaModel}</option>}
                </select>
              </div>
              <div>
                <label htmlFor="ollama-url" className="field-label">
                  Ollama server URL
                </label>
                <input id="ollama-url" value={ollamaBaseUrl} onChange={(e) => setOllamaBaseUrl(e.target.value)} className="field-input mt-1" />
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => void saveOllamaConfig()} disabled={ollamaBusy !== null} className="btn-primary">
                {ollamaBusy === "save" ? "Saving…" : "Save"}
              </button>
              <button onClick={() => void testOllama()} disabled={ollamaBusy !== null} className="btn-secondary">
                {ollamaBusy === "test" ? "Testing…" : "Test Connection"}
              </button>
            </div>
            {ollamaMessage && <p className="text-sm text-slate-600">{ollamaMessage}</p>}
            <p className="text-xs text-slate-400">
              A model must already be pulled locally (e.g. <code>ollama pull {ollamaModel}</code>) before it will work here.
            </p>
          </div>
        )}
      </div>

      <div className={`card space-y-5 transition-opacity ${llm.provider !== "gemini" ? "opacity-60" : ""}`}>
        <div>
          <p className="text-sm font-medium text-slate-700">Status</p>
          <p className="mt-1 text-sm text-slate-600">{status.configured ? (status.source === "env" ? "Configured on server" : `Key configured (${status.masked})`) : "Not configured"}</p>
        </div>
        <div>
          <label htmlFor="gemini-key" className="field-label">
            Gemini API key
          </label>
          <div className="mt-1 flex gap-2">
            <input id="gemini-key" type={revealed ? "text" : "password"} value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="Paste a new key to replace the current one" className="field-input flex-1" />
            <button type="button" onClick={() => setRevealed((r) => !r)} className="btn-secondary">
              {revealed ? "Hide" : "Reveal"}
            </button>
          </div>
          <p className="mt-1 text-xs text-slate-400">Only what you type here can be revealed. A saved key is never sent back to this page.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={save} disabled={busy !== null || !apiKey} className="btn-primary">
            {busy === "save" ? "Saving…" : "Save"}
          </button>
          <button onClick={remove} disabled={busy !== null || !status.configured} className="btn-secondary">
            Remove
          </button>
          <button onClick={test} disabled={busy !== null || !status.configured} className="btn-secondary">
            {busy === "test" ? "Testing…" : "Test Connection"}
          </button>
        </div>
        {message && <p className="text-sm text-slate-600">{message}</p>}

        <div>
          <label htmlFor="gemini-model" className="field-label">
            Model
          </label>
          <select id="gemini-model" value={model} onChange={(e) => void saveModel(e.target.value)} className="field-input mt-1">
            {status.supported_models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className={`card space-y-5 transition-opacity ${llm.provider !== "nvidia" ? "opacity-60" : ""}`}>
        <div>
          <p className="text-sm font-medium text-slate-700">Status</p>
          <p className="mt-1 text-sm text-slate-600">{nvidia.configured ? (nvidia.source === "env" ? "Configured on server" : `Key configured (${nvidia.masked})`) : "Not configured"}</p>
          <p className="mt-1 text-xs text-slate-400">
            Get a free API key at{" "}
            <a href="https://build.nvidia.com" target="_blank" rel="noreferrer" className="text-brand-600 underline hover:text-brand-700">
              build.nvidia.com
            </a>
            .
          </p>
        </div>
        <div>
          <label htmlFor="nvidia-key" className="field-label">
            NVIDIA API key
          </label>
          <div className="mt-1 flex gap-2">
            <input id="nvidia-key" type={nvidiaRevealed ? "text" : "password"} value={nvidiaApiKey} onChange={(e) => setNvidiaApiKey(e.target.value)} placeholder="Paste a new key to replace the current one" className="field-input flex-1" />
            <button type="button" onClick={() => setNvidiaRevealed((r) => !r)} className="btn-secondary">
              {nvidiaRevealed ? "Hide" : "Reveal"}
            </button>
          </div>
          <p className="mt-1 text-xs text-slate-400">Only what you type here can be revealed. A saved key is never sent back to this page.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => void saveNvidiaKey()} disabled={nvidiaBusy !== null || !nvidiaApiKey} className="btn-primary">
            {nvidiaBusy === "save" ? "Saving…" : "Save"}
          </button>
          <button onClick={() => void removeNvidiaKey()} disabled={nvidiaBusy !== null || !nvidia.configured} className="btn-secondary">
            Remove
          </button>
          <button onClick={() => void testNvidia()} disabled={nvidiaBusy !== null || !nvidia.configured} className="btn-secondary">
            {nvidiaBusy === "test" ? "Testing…" : "Test Connection"}
          </button>
        </div>
        {nvidiaMessage && <p className="text-sm text-slate-600">{nvidiaMessage}</p>}

        <div>
          <label htmlFor="nvidia-model" className="field-label">
            Model
          </label>
          <select id="nvidia-model" value={nvidiaModel} onChange={(e) => void saveNvidiaModel(e.target.value)} className="field-input mt-1">
            {nvidia.supported_models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
            {!nvidia.supported_models.includes(nvidiaModel) && nvidiaModel && <option value={nvidiaModel}>{nvidiaModel}</option>}
          </select>
          <p className="mt-1 text-xs text-slate-400">Any model ID available to your NVIDIA account works, even if it's not in this list.</p>
        </div>
      </div>
    </div>
  );
}

function LinkedInPanel() {
  const [status, setStatus] = useState<LinkedInSettingsStatus | null>(null);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function load() {
    setStatus(await api.get<LinkedInSettingsStatus>("/api/settings/linkedin"));
  }
  useEffect(() => {
    void load();
  }, []);

  async function saveApp() {
    setBusy("save");
    await api.put("/api/settings/linkedin", { client_id: clientId, client_secret: clientSecret });
    setClientId("");
    setClientSecret("");
    await load();
    setBusy(null);
  }

  async function removeApp() {
    setBusy("remove");
    await api.delete("/api/settings/linkedin");
    await load();
    setBusy(null);
  }

  async function disconnect() {
    setBusy("disconnect");
    await api.post("/api/settings/linkedin/disconnect");
    await load();
    setBusy(null);
  }

  if (!status) return null;

  return (
    <div className="card space-y-6">
      <div>
        <p className="text-sm text-slate-600">Create a LinkedIn developer app at developer.linkedin.com, request the "Share on LinkedIn" and "Sign In with LinkedIn using OpenID Connect" products, and register the redirect URL below exactly.</p>
        <div className="mt-2 flex items-center gap-2">
          <code className="flex-1 truncate rounded-lg bg-slate-100 px-3 py-2 text-xs">{status.redirect_uri}</code>
          <button
            onClick={() => {
              void navigator.clipboard.writeText(status.redirect_uri);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="btn-secondary !px-3 !py-2 !text-xs"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="li-client-id" className="field-label">
            Client ID
          </label>
          <input id="li-client-id" value={clientId} onChange={(e) => setClientId(e.target.value)} className="field-input mt-1" />
        </div>
        <div>
          <label htmlFor="li-client-secret" className="field-label">
            Client Secret
          </label>
          <input id="li-client-secret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} className="field-input mt-1" />
        </div>
      </div>
      <p className="text-sm text-slate-600">{status.app_configured ? (status.app_source === "env" ? "Configured on server" : `Saved (${status.app_masked})`) : "Not configured"}</p>
      <div className="flex flex-wrap gap-2">
        <button onClick={saveApp} disabled={busy !== null || !clientId || !clientSecret} className="btn-primary">
          Save Credentials
        </button>
        <button onClick={removeApp} disabled={busy !== null || !status.app_configured} className="btn-secondary">
          Remove
        </button>
      </div>

      <hr className="border-slate-200" />

      <div>
        <p className="text-sm font-medium text-slate-700">Connection</p>
        {status.connection.connected ? (
          <div className="mt-2 space-y-2">
            <p className="text-sm text-slate-600">
              Connected as <strong>{status.connection.account_name}</strong>
              {status.connection.expired && <span className="ml-2 text-amber-700">(token expired — reconnect)</span>}
            </p>
            <button onClick={disconnect} disabled={busy !== null} className="btn-secondary">
              Disconnect
            </button>
          </div>
        ) : (
          <a href="/api/linkedin/oauth/start" className={status.app_configured ? "btn-primary mt-2" : "btn-primary mt-2 pointer-events-none opacity-55"}>
            Connect LinkedIn
          </a>
        )}
      </div>
    </div>
  );
}

function BrandPanel() {
  const [brand, setBrand] = useState<BrandSettings | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void api.get<BrandSettings>("/api/settings/brand").then(setBrand);
  }, []);

  async function save() {
    if (!brand) return;
    const updated = await api.put<BrandSettings>("/api/settings/brand", brand);
    setBrand(updated);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  if (!brand) return null;
  const set = <K extends keyof BrandSettings>(key: K, value: BrandSettings[K]) => setBrand({ ...brand, [key]: value });

  return (
    <div className="card space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Brand name" value={brand.brand_name} onChange={(v) => set("brand_name", v)} />
        <Field label="Image footer" value={brand.image_footer} onChange={(v) => set("image_footer", v)} />
        <ColorField label="Primary color" value={brand.brand_color_primary} onChange={(v) => set("brand_color_primary", v)} />
        <ColorField label="Secondary color" value={brand.brand_color_secondary} onChange={(v) => set("brand_color_secondary", v)} />
        <ColorField label="Text color" value={brand.brand_color_text} onChange={(v) => set("brand_color_text", v)} />
        <SelectField label="Image template" value={brand.image_template} options={["classic", "minimal"]} onChange={(v) => set("image_template", v as BrandSettings["image_template"])} />
        <SelectField label="Content tone" value={brand.content_tone} options={["professional", "conversational", "enthusiastic"]} onChange={(v) => set("content_tone", v as BrandSettings["content_tone"])} />
        <Field label="Output language" value={brand.output_language} onChange={(v) => set("output_language", v)} />
        <Field label="Timezone" value={brand.timezone} onChange={(v) => set("timezone", v)} />
        <Field label="Processing retry limit" type="number" value={String(brand.retry_limit)} onChange={(v) => set("retry_limit", Number(v) || 3)} />
      </div>

      <hr className="border-slate-200" />

      <div>
        <p className="text-sm font-medium text-slate-700">Transcript fallback</p>
        <p className="mt-1 text-xs text-slate-500">When a video has no YouTube transcript panel (common for Shorts or videos with captions disabled), download its audio and transcribe it locally with Whisper — free, offline, runs on this machine.</p>
        <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={brand.whisper_fallback} onChange={(e) => set("whisper_fallback", e.target.checked)} className="h-4 w-4 rounded border-slate-300 text-brand-500 focus:ring-brand-500/30" />
          Fall back to local Whisper transcription
        </label>
        {brand.whisper_fallback && (
          <div className="mt-2 max-w-xs">
            <SelectField label="Whisper model size" value={brand.whisper_model} options={["tiny", "base", "small", "medium"]} onChange={(v) => set("whisper_model", v)} />
            <p className="mt-1 text-xs text-slate-400">Larger models are more accurate but slower on CPU. The first use of a given size downloads it once and caches it.</p>
          </div>
        )}
      </div>

      <button onClick={save} className="btn-primary">
        {saved ? "Saved" : "Save preferences"}
      </button>
    </div>
  );
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  return (
    <label className="field-label">
      {label}
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} className="field-input mt-1 font-normal" />
    </label>
  );
}

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="field-label">
      {label}
      <div className="mt-1 flex items-center gap-2">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="h-9 w-12 rounded-lg border border-slate-300" />
        <input value={value} onChange={(e) => onChange(e.target.value)} className="field-input flex-1 font-normal" />
      </div>
    </label>
  );
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <label className="field-label">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="field-input mt-1 font-normal capitalize">
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

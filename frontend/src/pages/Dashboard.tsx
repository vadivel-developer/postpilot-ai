import { useCallback, useEffect, useState } from "react";
import DraftCard, { EmptyCard } from "../components/DraftCard";
import { api, ApiError } from "../lib/api";
import type { Channel, ChannelCandidate, Draft, ResolvedChannel } from "../lib/types";

function localDateISO(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function formatCardLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

export default function Dashboard() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selectedChannelId, setSelectedChannelId] = useState<number | null>(null);
  const [channelInput, setChannelInput] = useState("");
  const [candidates, setCandidates] = useState<ChannelCandidate[] | null>(null);
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState("");

  const [todayDraft, setTodayDraft] = useState<Draft | null>(null);
  const [tomorrowDraft, setTomorrowDraft] = useState<Draft | null>(null);
  const [loadingCards, setLoadingCards] = useState(true);
  const [generating, setGenerating] = useState<"today" | "tomorrow" | null>(null);
  const [notice, setNotice] = useState("");

  const today = localDateISO(0);
  const tomorrow = localDateISO(1);

  const loadChannels = useCallback(async () => {
    const list = await api.get<Channel[]>("/api/channels");
    setChannels(list);
    if (list.length && selectedChannelId === null) {
      const def = list.find((c) => c.is_default) ?? list[0];
      setSelectedChannelId(def.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadCards = useCallback(async () => {
    setLoadingCards(true);
    const rows = await api.get<Draft[]>(`/api/drafts?date_from=${today}&date_to=${tomorrow}`);
    setTodayDraft(rows.find((d) => d.card_date === today) ?? null);
    setTomorrowDraft(rows.find((d) => d.card_date === tomorrow) ?? null);
    setLoadingCards(false);
  }, [today, tomorrow]);

  useEffect(() => {
    void loadChannels();
    void loadCards();
  }, [loadChannels, loadCards]);

  async function resolveChannel(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setCandidates(null);
    if (!channelInput.trim()) return;
    setResolving(true);
    try {
      const res = await api.post<{ resolved?: ResolvedChannel; candidates?: ChannelCandidate[] }>("/api/channels/resolve", { input: channelInput.trim() });
      if (res.candidates) {
        setCandidates(res.candidates);
      } else if (res.resolved) {
        await confirmChannel(res.resolved.url, res.resolved.name);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resolve that channel.");
    } finally {
      setResolving(false);
    }
  }

  async function confirmChannel(url: string, name: string) {
    setError("");
    try {
      const channel = await api.post<Channel>("/api/channels/confirm", { url, name });
      setCandidates(null);
      setChannelInput("");
      await loadChannels();
      setSelectedChannelId(channel.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save that channel.");
    }
  }

  async function generate(which: "today" | "tomorrow") {
    if (!selectedChannelId) {
      setError("Select or add a channel first.");
      return;
    }
    setGenerating(which);
    setNotice("");
    setError("");
    try {
      const cardDate = which === "today" ? today : tomorrow;
      const res = await api.post<{ draft?: Draft; existing_draft?: Draft; no_new_video?: boolean; message?: string }>("/api/drafts/generate", { channel_id: selectedChannelId, card_date: cardDate });
      if (res.no_new_video) {
        setNotice("No new video found for this channel.");
      } else if (res.existing_draft) {
        setNotice(res.message ?? "This video was already turned into a draft.");
        await loadCards();
      } else if (res.draft) {
        if (which === "today") setTodayDraft(res.draft);
        else setTomorrowDraft(res.draft);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a post.");
    } finally {
      setGenerating(null);
    }
  }

  return (
    <div className="space-y-8">
      <section className="card">
        <div className="mx-auto max-w-xl text-center">
          <h1 className="panel-heading text-lg">Find a YouTube channel</h1>
          <p className="mt-1 text-sm text-slate-500">Enter a channel name, channel URL, or a specific video URL.</p>
          <form onSubmit={resolveChannel} className="mt-4 flex gap-2">
            <label htmlFor="channel-input" className="sr-only">
              Channel name, URL, or video URL
            </label>
            <input id="channel-input" value={channelInput} onChange={(e) => setChannelInput(e.target.value)} placeholder="e.g. @channelhandle or a video URL" className="field-input flex-1" />
            <button type="submit" disabled={resolving} className="btn-primary shrink-0">
              {resolving ? "Finding…" : "Find Channel"}
            </button>
          </form>

          {candidates && candidates.length > 0 && (
            <div className="mt-4 space-y-2 text-left">
              <p className="text-sm font-medium text-slate-700">Multiple channels match — confirm the right one:</p>
              {candidates.map((c) => (
                <button key={c.url} onClick={() => confirmChannel(c.url, c.name)} className="block w-full rounded-lg border border-slate-200 px-3 py-2 text-left text-sm transition-colors hover:border-brand-400 hover:bg-brand-50">
                  <span className="font-medium">{c.name}</span> {c.handle && <span className="text-slate-500">({c.handle})</span>}
                  <br />
                  <span className="text-xs text-slate-400">{c.url}</span>
                </button>
              ))}
            </div>
          )}

          {channels.length > 0 && (
            <div className="mt-4 text-left">
              <label htmlFor="saved-channel" className="field-label">
                Saved channel
              </label>
              <select id="saved-channel" value={selectedChannelId ?? ""} onChange={(e) => setSelectedChannelId(Number(e.target.value))} className="field-input mt-1">
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {error && (
            <p role="alert" className="mt-3 text-sm text-red-600">
              {error}
            </p>
          )}
          {notice && <p className="mt-3 text-sm text-slate-600">{notice}</p>}
        </div>
      </section>

      {loadingCards ? (
        <p className="text-sm text-slate-500">Loading cards…</p>
      ) : (
        <div className="space-y-6">
          {todayDraft ? <DraftCard draft={todayDraft} label={formatCardLabel(today)} onChanged={setTodayDraft} /> : <EmptyCard label={formatCardLabel(today)} onGenerate={() => generate("today")} disabled={generating !== null || !selectedChannelId} />}
          {tomorrowDraft ? <DraftCard draft={tomorrowDraft} label={formatCardLabel(tomorrow)} onChanged={setTomorrowDraft} /> : <EmptyCard label={formatCardLabel(tomorrow)} onGenerate={() => generate("tomorrow")} disabled={generating !== null || !selectedChannelId} />}
        </div>
      )}
    </div>
  );
}

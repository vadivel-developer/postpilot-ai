import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { IN_PROGRESS_STATUSES, STATUS_LABELS, type Draft } from "../lib/types";

function StatusPill({ status }: { status: Draft["status"] }) {
  const tone =
    status === "draft" || status === "needs_review"
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : status === "failed" || status === "transcript_unavailable"
        ? "bg-red-50 text-red-700 border-red-200"
        : IN_PROGRESS_STATUSES.includes(status)
          ? "bg-blue-50 text-blue-700 border-blue-200"
          : "bg-slate-100 text-slate-600 border-slate-200";
  return <span className={`badge ${tone}`}>{STATUS_LABELS[status]}</span>;
}

function SeverityBadge({ severity }: { severity: string }) {
  const tone = severity === "high" ? "bg-red-100 text-red-700" : severity === "medium" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600";
  return <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase ${tone}`}>{severity}</span>;
}

export function EmptyCard({ label, onGenerate, disabled }: { label: string; onGenerate: () => void; disabled: boolean }) {
  return (
    <section className="card-dashed">
      <h3 className="panel-heading">{label}</h3>
      <p className="mt-1 text-sm text-slate-500">Status: Not generated</p>
      <button onClick={onGenerate} disabled={disabled} className="btn-primary mt-4">
        Generate Post
      </button>
    </section>
  );
}

export default function DraftCard({ draft, label, onChanged }: { draft: Draft; label: string; onChanged: (d: Draft) => void }) {
  const [postText, setPostText] = useState(draft.post_text ?? "");
  const [hashtags, setHashtags] = useState((draft.hashtags ?? []).join(" "));
  const [headline, setHeadline] = useState(draft.image_headline ?? "");
  const [takeaways, setTakeaways] = useState((draft.image_takeaways ?? []).join("\n"));
  const [transcriptPaste, setTranscriptPaste] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [showTranscript, setShowTranscript] = useState(false);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    setPostText(draft.post_text ?? "");
    setHashtags((draft.hashtags ?? []).join(" "));
    setHeadline(draft.image_headline ?? "");
    setTakeaways((draft.image_takeaways ?? []).join("\n"));
    // Intentionally re-syncs only when a fresh draft arrives (a new id, or a server-side update),
    // not on every keystroke into the local edit fields above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.id, draft.updated_at]);

  useEffect(() => {
    if (!IN_PROGRESS_STATUSES.includes(draft.status) && draft.publish?.status !== "publishing") return;
    pollRef.current = window.setInterval(async () => {
      const fresh = await api.get<Draft>(`/api/drafts/${draft.id}`);
      onChanged(fresh);
    }, 2500);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.status, draft.publish?.status]);

  async function run<T>(key: string, fn: () => Promise<T>) {
    setBusy(key);
    setError("");
    try {
      const result = await fn();
      return result;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function saveEdits() {
    const updated = await run("save", () =>
      api.patch<Draft>(`/api/drafts/${draft.id}`, {
        post_text: postText,
        hashtags: hashtags
          .split(/\s+/)
          .map((h) => h.trim())
          .filter(Boolean),
        image_headline: headline,
        image_takeaways: takeaways
          .split("\n")
          .map((t) => t.trim())
          .filter(Boolean),
      }),
    );
    if (updated) onChanged(updated);
  }

  async function regenerateText() {
    if (!window.confirm("Regenerate the text? Your current edits will be saved as a restorable revision first.")) return;
    const updated = await run("regen-text", () => api.post<Draft>(`/api/drafts/${draft.id}/regenerate-text`));
    if (updated) onChanged(updated);
  }

  async function regenerateImage() {
    const updated = await run("regen-image", () => api.post<Draft>(`/api/drafts/${draft.id}/regenerate-image`));
    if (updated) onChanged(updated);
  }

  async function retry() {
    const updated = await run("retry", () => api.post<Draft>(`/api/drafts/${draft.id}/retry`));
    if (updated) onChanged(updated);
  }

  async function submitTranscript() {
    if (transcriptPaste.trim().length < 20) {
      setError("Paste at least a few sentences of transcript.");
      return;
    }
    const updated = await run("transcript", () => api.post<Draft>(`/api/drafts/${draft.id}/transcript`, { text: transcriptPaste }));
    if (updated) onChanged(updated);
  }

  async function publish() {
    if (!window.confirm(`Publish this post to LinkedIn now? Card date "${label}" does not schedule anything — this publishes immediately.`)) return;
    await run("publish", () => api.post(`/api/drafts/${draft.id}/publish`));
    const fresh = await api.get<Draft>(`/api/drafts/${draft.id}`);
    onChanged(fresh);
  }

  const editable = draft.status === "draft" || draft.status === "needs_review";
  const findings = draft.verification ?? [];

  return (
    <section className="card transition-shadow hover:shadow-[var(--shadow-card-hover)]" aria-label={`${label} draft card`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="panel-heading">{label}</h3>
          <p className="mt-0.5 text-sm text-slate-500">{draft.video?.title ?? "…"}</p>
        </div>
        <StatusPill status={draft.status} />
      </div>

      {draft.video && (
        <a href={draft.video.source_url} target="_blank" rel="noreferrer" className="mt-3 block text-sm text-brand-600 underline underline-offset-2 hover:text-brand-700">
          {draft.video.source_url}
        </a>
      )}

      {IN_PROGRESS_STATUSES.includes(draft.status) && (
        <div className="mt-4 flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2.5 text-sm text-blue-700">
          <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" aria-hidden="true" />
          Working: {STATUS_LABELS[draft.status]}…
        </div>
      )}

      {draft.status === "transcript_unavailable" && (
        <div className="mt-4 space-y-3 rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700">{draft.last_error || "The transcript could not be retrieved automatically."}</p>
          <div className="flex flex-wrap gap-2">
            <button onClick={retry} disabled={busy !== null} className="btn-danger">
              {busy === "retry" ? "Retrying…" : "Retry"}
            </button>
          </div>
          <div>
            <label htmlFor={`paste-${draft.id}`} className="field-label">
              Or paste the transcript yourself
            </label>
            <textarea id={`paste-${draft.id}`} rows={4} value={transcriptPaste} onChange={(e) => setTranscriptPaste(e.target.value)} className="field-input mt-1" placeholder="Paste the video transcript text here…" />
            <button onClick={submitTranscript} disabled={busy !== null} className="btn-primary mt-2">
              {busy === "transcript" ? "Submitting…" : "Use this transcript"}
            </button>
          </div>
        </div>
      )}

      {draft.status === "failed" && (
        <div className="mt-4 space-y-2 rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700">{draft.last_error || "Something went wrong while generating this post."}</p>
          <button onClick={retry} disabled={busy !== null} className="btn-danger">
            {busy === "retry" ? "Retrying…" : "Retry"}
          </button>
        </div>
      )}

      {(draft.status === "draft" || draft.status === "needs_review") && (
        <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-4">
            {draft.translated_text && (
              <div>
                <button onClick={() => setShowTranscript((s) => !s)} className="text-sm font-medium text-brand-600 hover:text-brand-700">
                  {showTranscript ? "Hide" : "Show"} original transcript &amp; translation
                </button>
                {showTranscript && (
                  <div className="mt-2 max-h-60 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                    <p className="font-medium text-slate-700">Source language: {draft.source_language ?? "unknown"}</p>
                    <p className="mt-2 whitespace-pre-wrap">{draft.translated_text}</p>
                  </div>
                )}
                {draft.summary_text && <p className="mt-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{draft.summary_text}</p>}
              </div>
            )}

            {findings.length > 0 && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm font-medium text-amber-800">Verification findings (checked against the transcript)</p>
                <ul className="mt-2 space-y-1.5">
                  {findings.map((f, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-amber-900">
                      <SeverityBadge severity={f.severity} />
                      <span>{f.description}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <label htmlFor={`post-${draft.id}`} className="field-label">
                LinkedIn post
              </label>
              <textarea id={`post-${draft.id}`} rows={10} value={postText} onChange={(e) => setPostText(e.target.value)} disabled={!editable} className="field-input mt-1" />
            </div>
            <div>
              <label htmlFor={`hashtags-${draft.id}`} className="field-label">
                Hashtags
              </label>
              <input id={`hashtags-${draft.id}`} value={hashtags} onChange={(e) => setHashtags(e.target.value)} disabled={!editable} className="field-input mt-1" />
            </div>

            <div className="flex flex-wrap gap-2">
              <button onClick={saveEdits} disabled={busy !== null || !editable} className="btn-secondary">
                {busy === "save" ? "Saving…" : "Save Draft"}
              </button>
              <button onClick={regenerateText} disabled={busy !== null} className="btn-secondary">
                {busy === "regen-text" ? "Regenerating…" : "Regenerate Text"}
              </button>
              <button onClick={publish} disabled={busy !== null || draft.publish?.status === "published" || draft.publish?.status === "uncertain" || draft.publish?.status === "publishing"} className="btn-primary">
                {busy === "publish" ? "Publishing…" : "Publish to LinkedIn"}
              </button>
            </div>

            {draft.publish && (
              <div className={`rounded-xl p-3 text-sm ${draft.publish.status === "published" ? "bg-green-50 text-green-700" : draft.publish.status === "uncertain" ? "bg-amber-50 text-amber-800" : draft.publish.status === "failed" ? "bg-red-50 text-red-700" : "bg-blue-50 text-blue-700"}`}>
                {draft.publish.status === "publishing" && "Publishing to LinkedIn…"}
                {draft.publish.status === "published" && (
                  <>
                    Published.{" "}
                    {draft.publish.post_url && (
                      <a href={draft.publish.post_url} target="_blank" rel="noreferrer" className="underline">
                        View post
                      </a>
                    )}
                  </>
                )}
                {draft.publish.status === "uncertain" && "Publication uncertain — LinkedIn did not confirm success. Check your LinkedIn profile before trying again to avoid a duplicate post."}
                {draft.publish.status === "failed" && `Publish failed: ${draft.publish.error ?? ""}`}
              </div>
            )}
          </div>

          <div className="space-y-3 rounded-xl bg-slate-50/70 p-4">
            <div>
              <label htmlFor={`headline-${draft.id}`} className="field-label">
                Image headline
              </label>
              <input id={`headline-${draft.id}`} value={headline} onChange={(e) => setHeadline(e.target.value)} disabled={!editable} className="field-input mt-1" />
            </div>
            <div>
              <label htmlFor={`takeaways-${draft.id}`} className="field-label">
                Takeaways (one per line)
              </label>
              <textarea id={`takeaways-${draft.id}`} rows={4} value={takeaways} onChange={(e) => setTakeaways(e.target.value)} disabled={!editable} className="field-input mt-1" />
            </div>
            {draft.image_url && (
              <div>
                <img src={draft.image_url} alt={`Branded LinkedIn image: ${headline}`} className="w-full rounded-lg border border-slate-200 shadow-sm" />
                {draft.image_outdated && <p className="mt-1 text-xs text-amber-700">This image no longer matches the edited headline/takeaways.</p>}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <button onClick={saveEdits} disabled={busy !== null || !editable} className="btn-secondary !px-3 !py-1.5">
                Save
              </button>
              <button onClick={regenerateImage} disabled={busy !== null} className="btn-secondary !px-3 !py-1.5">
                {busy === "regen-image" ? "Rendering…" : "Regenerate Image"}
              </button>
              {draft.image_url && (
                <a href={draft.image_url} download className="btn-secondary !px-3 !py-1.5">
                  Download
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {error}
        </p>
      )}
    </section>
  );
}

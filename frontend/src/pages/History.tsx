import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { STATUS_LABELS, type Draft } from "../lib/types";

function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function History() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void api.get<Draft[]>(`/api/drafts?date_from=${isoDaysAgo(60)}&date_to=${isoDaysAgo(-1)}`).then((rows) => {
      setDrafts(rows.sort((a, b) => b.card_date.localeCompare(a.card_date)));
      setLoading(false);
    });
  }, []);

  return (
    <div>
      <h1 className="panel-heading text-lg">Post history</h1>
      {loading ? (
        <p className="mt-4 text-sm text-slate-500">Loading…</p>
      ) : drafts.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">No posts yet. Generate one from the Dashboard.</p>
      ) : (
        <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200/80 bg-white" style={{ boxShadow: "var(--shadow-card)" }}>
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50/80 text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Video</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Publish</th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((d) => (
                <tr key={d.id} className="border-t border-slate-100 transition-colors hover:bg-slate-50/60">
                  <td className="px-4 py-3 text-slate-700">{d.card_date}</td>
                  <td className="px-4 py-3 text-slate-700">{d.video?.title ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{STATUS_LABELS[d.status]}</td>
                  <td className="px-4 py-3">
                    {d.publish?.status === "published" && d.publish.post_url ? (
                      <a href={d.publish.post_url} target="_blank" rel="noreferrer" className="font-medium text-brand-600 underline hover:text-brand-700">
                        View
                      </a>
                    ) : (
                      <span className="text-slate-400">{d.publish?.status ?? "not published"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

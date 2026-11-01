import { useState, type FormEvent } from "react";
import { ingest, type Song } from "../api";

interface Props {
  songs: Song[] | null;
  error: string | null;
  onChanged: () => void;
}

const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

export function Library({ songs, error, onChanged }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [status, setStatus] = useState<{ tone: "ok" | "bad" | "busy"; text: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setStatus({ tone: "busy", text: "Calculando la huella…" });
    try {
      const r = await ingest(file, { title: title.trim(), artist: artist.trim() });
      setStatus({
        tone: "ok",
        text: r.already_existed
          ? `Ya estaba en la biblioteca: ${r.song.title}`
          : `Agregada: ${r.song.artist ?? "?"} — ${r.song.title} (${r.song.n_hashes.toLocaleString()} hashes)`,
      });
      setFile(null);
      setTitle("");
      setArtist("");
      (e.target as HTMLFormElement).reset();
      onChanged();
    } catch (err) {
      setStatus({ tone: "bad", text: err instanceof Error ? err.message : String(err) });
    }
  }

  return (
    <div className="library">
      <section className="card">
        <h2>Agregar canción</h2>
        <form onSubmit={submit} className="ingest">
          <input type="file" accept="audio/*,.mp3,.wav,.flac,.ogg,.m4a" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          <input placeholder="Título (opcional: si no, se usa «Artista - Título» del nombre de archivo)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input placeholder="Artista (opcional)" value={artist} onChange={(e) => setArtist(e.target.value)} />
          <button type="submit" disabled={!file || status?.tone === "busy"}>
            Agregar
          </button>
        </form>
        {status && <p className={`hint ${status.tone}`}>{status.text}</p>}
      </section>

      <section className="card">
        <h2>Biblioteca {songs && <small>({songs.length} canciones)</small>}</h2>
        {error && <p className="hint bad">{error}</p>}
        {songs && (
          <table>
            <thead>
              <tr>
                <th>Artista</th>
                <th>Título</th>
                <th>Duración</th>
                <th>Hashes</th>
              </tr>
            </thead>
            <tbody>
              {songs.map((s) => (
                <tr key={s.id}>
                  <td>{s.artist ?? "—"}</td>
                  <td>{s.title}</td>
                  <td>{fmtTime(s.duration_s)}</td>
                  <td>{s.n_hashes.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

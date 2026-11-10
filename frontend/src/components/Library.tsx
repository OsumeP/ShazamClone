import { useState, type FormEvent } from "react";
import { ingest, type Song } from "../api";

interface Props {
  songs: Song[] | null;
  error: string | null;
  onChanged: () => void;
}

type Status = { tone: "busy" | "ok" | "exists" | "bad"; title: string; detail?: string };

const ICONS: Record<Status["tone"], string> = { busy: "…", ok: "✓", exists: "i", bad: "✕" };

const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

export function Library({ songs, error, onChanged }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [status, setStatus] = useState<Status | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget; // se guarda antes del await: después currentTarget ya no existe
    if (!file) return;
    setStatus({ tone: "busy", title: "Calculando la huella…", detail: "Puede tardar unos segundos." });
    try {
      const r = await ingest(file, { title: title.trim(), artist: artist.trim() });
      const label = `${r.song.artist ?? "Artista desconocido"} — ${r.song.title}`;
      setStatus(
        r.already_existed
          ? { tone: "exists", title: "Esa canción ya estaba en la biblioteca", detail: label }
          : { tone: "ok", title: "¡Canción agregada!", detail: `${label} · ${r.song.n_hashes.toLocaleString()} hashes` },
      );
      setFile(null);
      setTitle("");
      setArtist("");
      form.reset();
      onChanged();
    } catch (err) {
      setStatus({
        tone: "bad",
        title: "No se pudo agregar la canción",
        detail: err instanceof Error ? err.message : String(err),
      });
    }
  }

  return (
    <div className="library">
      <section className="card">
        <h2>Agregar canción</h2>
        <form onSubmit={submit} className="ingest">
          <div className="file-row">
            <label className="btn btn-secondary">
              Elegir archivo
              <input
                type="file"
                className="visually-hidden"
                accept="audio/*,.mp3,.wav,.flac,.ogg,.m4a"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </label>
            <span className="file-name">{file ? file.name : "Ningún archivo seleccionado"}</span>
          </div>
          <input
            aria-label="Título"
            placeholder="Título (opcional: si no, se usa «Artista - Título» del nombre de archivo)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input aria-label="Artista" placeholder="Artista (opcional)" value={artist} onChange={(e) => setArtist(e.target.value)} />
          <button type="submit" className="btn btn-primary" disabled={!file || status?.tone === "busy"}>
            Agregar
          </button>
        </form>
        {status && (
          <div className={`notice ${status.tone}`} role="status">
            <span className="notice-icon" aria-hidden="true">
              {ICONS[status.tone]}
            </span>
            <div>
              <p className="notice-title">{status.title}</p>
              {status.detail && <p className="notice-detail">{status.detail}</p>}
            </div>
          </div>
        )}
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

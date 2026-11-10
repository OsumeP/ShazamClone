import { useCallback, useEffect, useState } from "react";
import { getHealth, getSongs, type Health, type Song } from "./api";
import { Library } from "./components/Library";
import { Recognizer } from "./components/Recognizer";

type Tab = "recognize" | "library";

export default function App() {
  const [tab, setTab] = useState<Tab>("recognize");
  const [health, setHealth] = useState<Health | null>(null);
  const [songs, setSongs] = useState<Song[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [h, s] = await Promise.all([getHealth(), getSongs()]);
      setHealth(h);
      setSongs(s);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="app">
      <header>
        <div>
          <h1>SonicMatch</h1>
          <p className="subtitle">
            Reconocimiento de música por huellas acústicas (STFT + mapa de constelación)
          </p>
          <p className={`conn ${error ? "bad" : health ? "ok" : "wait"}`} role="status">
            <span className="dot" aria-hidden="true" />
            {error ? "Backend sin conexión" : health ? "Conectado" : "Conectando…"}
          </p>

        </div>
      </header>

      <div className="tabs-row">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "recognize"} className={tab === "recognize" ? "selected" : ""} onClick={() => setTab("recognize")}>
            Reconocer
          </button>
          <button role="tab" aria-selected={tab === "library"} className={tab === "library" ? "selected" : ""} onClick={() => setTab("library")}>
            Biblioteca
          </button>
        </div>

        <dl className="stats">
          <div>
            <dt>Canciones</dt>
            <dd>{health ? health.songs : "—"}</dd>
          </div>
          <div>
            <dt>Hashes</dt>
            <dd>{health ? health.hashes.toLocaleString() : "—"}</dd>
          </div>
        </dl>
      </div>

      <main>
        {error && tab === "recognize" && <p className="hint bad">{error}</p>}
        {tab === "recognize" ? <Recognizer /> : <Library songs={songs} error={error} onChanged={refresh} />}
      </main>

      <footer>
        Teoría de la Información y Sistemas de Comunicación · UNAL 2026-II · Juan David Patarroyo Sánchez, Laura Natalia
        Duarte Acero
      </footer>
    </div>
  );
}

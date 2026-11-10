import type { Recognition } from "../api";
import { levelHint } from "./LevelMeter";

export interface RecordingInfo {
  levelDbfs: number;
  peak: number;
  sampleRate: number;
  trackSettings: MediaTrackSettings;
}

interface Props {
  result: Recognition;
  latencyMs: number; // desde el fin de la grabación (o desde el envío del archivo) hasta la respuesta
  recording?: RecordingInfo;
}

// Un desfase negativo (coincidencias casuales) no es una posición válida en la canción.
const fmtTime = (s: number) => (s < 0 ? "—" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);

export function ResultCard({ result, latencyMs, recording }: Props) {
  const t = result.timings_ms;
  const second = result.candidates[1]?.score ?? 0;
  return (
    <section className={`card result ${result.recognized ? "hit" : "miss"}`}>
      {result.recognized && result.song ? (
        <>
          <h2>{result.song.title}</h2>        
          <p className="eyebrow">Canción reconocida</p>
          <p className="artist">{result.song.artist ?? "Artista desconocido"}</p>
          <p className="detail">
            El fragmento empieza en <strong>{fmtTime(result.offset_s ?? 0)}</strong> de la canción
          </p>
        </>
      ) : (
        <>
          <h2>No reconocida</h2>        
          <p className="eyebrow">Sin coincidencia</p>
          <p className="detail">
            Ninguna canción alcanzó el umbral (≥ 10 hashes alineados y el doble que la segunda).
          </p>
        </>
      )}

      <dl className="metrics">
        <div>
          <dt>Hashes alineados</dt>
          <dd>{result.score}</dd>
        </div>
        <div>
          <dt>Mejor / segundo</dt>
          <dd>
            {result.score} / {second} {result.confidence > 0 && <small>(×{result.confidence})</small>}
          </dd>
        </div>
        <div>
          <dt>Latencia total</dt>
          <dd className={latencyMs < 3000 ? "good" : "bad"}>{Math.round(latencyMs)} ms</dd>
        </div>
        <div>
          <dt>Hashes de la consulta</dt>
          <dd>{result.n_query_hashes}</dd>
        </div>
      </dl>

      <p className="timings">
        Servidor {t.server_total} ms = decodificación {t.decode} + huella {t.fingerprint} + búsqueda {t.lookup} +
        puntuación {t.scoring}; el resto es codificación WAV y red. RNF3: &lt; 3000 ms desde el fin de la grabación.
      </p>

      {recording && <RecordingDiagnostics rec={recording} duration={result.query_duration_s} />}

      {result.candidates.length > 0 && (
        <details>
          <summary>Candidatos (histograma de Δ por canción)</summary>
          <table>
            <thead>
              <tr>
                <th>Canción</th>
                <th>Alineados</th>
                <th>Coincidencias</th>
                <th>Inicio</th>
              </tr>
            </thead>
            <tbody>
              {result.candidates.map((c) => (
                <tr key={c.song_id}>
                  <td>
                    {c.artist ?? "?"} — {c.title}
                  </td>
                  <td>{c.score}</td>
                  <td>{c.n_matches}</td>
                  <td>{fmtTime(c.offset_s)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  );
}

function RecordingDiagnostics({ rec, duration }: { rec: RecordingInfo; duration: number }) {
  const hint = levelHint(rec.levelDbfs, rec.peak);
  const s = rec.trackSettings;
  // Algunos navegadores reportan un modo como texto en lugar de un booleano.
  const flag = (v: boolean | string | undefined) =>
    v === undefined ? "?" : v === false || v === "false" ? "desactivado" : `activado ⚠${typeof v === "string" ? ` (${v})` : ""}`;
  return (
    <div className="diagnostics">
      <p className={`hint ${hint.tone}`}>
        Nivel {rec.levelDbfs.toFixed(1)} dBFS, pico {rec.peak.toFixed(2)} — {hint.text}
      </p>
      <p>
        {duration.toFixed(1)} s grabados a {rec.sampleRate} Hz (el servidor remuestrea a 44 100 Hz). Procesamiento del
        navegador: cancelación de eco {flag(s.echoCancellation)}, supresión de ruido {flag(s.noiseSuppression)}, control
        automático de ganancia {flag(s.autoGainControl)}.
      </p>
    </div>
  );
}

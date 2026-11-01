import { useRef, useState } from "react";
import { recognize, type Recognition } from "../api";
import { recordClip } from "../audio/recorder";
import { encodeWav } from "../audio/wav";
import { LevelMeter } from "./LevelMeter";
import { LiveSpectrogram } from "./LiveSpectrogram";
import { ResultCard, type RecordingInfo } from "./ResultCard";

const DURATIONS = [5, 7, 10]; // RF4: ráfagas de 5 a 10 s

type State =
  | { kind: "idle" }
  | { kind: "recording"; progress: number }
  | { kind: "processing" }
  | { kind: "done"; result: Recognition; latencyMs: number; recording?: RecordingInfo }
  | { kind: "error"; message: string };

export function Recognizer({ onRecognized }: { onRecognized?: () => void }) {
  const [seconds, setSeconds] = useState(10);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [level, setLevel] = useState<number | null>(null);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const busy = state.kind === "recording" || state.kind === "processing";

  async function listen() {
    const abort = new AbortController();
    abortRef.current = abort;
    setLevel(null);
    setState({ kind: "recording", progress: 0 });
    try {
      const rec = await recordClip({
        seconds,
        signal: abort.signal,
        onLevel: setLevel,
        onProgress: (p) => setState({ kind: "recording", progress: p }),
        onAnalyser: setAnalyser,
      });
      setState({ kind: "processing" });
      const wav = new Blob([encodeWav(rec.samples, rec.sampleRate)], { type: "audio/wav" });
      const result = await recognize(wav);
      const latencyMs = performance.now() - rec.endedAt; // A3: desde el fin de la grabación
      setState({
        kind: "done",
        result,
        latencyMs,
        recording: { levelDbfs: rec.levelDbfs, peak: rec.peak, sampleRate: rec.sampleRate, trackSettings: rec.trackSettings },
      });
      onRecognized?.();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return setState({ kind: "idle" });
      const message =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Permiso de micrófono denegado. Habilítalo en la configuración del sitio del navegador."
          : err instanceof Error
            ? err.message
            : String(err);
      setState({ kind: "error", message });
    } finally {
      abortRef.current = null;
    }
  }

  async function fromFile(file: File) {
    setState({ kind: "processing" });
    const t0 = performance.now();
    try {
      const result = await recognize(file, file.name);
      setState({ kind: "done", result, latencyMs: performance.now() - t0 });
    } catch (err) {
      setState({ kind: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }

  return (
    <div className="recognizer">
      <section className="card capture">
        <button
          className={`listen ${state.kind === "recording" ? "active" : ""}`}
          onClick={state.kind === "recording" ? () => abortRef.current?.abort() : listen}
          disabled={state.kind === "processing"}
          aria-label={state.kind === "recording" ? "Cancelar grabación" : "Escuchar"}
        >
          <span className="pulse" />
          <span className="label">
            {state.kind === "recording" ? "Cancelar" : state.kind === "processing" ? "Buscando…" : "Escuchar"}
          </span>
        </button>

        <div className="controls">
          <div className="segmented" role="radiogroup" aria-label="Duración de la grabación">
            {DURATIONS.map((d) => (
              <button
                key={d}
                role="radio"
                aria-checked={seconds === d}
                className={seconds === d ? "selected" : ""}
                onClick={() => setSeconds(d)}
                disabled={busy}
              >
                {d} s
              </button>
            ))}
          </div>
          <label className={`file ${busy ? "disabled" : ""}`}>
            o reconocer un archivo…
            <input
              type="file"
              accept="audio/*"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void fromFile(f);
                e.target.value = "";
              }}
            />
          </label>
        </div>

        {state.kind === "recording" && (
          <>
            <progress value={state.progress} max={1} />
            <LevelMeter dbfs={level} />
          </>
        )}
        <LiveSpectrogram analyser={state.kind === "recording" ? analyser : null} />
        <p className="tip">
          Reproduce una canción de la biblioteca cerca del micrófono (10–30 cm). Apunta a un nivel entre −35 y −15
          dBFS.
        </p>
      </section>

      {state.kind === "done" && (
        <ResultCard result={state.result} latencyMs={state.latencyMs} recording={state.recording} />
      )}
      {state.kind === "error" && (
        <section className="card error" role="alert">
          <h2>Algo salió mal</h2>
          <p>{state.message}</p>
        </section>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { recognize, type Recognition } from "../api";
import { recordClip } from "../audio/recorder";
import { encodeWav } from "../audio/wav";
import listenIcon from "../assets/img_propuesta.png";
import volumeIcon from "../assets/img_volumen.png";
import { AnalysisCard } from "./AnalysisCard";
import { LevelMeter } from "./LevelMeter";
import { ResultCard, type RecordingInfo } from "./ResultCard";

const DURATIONS = [5, 7, 10]; // RF4: ráfagas de 5 a 10 s

type State =
  | { kind: "idle" }
  | { kind: "recording"; progress: number }
  | { kind: "processing" }
  | { kind: "done"; result: Recognition; latencyMs: number; recording?: RecordingInfo }
  | { kind: "error"; message: string };

// Traduce los errores de getUserMedia a instrucciones concretas. Los mensajes
// ("dismissed", "by system") son los de Chrome y Edge; en otros navegadores
// se usa el texto general de NotAllowedError.
function describeError(err: unknown): string {
  if (err instanceof DOMException) {
    switch (err.name) {
      case "NotAllowedError":
        if (/dismissed/i.test(err.message))
          return "Cerraste el aviso del micrófono sin elegir. Pulsa de nuevo y elige «Permitir».";
        if (/by system/i.test(err.message))
          return "Windows está bloqueando el micrófono para el navegador. Revisa Configuración → Privacidad → Micrófono (incluida la opción de aplicaciones de escritorio).";
        return "El navegador tiene el micrófono bloqueado para este sitio. Haz clic en el icono junto a la dirección, permite el micrófono y recarga la página.";
      case "NotFoundError":
        return "No se encontró ningún micrófono. Conéctalo o elígelo en la configuración del navegador.";
      case "NotReadableError":
        return "El micrófono está en uso por otra aplicación (¿Meet, Teams?). Ciérrala e inténtalo de nuevo.";
    }
  }
  return err instanceof Error ? err.message : String(err);
}

export function Recognizer({ onRecognized }: { onRecognized?: () => void }) {
  const [seconds, setSeconds] = useState(5);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [level, setLevel] = useState<number | null>(null);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [source, setSource] = useState<"mic" | "file" | null>(null);
  const [origin, setOrigin] = useState("Micrófono");
  const abortRef = useRef<AbortController | null>(null);
  const busy = state.kind === "recording" || state.kind === "processing";
  const [showDone, setShowDone] = useState(false);

  // «Proceso terminado» junto a «Subir archivo»: visible 5 s tras cada reconocimiento.
  useEffect(() => {
    if (state.kind !== "done") {
      setShowDone(false);
      return;
    }
    setShowDone(true);
    const timer = window.setTimeout(() => setShowDone(false), 5000);
    return () => window.clearTimeout(timer);
  }, [state.kind]);

  const listenLabel =
    state.kind === "recording"
      ? "Grabando… haz clic para cancelar"
      : state.kind === "processing"
        ? "Buscando…"
        : "Haz clic para grabar";

  async function listen() {
    const abort = new AbortController();
    abortRef.current = abort;
    setSource("mic");
    setOrigin(`Micrófono · ${seconds} s`);
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
      const result = await recognize(wav, "grabacion.wav", true); // con datos para la constelación
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
      setState({ kind: "error", message: describeError(err) });
    } finally {
      abortRef.current = null;
    }
  }

  async function fromFile(file: File) {
    setSource("file"); // con un archivo no hay gráficas: la tarjeta de análisis se oculta
    setState({ kind: "processing" });
    const t0 = performance.now();
    try {
      const result = await recognize(file, file.name);
      setState({ kind: "done", result, latencyMs: performance.now() - t0 });
    } catch (err) {
      setState({ kind: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }

  const analysis = state.kind === "done" && source === "mic" ? (state.result.analysis ?? null) : null;

  return (
    <div className="recognizer">
      {/* Añadimos la clase panel-container para poder superponer el título sobre la línea */}
      <section className="card panel-container">
        <h2 className="step-title">1 · Elegir la entrada</h2>
        
        <div className="inputs">
          <div className="input-record">
            {/* 1. Botón redondo del micrófono */}
            <button
              className={`listen ${state.kind === "recording" ? "active" : ""}`}
              onClick={state.kind === "recording" ? () => abortRef.current?.abort() : listen}
              disabled={state.kind === "processing"}
              aria-label={state.kind === "recording" ? "Cancelar grabación" : "Escuchar"}
            >
              <span className="pulse" />
              <img className="listen-img" src={listenIcon} alt="" />
            </button>
            
            {/* 2. Bloque de información con las 3 líneas alineado a la derecha del micro */}
            <div className="record-info-block">
              <p className="listen-label" aria-live="polite">
                {listenLabel}
              </p>
              
              <span id="duration-label" className="duration-label">
                Tiempo a grabar
              </span>
              
              <div className="segmented" role="radiogroup" aria-labelledby="duration-label">
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
            </div>
          </div>


          <div className="divider-v" role="separator" aria-orientation="vertical">
            <span>o</span>
          </div>

          <div className="input-upload">
            <label className={`btn btn-secondary ${busy ? "disabled" : ""}`}>
              Subir archivo
              <input
                type="file"
                accept="audio/*"
                className="visually-hidden"
                disabled={busy}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void fromFile(f);
                  e.target.value = "";
                }}
              />
            </label>
            <p className="input-note">mp3, wav, flac, ogg o m4a</p>
          </div>
        </div>
        
        <p className={`process-status ${state.kind === "processing" ? "busy" : "ok"}`} role="status" aria-live="polite">
          {state.kind === "processing" ? "Procesando…" : showDone ? "✓ Proceso terminado" : ""}
        </p>

        <p className="tip">
          Reproduce una canción de la biblioteca cerca del micrófono (10–30 cm). Apunta a un nivel entre −35 y −15
          dBFS.
        </p>
      </section>

      {source !== "file" && (
        <>
          {/* Barra de progreso entre las tarjetas; se oculta sin quitar su espacio */}
          <progress
            value={state.kind === "recording" ? state.progress : 0}
            max={1}
            className={`mid-progress-bar ${state.kind === "recording" ? "" : "idle"}`}
            aria-label="Progreso de la grabación"
          />
          <AnalysisCard
            origin={origin}
            analyser={state.kind === "recording" ? analyser : null}
            analysis={analysis}
            meter={<LevelMeter dbfs={state.kind === "recording" ? level : null} vertical icon={volumeIcon} />}
          />
        </>
      )}
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

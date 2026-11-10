import { useEffect, useState, type ReactNode } from "react";
import type { Analysis } from "../api";
import { ConstellationView } from "./ConstellationView";
import { LiveSpectrogram } from "./LiveSpectrogram";
import { LiveSpectrum } from "./LiveSpectrum";

interface Props {
  origin: string; // de dónde viene lo que se ve, p. ej. "Micrófono · 5 s"
  analyser: AnalyserNode | null; // activo solo mientras se graba
  analysis: Analysis | null; // llega con la respuesta del servidor
  meter?: ReactNode; // medidor de nivel: va a la derecha de las gráficas
}

export function AnalysisCard({ origin, analyser, analysis, meter }: Props) {
  const [showConstellation, setShowConstellation] = useState(false);

  // Cada análisis nuevo (o su ausencia al empezar otra grabación) cierra la constelación.
  useEffect(() => {
    setShowConstellation(false);
  }, [analysis]);

  return (
    <section className="card">
      <div className="analysis-head">
        <h2 className="step-title">2 · Análisis</h2>
        <span className="origin-badge">{origin}</span>
      </div>

      <div className="analysis-layout">
        <div className="graphs">
          <LiveSpectrogram analyser={analyser} />
          <LiveSpectrum analyser={analyser} />
        </div>
        {meter}
      </div>

      <div className="analysis-actions">
        <button
          className="btn btn-secondary"
          disabled={!analysis}
          aria-expanded={showConstellation}
          onClick={() => setShowConstellation((v) => !v)}
        >
          {showConstellation ? "Ocultar constelación" : "Ver constelación"}
        </button>
        {!analysis && <span className="tip-inline">Disponible al terminar la grabación</span>}
      </div>

      {analysis && showConstellation && (
        <div className="analysis-constellation">
          <ConstellationView analysis={analysis} />
        </div>
      )}
    </section>
  );
}

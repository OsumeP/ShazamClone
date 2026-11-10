import { useState, type KeyboardEvent } from "react";
import { LiveSpectrogram } from "./LiveSpectrogram";
import { LiveSpectrum } from "./LiveSpectrum";

type TabId = "spectrogram" | "spectrum" | "constellation";

const TABS: { id: TabId; label: string }[] = [
  { id: "spectrogram", label: "Espectrograma" },
  { id: "spectrum", label: "Espectro" },
  { id: "constellation", label: "Constelación" },
];

// Los tres paneles se mantienen montados (solo se ocultan): así el espectrograma
// conserva lo dibujado al cambiar de pestaña.
export function VisualTabs({ analyser }: { analyser: AnalyserNode | null }) {
  const [tab, setTab] = useState<TabId>("spectrogram");

  function select(id: TabId) {
    setTab(id);
    document.getElementById(`tab-${id}`)?.focus();
  }

  function onKeyDown(e: KeyboardEvent) {
    const i = TABS.findIndex((t) => t.id === tab);
    if (e.key === "ArrowRight") select(TABS[(i + 1) % TABS.length].id);
    else if (e.key === "ArrowLeft") select(TABS[(i - 1 + TABS.length) % TABS.length].id);
  }

  return (
    <div className="viz">
      <div className="viz-tabs" role="tablist" aria-label="Vista de las gráficas" onKeyDown={onKeyDown}>
        {TABS.map((t) => (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            role="tab"
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className={tab === t.id ? "selected" : ""}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div id="panel-spectrogram" role="tabpanel" aria-labelledby="tab-spectrogram" hidden={tab !== "spectrogram"}>
        <LiveSpectrogram analyser={analyser} />
      </div>
      <div id="panel-spectrum" role="tabpanel" aria-labelledby="tab-spectrum" hidden={tab !== "spectrum"}>
        <LiveSpectrum analyser={analyser} />
      </div>
      <div id="panel-constellation" role="tabpanel" aria-labelledby="tab-constellation" hidden={tab !== "constellation"}>
        <figure className="spectrogram">
          <div className="viz-empty">La constelación de picos se mostrará aquí al terminar de grabar.</div>
          <figcaption>Constelación: los picos del espectrograma que se convierten en hashes</figcaption>
        </figure>
      </div>
    </div>
  );
}

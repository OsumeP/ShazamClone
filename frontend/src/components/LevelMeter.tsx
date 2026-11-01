// Medidor de nivel en dBFS. La Fase 6 mostró que con nivel bajo (< −50 dBFS)
// el ruido propio del micrófono tapa los picos: el medidor guía al usuario.

const MIN_DB = -70;

export function levelHint(dbfs: number, peak?: number): { tone: "ok" | "warn" | "bad"; text: string } {
  if (peak !== undefined && peak >= 0.99) return { tone: "bad", text: "Saturación: aleja el micrófono o baja el volumen" };
  if (dbfs < -55) return { tone: "bad", text: "Señal muy débil: acerca el parlante o sube el volumen" };
  if (dbfs < -40) return { tone: "warn", text: "Señal baja: conviene acercar el parlante" };
  return { tone: "ok", text: "Buen nivel" };
}

export function LevelMeter({ dbfs }: { dbfs: number | null }) {
  const value = dbfs ?? MIN_DB;
  const pct = Math.max(0, Math.min(100, ((value - MIN_DB) / -MIN_DB) * 100));
  const hint = levelHint(value);
  return (
    <div className="level">
      <div className="level-bar">
        <div className={`level-fill ${hint.tone}`} style={{ width: `${pct}%` }} />
        <div className="level-target" title="Zona recomendada: −35 a −15 dBFS" />
      </div>
      <span className="level-label">{dbfs === null ? "— dBFS" : `${value.toFixed(1)} dBFS`}</span>
    </div>
  );
}

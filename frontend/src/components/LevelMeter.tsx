// Medidor de nivel en dBFS. La Fase 6 mostró que con nivel bajo (< −50 dBFS)
// el ruido propio del micrófono tapa los picos: el medidor guía al usuario.

const MIN_DB = -70;

export function levelHint(dbfs: number, peak?: number): { tone: "ok" | "warn" | "bad"; text: string } {
  if (peak !== undefined && peak >= 0.99) return { tone: "bad", text: "Saturación: aleja el micrófono o baja el volumen" };
  if (dbfs < -55) return { tone: "bad", text: "Señal muy débil: acerca el parlante o sube el volumen" };
  if (dbfs < -40) return { tone: "warn", text: "Señal baja: conviene acercar el parlante" };
  return { tone: "ok", text: "Buen nivel" };
}

// En vertical el nivel sube de abajo hacia arriba (altura); en horizontal crece a la derecha (ancho).
export function LevelMeter({ dbfs, vertical = false, icon }: { dbfs: number | null; vertical?: boolean; icon?: string }) {
  const value = dbfs ?? MIN_DB;
  const pct = Math.max(0, Math.min(100, ((value - MIN_DB) / -MIN_DB) * 100));
  const hint = levelHint(value);
  const label = dbfs === null ? "— dBFS" : `${value.toFixed(vertical ? 0 : 1)} dBFS`;
  return (
    <div className={`level ${vertical ? "vertical" : ""}`}>
      <div className="level-bar">
        <div className={`level-fill ${hint.tone}`} style={vertical ? { height: `${pct}%` } : { width: `${pct}%` }} />
        <div className="level-target" title="Zona recomendada: −35 a −15 dBFS" />
      </div>
      {vertical && icon && <img className="level-icon" src={icon} alt="" />}
      <span className="level-label">{label}</span>
    </div>
  );
}

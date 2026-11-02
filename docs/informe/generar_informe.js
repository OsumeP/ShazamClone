// Genera docs/Informe_ShazamClone.docx (Fase 8.4).
//
// Uso (desde docs/informe/):
//   npm install                 # una vez: instala docx
//   npm run build               # escribe ../Informe_ShazamClone.docx
//
// Después, abrir el documento en Word y actualizar el índice
// (clic derecho sobre el índice > Actualizar campos > Actualizar toda la tabla).
// Las figuras se leen de docs/figures/; las cifras están escritas en este
// archivo a partir de docs/DOCUMENTACION.md. Si cambian los resultados, hay
// que actualizarlas aquí. Las tablas y figuras se numeran solas, pero las
// referencias en el texto ("Tabla 6", "Figura 5") se escriben a mano.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, ImageRun, PageBreak, Header, Footer, PageNumber, TableOfContents,
  LevelFormat, BorderStyle, TabStopType,
} = require("docx");

const REPO = path.resolve(__dirname, "..", "..");
const FIG = path.join(REPO, "docs", "figures");
const OUT = path.join(REPO, "docs", "Informe_ShazamClone.docx");
const CONTENT_DXA = 11906 - 2 * 1440; // A4 con márgenes de 1"
const CONTENT_PX = Math.round((CONTENT_DXA / 1440) * 96);
const FONT = "Calibri";

// ---------------------------------------------------------------- utilidades
function runs(text, base = {}) {
  // **negrita**, *cursiva*, `código`
  // además: _{subíndice} y ^{superíndice}
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|_\{[^}]+\}|\^\{[^}]+\})/g).filter(Boolean);
  return parts.map((s) => {
    if (s.startsWith("**")) return new TextRun({ ...base, text: s.slice(2, -2), bold: true });
    if (s.startsWith("`")) return new TextRun({ ...base, text: s.slice(1, -1), font: "Consolas", size: 19 });
    if (s.startsWith("_{")) return new TextRun({ ...base, text: s.slice(2, -1), subScript: true });
    if (s.startsWith("^{")) return new TextRun({ ...base, text: s.slice(2, -1), superScript: true });
    if (s.startsWith("*") && s.length > 2) return new TextRun({ ...base, text: s.slice(1, -1), italics: true });
    return new TextRun({ ...base, text: s });
  });
}
const p = (text, opts = {}) =>
  new Paragraph({ children: runs(text), alignment: AlignmentType.JUSTIFIED, spacing: { after: 120, line: 276 }, ...opts });
const h1 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_1 });
const h2 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_2 });
const h3 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_3 });
const bullet = (text, level = 0) =>
  new Paragraph({ children: runs(text), numbering: { reference: "bullets", level }, spacing: { after: 60, line: 276 }, alignment: AlignmentType.JUSTIFIED });
// Cada lista numerada usa su propia referencia para reiniciar en 1.
const numbered = (text, reference = "numbers") =>
  new Paragraph({ children: runs(text), numbering: { reference, level: 0 }, spacing: { after: 60, line: 276 }, alignment: AlignmentType.JUSTIFIED });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// Ecuación: segmentos "texto" | {sub: "…"} | {sup: "…"}; numerada a la derecha.
let eqCount = 0;
function eq(segments) {
  eqCount += 1;
  const r = segments.map((s) =>
    typeof s === "string"
      ? new TextRun({ text: s, font: "Cambria Math", italics: true, size: 23 })
      : new TextRun({ text: s.sub ?? s.sup, font: "Cambria Math", italics: true, size: 23, subScript: !!s.sub, superScript: !!s.sup }),
  );
  return new Paragraph({
    children: [new TextRun({ text: "\t" }), ...r, new TextRun({ text: `\t(${eqCount})`, size: 22 })],
    tabStops: [
      { type: TabStopType.CENTER, position: Math.round(CONTENT_DXA / 2) },
      { type: TabStopType.RIGHT, position: CONTENT_DXA },
    ],
    spacing: { before: 80, after: 120 },
  });
}

let tableCount = 0;
let figureCount = 0;
const caption = (text, keepNext = false) =>
  new Paragraph({
    children: runs(text, { size: 19, italics: false }),
    alignment: AlignmentType.CENTER,
    spacing: { before: 60, after: 160 },
    keepNext,
  });

function table(title, headers, rows, weights, { fontSize = 18, firstColLeft = true } = {}) {
  tableCount += 1;
  const total = weights.reduce((a, b) => a + b, 0);
  const widths = weights.map((w) => Math.floor((w / total) * CONTENT_DXA));
  widths[widths.length - 1] += CONTENT_DXA - widths.reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: "A6A6A6" };
  const borders = { top: border, bottom: border, left: border, right: border };
  // keepNext en todas las filas menos la última: Word mantiene la tabla en una página
  const cell = (text, i, header, shade, keepNext = true) =>
    new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      borders,
      shading: header ? { type: ShadingType.CLEAR, color: "auto", fill: "D9E2F3" } : shade ? { type: ShadingType.CLEAR, color: "auto", fill: "F2F2F2" } : undefined,
      margins: { top: 40, bottom: 40, left: 80, right: 80 },
      children: [
        new Paragraph({
          children: runs(String(text), { size: fontSize, bold: header || undefined }),
          alignment: header ? AlignmentType.CENTER : i === 0 && firstColLeft ? AlignmentType.LEFT : AlignmentType.CENTER,
          keepNext,
        }),
      ],
    });
  return [
    caption(`**Tabla ${tableCount}.** ${title}`, true),
    new Table({
      width: { size: CONTENT_DXA, type: WidthType.DXA },
      columnWidths: widths,
      rows: [
        new TableRow({ tableHeader: true, cantSplit: true, children: headers.map((h, i) => cell(h, i, true)) }),
        ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false, ri % 2 === 1, ri < rows.length - 1)) })),
      ],
    }),
    new Paragraph({ spacing: { after: 120 }, children: [] }),
  ];
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function figure(file, text, widthFrac = 1) {
  figureCount += 1;
  const full = path.join(FIG, file);
  const { w, h } = pngSize(full);
  const width = Math.round(CONTENT_PX * widthFrac);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      keepNext: true,
      spacing: { before: 120 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(full), transformation: { width, height: Math.round((width * h) / w) } })],
    }),
    caption(`**Figura ${figureCount}.** ${text}`),
  ];
}

// ---------------------------------------------------------------- contenido
const portada = [
  new Paragraph({ spacing: { before: 1200 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Universidad Nacional de Colombia — Sede Bogotá", size: 26, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Facultad de Ingeniería", size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 1400 }, children: [new TextRun({ text: "Teoría de la Información y Sistemas de Comunicación — 2026-II", size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 300 }, children: [new TextRun({ text: "Sistema de Reconocimiento y Codificación de Huellas Acústicas mediante la Transformada de Fourier de Tiempo Reducido (STFT)", size: 40, bold: true, color: "1F3864" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 1600 }, children: [new TextRun({ text: "Informe técnico", size: 28, italics: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Juan David Patarroyo Sánchez", size: 26 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [new TextRun({ text: "Laura Natalia Duarte Acero", size: 26 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Profesor: Oswaldo Rojas Camacho", size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Bogotá, noviembre de 2026", size: 24 })] }),
  pageBreak(),
];

const resumen = [
  h1("Resumen"),
  p("Este informe presenta el diseño, la implementación y la evaluación de un sistema de identificación de música a partir de grabaciones cortas tomadas con un micrófono, inspirado en el algoritmo de Shazam. La señal se normaliza a 44.1 kHz y se descompone en el plano tiempo-frecuencia con la Transformada de Fourier de Tiempo Reducido (STFT). Del espectrograma se extrae un **mapa de constelación** con los máximos locales de energía y, a partir de pares de picos, se generan **hashes combinatorios** de 32 bits que codifican dos frecuencias y su separación temporal. La identificación se decide por **coherencia temporal**: las coincidencias verdaderas comparten un mismo desfase entre la grabación y la canción."),
  p("Con una biblioteca de 20 canciones, la huella ocupa el **2.56 %** del audio original sin comprimir. Se reconocieron 400 de 400 fragmentos limpios de 5 y 10 s, y con ruido moderado (SNR ≥ 5 dB) el acierto fue de **al menos 98 %** para cuatro tipos de ruido, sin falsos positivos en 1 000 consultas de canciones ajenas. La latencia máxima de procesamiento fue de 456 ms. Desde la Teoría de la Información se muestra que el filtrado por picos resiste el ruido de energía dispersa (alta entropía espectral), pero es más vulnerable a interferencias estructuradas como el murmullo de voces. La supervivencia de un hash es aproximadamente el cuadrado de la de un pico, y la capacidad del canal, aun a −5 dB, supera en más de dos órdenes de magnitud la información necesaria para identificar una canción."),
  new Paragraph({ spacing: { before: 120, after: 240 }, children: runs("**Palabras clave:** huella acústica, STFT, espectrograma, mapa de constelación, hashing, entropía de Shannon, capacidad de canal, reconocimiento de audio.") }),
  pageBreak(),
  new Paragraph({ children: [new TextRun({ text: "Contenido", bold: true, size: 32, color: "1F3864" })], spacing: { after: 200 } }),
  new TableOfContents("Contenido", { hyperlink: true, headingStyleRange: "1-2" }),
  pageBreak(),
];

const introduccion = [
  h1("1. Introducción"),
  p("Identificar una canción a partir de unos pocos segundos captados por un micrófono en un entorno ruidoso es un problema clásico de comunicación: la música (la fuente) viaja por el aire (un canal con ruido, reverberación y distorsión) hasta un micrófono (el receptor), y el sistema debe recuperar la información que la identifica. Comparar formas de onda directamente es inviable: cualquier cambio de volumen, desfase o ruido destruye la correspondencia muestra a muestra. El enfoque de Wang [1] propone, en cambio, extraer una **huella acústica**: una representación compacta, basada en los picos de energía del espectrograma, que se conserva aunque el canal degrade la señal."),
  h2("1.1 Objetivo general"),
  p("Diseñar e implementar un sistema digital de identificación de señales de audio en tiempo real basado en la extracción de huellas acústicas mediante la Transformada de Fourier, y evaluar su robustez ante el ruido ambiental bajo los principios de la Teoría de la Información de Shannon."),
  h2("1.2 Objetivos específicos"),
  numbered("Descomponer señales de audio musicales en el dominio tiempo-frecuencia mediante la STFT para generar espectrogramas."),
  numbered("Implementar un algoritmo de reducción de datos que extraiga los picos espectrales de máxima energía (mapa de constelación) y minimice el almacenamiento."),
  numbered("Desarrollar un módulo de comparación por hashing que contraste muestras ruidosas en tiempo real contra la base de datos."),
  numbered("Identificar y retornar la canción correcta en tiempo real con alta coherencia temporal."),
  h2("1.3 Requerimientos"),
  p("Los requerimientos funcionales cubren la carga de archivos `.wav`/`.mp3` (RF1), el análisis STFT (RF2), la generación de huellas con distancias temporales Δt (RF3), la captura por micrófono en ráfagas de 5 a 10 s (RF4) y el matching (RF5). Los no funcionales exigen muestreo de al menos 44.1 kHz (RNF1), una huella de no más del 5 % del audio original (RNF2), respuesta en menos de 3 s (RNF3), acierto superior al 80 % con ruido moderado (RNF4) y ejecución en Python con herramientas abiertas, sin GPU (RNF5)."),
  p("Para que estos requerimientos fueran verificables se fijaron tres criterios: el tamaño de la huella se compara con el **WAV normalizado** (44.1 kHz, mono, PCM de 16 bits); la latencia se mide **desde el fin de la grabación** hasta la respuesta; y el ruido moderado corresponde a una **SNR ≥ 5 dB**."),
];

const marco = [
  h1("2. Marco teórico"),
  h2("2.1 Muestreo y criterio de Nyquist"),
  p("Una señal continua de banda limitada a f_{max} puede reconstruirse a partir de sus muestras si la frecuencia de muestreo cumple"),
  eq(["f", { sub: "s" }, " ≥ 2 · f", { sub: "max" }]),
  p("Como el oído humano percibe hasta unos 20 kHz, se adopta f_{s} = 44.1 kHz, con frecuencia de Nyquist de 22.05 kHz. Todo el audio que entra al sistema, sea una canción de la biblioteca o una grabación, se normaliza a esa frecuencia, a un solo canal y a valores en [−1, 1]."),
  h2("2.2 Transformada Discreta de Fourier y STFT"),
  p("La DFT de N muestras transforma la señal al dominio de la frecuencia:"),
  eq(["X[k] = Σ", { sub: "n=0" }, { sup: "N−1" }, " x[n] · e", { sup: "−j2πkn/N" }, ",   k = 0, 1, …, N−1"]),
  p("La música no es estacionaria: su contenido espectral cambia nota a nota. La STFT aplica la DFT sobre ventanas deslizantes w[n] desplazadas un salto R:"),
  eq(["X(m, k) = Σ", { sub: "n" }, " x[n] · w[n − mR] · e", { sup: "−j2πkn/N" }]),
  p("donde m es el índice de la ventana. La resolución en frecuencia es Δf = f_{s}/N y la temporal es R/f_{s}. El **espectrograma** es la potencia de la STFT, que se expresa en decibelios para comprimir su rango dinámico:"),
  eq(["S", { sub: "dB" }, "(m, k) = 10 · log", { sub: "10" }, "( |X(m, k)|", { sup: "2" }, " + ε )"]),
  p("En escala logarítmica, un cambio de volumen equivale a sumar una constante a todo el espectrograma, propiedad que el sistema aprovecha para ser invariante a la ganancia del micrófono."),
  h2("2.3 Entropía de Shannon"),
  p("La entropía mide la incertidumbre de una variable aleatoria:"),
  eq(["H(X) = − Σ", { sub: "i" }, " p(x", { sub: "i" }, ") · log", { sub: "2" }, " p(x", { sub: "i" }, ")"]),
  p("Si se normaliza el espectro de potencia de una ventana como una distribución de probabilidad, p_{k} = S(m,k) / Σ_{k} S(m,k), su entropía describe qué tan concentrada está la energía. Un tono puro o una música con pocos armónicos dominantes tiene **entropía espectral baja**; el ruido blanco, con su energía repartida uniformemente, tiene **entropía máxima**. En este trabajo se usa la versión normalizada H/log₂K ∈ [0, 1], donde K es el número de bins considerados."),
  h2("2.4 Capacidad del canal"),
  p("El teorema de Shannon-Hartley establece la tasa máxima de información que puede transmitirse sin error por un canal de ancho de banda B con relación señal a ruido S/N:"),
  eq(["C = B · log", { sub: "2" }, "(1 + S/N)   [bit/s]"]),
  p("El modelo del canal en este problema es *fuente (música) → aire con ruido → micrófono → procesamiento digital*. La pregunta de fondo es cuánta de la información identificadora de una canción sobrevive a ese canal y qué representación la extrae mejor."),
  h2("2.5 Huellas acústicas por constelación (Wang, 2003)"),
  p("Wang [1] propone tres ideas que este sistema implementa: (i) reducir el espectrograma a sus picos de máxima energía, que son los puntos con mayor probabilidad de sobrevivir al ruido; (ii) combinar pares de picos en hashes (f₁, f₂, Δt), mucho más específicos que un pico aislado e invariantes a desplazamientos en el tiempo; y (iii) decidir la identidad por la coherencia temporal de las coincidencias, que deben compartir un mismo desfase entre la grabación y la canción. La implementación abierta *Dejavu* [2] sirvió como referencia práctica."),
];

const diseno = [
  h1("3. Diseño e implementación"),
  p("El sistema se divide en dos procesos que comparten el mismo núcleo de procesamiento de señales (Figura 1): la **ingesta**, que se ejecuta una vez por canción y almacena sus huellas, y la **consulta**, que procesa una grabación y la contrasta con la base de datos. Usar exactamente el mismo código en ambos caminos garantiza que una canción y un fragmento suyo produzcan huellas comparables."),
  ...figure("diagrama_sistema.png", "Diagrama de bloques del sistema: ingesta (arriba) y consulta en tiempo real (abajo)."),
  p("La implementación usa Python con numpy, scipy y soundfile para el procesamiento de señales, SQLite como base de datos, FastAPI para la API REST y React con TypeScript (Vite) para la interfaz web. Todo corre en CPU. La Tabla 1 resume los parámetros finales."),
  ...table(
    "Parámetros finales del sistema.",
    ["Etapa", "Parámetro", "Valor", "Justificación"],
    [
      ["Normalización", "f_{s}, canales", "44.1 kHz, mono", "Criterio de Nyquist (RNF1)"],
      ["STFT", "Ventana, N, R", "Hann, 4096, 2048", "Δf ≈ 10.8 Hz; ≈ 46 ms entre ventanas"],
      ["Constelación", "Banda de búsqueda", "60 Hz – 5 kHz", "Concentra la energía armónica"],
      ["Constelación", "Vecindario", "15 × 15", "≈ 161 Hz × 0.7 s; ajustado en la evaluación"],
      ["Constelación", "Umbral", "mediana de la ventana + 10 dB", "Invariante a la ganancia y local en el tiempo"],
      ["Hashing", "Fan-out, zona Δt", "10 pares, 1–63 ventanas", "Hasta ≈ 2.9 s entre ancla y objetivo"],
      ["Hashing", "Codificación", "f₁ (10) + f₂ (10) + Δt (12) bits", "Cabe en un entero de 32 bits"],
      ["Matching", "Regla de decisión", "score ≥ 10 y ≥ 2 × segundo", "Calibrada con canciones fuera de la BD"],
    ],
    [2.2, 2.2, 3, 4],
  ),
  h2("3.1 Normalización y STFT"),
  p("Los archivos WAV, FLAC y OGG se leen con soundfile; MP3 y otros formatos se decodifican con FFmpeg a su frecuencia original. La mezcla a mono y el remuestreo polifásico con filtro anti-aliasing (`resample_poly`) se hacen siempre en Python, de modo que el procesamiento no depende del formato de origen. La STFT se implementó con numpy (ventaneo con vistas de memoria y `rfft`) y se validó contra `scipy.signal.ShortTimeFFT`: las magnitudes coinciden con un error relativo de 10⁻⁷. Las fases difieren en un factor (−1)^{k} porque scipy mide la fase respecto al centro de cada ventana, un desplazamiento de N/2 muestras. La Figura 2 muestra el espectrograma de un fragmento: las líneas horizontales son los armónicos de la melodía y las verticales, los golpes de percusión."),
  ...figure("espectrograma_Petit Biscuit - Sunset Lover.png", "Espectrograma en dB de *Sunset Lover* (Petit Biscuit), 60–70 s, banda 0–5 kHz."),
  h2("3.2 Mapa de constelación"),
  p("Un punto (m, k) del espectrograma es pico si es el máximo de su vecindario de 15 bins × 15 ventanas y supera en al menos 10 dB la **mediana de su propia ventana**. Ambas condiciones son relativas: sumar una constante a S_{dB} (cambiar el volumen) no altera los picos. Durante el desarrollo se detectó que un umbral basado en la mediana de *todo* el espectrograma hacía que una canción completa y un fragmento suyo produjeran picos distintos: la introducción de *Bad Apple* tiene una mediana 16 dB menor que la del resto de la canción, y su fragmento generaba 157 picos frente a 35 en la canción completa. El umbral por ventana resuelve el problema porque solo depende del contenido de esa ventana, que es idéntico en ambos casos."),
  p("Esta etapa es la **reducción de datos** que pide el segundo objetivo: de unos 176 000 B/s de espectrograma se pasa a unos 25 puntos por segundo (Figura 3). El piso de ruido, de energía dispersa, queda casi por completo bajo el umbral."),
  ...figure("constelacion_Petit Biscuit - Sunset Lover.png", "Arriba: mapa de constelación sobre el espectrograma. Abajo: pares ancla → objetivo usados para formar hashes."),
  h2("3.3 Hashing combinatorio"),
  p("Cada pico actúa como ancla (t₁, f₁) y se empareja con los siguientes diez picos cuya separación Δt = t₂ − t₁ esté entre 1 y 63 ventanas. Cada par produce"),
  eq(["hash = f", { sub: "1" }, " · 2", { sup: "22" }, " + f", { sub: "2" }, " · 2", { sup: "12" }, " + Δt,     offset = t", { sub: "1" }]),
  p("El hash solo contiene diferencias de tiempo, así que un fragmento que empieza en la ventana s de la canción produce los mismos hashes con offset desplazado en −s. Un hash combina tres valores (unos 30 bits efectivos) en lugar de uno (unos 10 bits), lo que hace muy improbables las coincidencias casuales. A cambio, un hash solo sobrevive al ruido si sobreviven sus dos picos."),
  h2("3.4 Almacenamiento"),
  p("Las huellas se guardan en SQLite en una tabla `fingerprints(hash, song_id, offset_frame)` declarada `WITHOUT ROWID`, con clave primaria (hash, song_id, offset_frame). La tabla queda ordenada por hash en un árbol B y funciona a la vez como índice, sin duplicar los datos en un índice secundario. Cada archivo se identifica por su SHA-1, de modo que repetir la ingesta no duplica canciones. Los metadatos se toman, en orden de prioridad, de un archivo `metadata.json` manual, del nombre del archivo (`Artista - Título`) y de los tags del archivo. Los tags se dejaron al final porque en el corpus real traían el nombre de quien subió el audio a internet en lugar del artista."),
  h2("3.5 Matching y coherencia temporal"),
  p("Los hashes de la grabación se buscan en la base de datos con una tabla temporal y un JOIN sobre la clave primaria. Para cada coincidencia se calcula Δ = t_{canción} − t_{fragmento}. Si la grabación proviene de una canción, sus coincidencias verdaderas comparten el mismo Δ y forman una recta de pendiente 1 en el plano (t_{fragmento}, t_{canción}); las coincidencias casuales con otras canciones se dispersan (Figura 4). La puntuación de cada canción es la altura del pico de su histograma de Δ, sumando el bin vecino para tolerar el desalineamiento de hasta R/2 entre las ventanas de la grabación y las de la canción. Ese Δ indica además dónde empieza el fragmento dentro de la canción. Se acepta el mejor candidato si alcanza 10 coincidencias alineadas y al menos el doble que el segundo."),
  ...figure("matching_Linkin Park - Crawling.png", "Coherencia temporal para un fragmento de 10 s de *Crawling*. Arriba: canción correcta (recta de pendiente 1 y pico de 1016 en el histograma). Abajo: segunda candidata (coincidencias dispersas, pico de 4). El pico secundario cerca de 128 s corresponde al estribillo repetido."),
  h2("3.6 Captura en tiempo real, API e interfaz"),
  p("La captura por micrófono existe en dos formas: un script de línea de comandos (sounddevice) y la aplicación web. En el navegador se piden las restricciones `echoCancellation`, `noiseSuppression` y `autoGainControl` en falso, porque ese procesamiento altera los picos espectrales. El audio se toma como PCM sin compresión mediante un *AudioWorklet*, en lugar de `MediaRecorder`, que usaría un códec con pérdidas. El navegador envía un WAV de 16 bits a su frecuencia nativa (normalmente 48 kHz) y el servidor lo remuestrea a 44.1 kHz con el mismo filtro que usa para las canciones. La interfaz muestra un espectrograma en vivo, un medidor de nivel en dBFS, la canción reconocida con su posición, la latencia desde el fin de la grabación y un diagnóstico de la captura. La API (FastAPI) expone `/api/recognize`, `/api/songs`, `/api/ingest` y `/api/health`."),
];

const metodologia = [
  h1("4. Metodología de evaluación"),
  bullet("**Corpus:** 20 canciones propias en MP3 (80.8 min), de géneros variados: pop, rock, electrónica y bandas sonoras de anime, incluidos títulos en japonés. Normalizadas ocupan 427.5 MB en WAV."),
  bullet("**Consultas positivas:** fragmentos de 5 y 10 s tomados en posiciones aleatorias con resolución de una muestra, de modo que casi nunca coinciden con el inicio de una ventana de la STFT."),
  bullet("**Consultas negativas:** se construyó una base de datos temporal sin 1 de cada 4 canciones y se consultaron fragmentos de las 5 excluidas. Lo correcto es responder *no reconocida*; cualquier aceptación es un falso positivo."),
  bullet("**Canal ruidoso simulado:** a los mismos fragmentos se les sumó ruido blanco, rosa (1/f), marrón (1/f²) o murmullo de voces a SNR de 20, 10, 5, 0 y −5 dB, con SNR = 10·log₁₀(P_{señal}/P_{ruido}) sobre todo el fragmento. El murmullo se sintetizó con seis voces, cada una formada por una serie armónica de frecuencia fundamental variable (100–250 Hz) y ruido en la banda vocal, moduladas por una envolvente silábica de unos 4 Hz."),
  bullet("**Canal real:** una canción reproducida desde el parlante de un celular y captada por el micrófono del computador, tanto con el script como con la aplicación web."),
  bullet("**Latencia:** medida desde que el audio está disponible (fin de la grabación) hasta el resultado."),
];

const resultados = [
  h1("5. Resultados"),
  h2("5.1 Tamaño de la huella (RNF2)"),
  p("Con la configuración final se obtienen 24.8 picos y 226 hashes por segundo de audio. La Tabla 2 muestra cómo evolucionó el tamaño a lo largo del desarrollo. Incluso el archivo completo de SQLite, con la estructura del árbol B, queda por debajo del 5 %."),
  ...table(
    "Tamaño de la huella frente al WAV normalizado (427.5 MB) para las 20 canciones.",
    ["Configuración", "Hashes", "Huella lógica (10 B/hash)", "Archivo SQLite"],
    [
      ["21×21, umbral global", "737 321", "7.37 MB — 1.72 %", "11.35 MB — 2.65 %"],
      ["21×21, umbral por ventana", "649 001", "6.49 MB — 1.52 %", "9.95 MB — 2.33 %"],
      ["**15×15, umbral por ventana (final)**", "**1 094 427**", "**10.94 MB — 2.56 %**", "**16.80 MB — 3.93 %**"],
    ],
    [3.4, 1.6, 2.6, 2.6],
  ),
  p("La canción con la huella más densa llega al 3.06 %. En términos de tasa de información, la huella de una consulta equivale a unos 7.2 kbit/s, frente a 705.6 kbit/s del PCM de 16 bits: alrededor del 1 %."),
  h2("5.2 Reconocimiento con audio limpio"),
  ...table(
    "Reconocimiento de fragmentos limpios (200 consultas por fila) y latencia de procesamiento.",
    ["Configuración", "Duración", "Acierto", "Score mín.", "Score mediano", "Latencia mediana", "Latencia máx."],
    [
      ["21×21", "5 s", "100 %", "26", "186", "143 ms", "193 ms"],
      ["21×21", "10 s", "100 %", "57", "378", "170 ms", "235 ms"],
      ["**15×15 (final)**", "5 s", "**100 %**", "50", "342", "244 ms", "342 ms"],
      ["**15×15 (final)**", "10 s", "**100 %**", "145", "612", "279 ms", "373 ms"],
    ],
    [2.4, 1.2, 1.2, 1.3, 1.6, 1.8, 1.6],
  ),
  p("En las 100 consultas negativas no hubo falsos positivos; la puntuación máxima de una canción ajena fue 7. Cuando el sistema ubicó un fragmento en una posición distinta de la real, la canción siempre fue la correcta: ocurre en secciones repetidas de forma idéntica, como loops o estribillos, donde el fragmento existe realmente en varios lugares."),
  h2("5.3 Robustez ante ruido (RNF4)"),
  p("Se evaluaron 4 000 consultas positivas (20 canciones × 5 fragmentos × 4 ruidos × 5 SNR × 2 duraciones) y 1 000 negativas. Las Tablas 4 y 5 y la Figura 5 muestran el acierto."),
  ...table(
    "Acierto con fragmentos de 5 s según tipo de ruido y SNR.",
    ["Ruido", "20 dB", "10 dB", "5 dB", "0 dB", "−5 dB"],
    [
      ["Blanco", "100 %", "100 %", "**100 %**", "100 %", "94 %"],
      ["Rosa", "100 %", "100 %", "**99 %**", "96 %", "76 %"],
      ["Marrón", "100 %", "100 %", "**100 %**", "100 %", "99 %"],
      ["Murmullo de voces", "100 %", "99 %", "**98 %**", "82 %", "29 %"],
    ],
    [3, 1.4, 1.4, 1.4, 1.4, 1.4],
  ),
  ...table(
    "Acierto con fragmentos de 10 s según tipo de ruido y SNR.",
    ["Ruido", "20 dB", "10 dB", "5 dB", "0 dB", "−5 dB"],
    [
      ["Blanco", "100 %", "100 %", "**100 %**", "100 %", "100 %"],
      ["Rosa", "100 %", "100 %", "**100 %**", "100 %", "88 %"],
      ["Marrón", "100 %", "100 %", "**100 %**", "100 %", "100 %"],
      ["Murmullo de voces", "100 %", "100 %", "**100 %**", "97 %", "62 %"],
    ],
    [3, 1.4, 1.4, 1.4, 1.4, 1.4],
  ),
  ...figure("ruido_acierto_vs_snr.png", "Tasa de acierto en función de la SNR para cada tipo de ruido. La línea discontinua marca el requisito del 80 %."),
  p("Con ruido moderado (SNR ≥ 5 dB) el peor caso es 98 %, muy por encima del 80 % exigido, y el sistema supera ese umbral hasta 0 dB con todos los ruidos. No hubo falsos positivos en las 1 000 consultas negativas, cuya puntuación máxima fue 7. La Tabla 6 justifica el umbral de decisión: con 8 todavía no hay falsos positivos, pero se mantuvo 10 como margen de seguridad, a un costo de 0.1 puntos de acierto."),
  ...table(
    "Barrido del umbral de puntuación (consultas con ruido; decisión recalculada sobre los mismos resultados).",
    ["Umbral", "Acierto SNR ≥ 5 dB", "Acierto total", "Falsos positivos (de 1 000)"],
    [["5", "99.9 %", "96.4 %", "18"], ["6", "99.9 %", "96.4 %", "15"], ["8", "99.9 %", "96.0 %", "0"], ["**10 (elegido)**", "**99.8 %**", "**95.5 %**", "**0**"], ["15", "99.8 %", "93.6 %", "0"], ["20", "99.6 %", "92.0 %", "0"]],
    [2, 2.5, 2, 3],
  ),
  p("La latencia de procesamiento (RNF3) tuvo una mediana de 234 ms y un máximo de 456 ms en 4 998 consultas. Se excluyeron dos mediciones de más de 20 minutos que coincidieron con la suspensión del equipo, según el registro de eventos de Windows. A través de HTTP, la ida y vuelta completa no superó 747 ms."),
  h2("5.4 Ajuste de parámetros"),
  p("Para elegir la densidad de la huella se compararon configuraciones en condiciones difíciles, con fragmentos de 5 s (Tabla 7). Cada configuración requiere reconstruir la base de datos, por lo que se usaron 15 canciones en la BD, 240 consultas positivas y 80 negativas por configuración."),
  ...table(
    "Comparación de configuraciones en condiciones de ruido difíciles (fragmentos de 5 s).",
    ["Configuración", "Hashes/s", "% WAV", "Murmullo 0 dB", "Murmullo −5 dB", "Rosa −5 dB", "Blanco −5 dB"],
    [
      ["21×21, +10 dB, fan-out 10", "133", "1.51", "76.7 %", "20.0 %", "61.7 %", "93.3 %"],
      ["Umbral +15 dB", "101", "1.15", "68.3 %", "18.3 %", "36.7 %", "58.3 %"],
      ["Umbral +6 dB", "156", "1.77", "78.3 %", "28.3 %", "61.7 %", "83.3 %"],
      ["Fan-out 5", "63", "0.71", "53.3 %", "5.0 %", "40.0 %", "58.3 %"],
      ["Fan-out 15", "204", "2.31", "86.7 %", "30.0 %", "70.0 %", "96.7 %"],
      ["Vecindario 21×11", "229", "2.60", "88.3 %", "41.7 %", "76.7 %", "95.0 %"],
      ["**Vecindario 15×15 (elegida)**", "**227**", "**2.57**", "**90.0 %**", "38.3 %", "75.0 %", "95.0 %"],
      ["15×15, fan-out 15", "351", "3.98", "91.7 %", "48.3 %", "80.0 %", "98.3 %"],
    ],
    [3.4, 1.3, 1.1, 1.6, 1.6, 1.5, 1.5],
    { fontSize: 17 },
  ),
  p("Subir el umbral empeora todos los casos, porque se pierden picos verdaderos además de los de ruido. Aumentar la densidad de picos (vecindario más pequeño) rinde más que aumentar el fan-out con un tamaño de huella similar. Ninguna configuración produjo falsos positivos. Se eligió 15×15 con fan-out 10: las variantes más densas solo ganan a −5 dB, fuera del rango exigido, y acercan la huella al límite del 5 %."),
  h2("5.5 Análisis desde la Teoría de la Información"),
  h3("Entropía espectral: música frente a ruido"),
  ...table(
    "Entropía espectral normalizada por ventana (banda 60 Hz – 5 kHz).",
    ["Señal", "Mediana", "Percentil 10", "Percentil 90"],
    [["Música (20 canciones)", "**0.566**", "0.371", "0.714"], ["Ruido blanco", "0.931", "0.925", "0.937"], ["Ruido rosa", "0.822", "0.779", "0.855"], ["Ruido marrón", "0.544", "0.466", "0.613"], ["Murmullo de voces", "0.630", "0.561", "0.676"]],
    [3.5, 2, 2, 2],
  ),
  ...figure("entropia_espectral.png", "Distribución de la entropía espectral por ventana para la música y los cuatro ruidos.", 0.8),
  h3("Supervivencia de picos y hashes"),
  p("La Tabla 9 mide qué fracción de los picos y hashes de un fragmento limpio sigue presente, en la misma posición, después de sumar el ruido. También muestra la SNR efectiva dentro de la banda de análisis, que difiere de la global según cómo reparte cada ruido su potencia."),
  ...table(
    "SNR en la banda de análisis y supervivencia de picos y hashes (10 fragmentos de 10 s).",
    ["Ruido", "SNR global", "SNR en banda", "Picos", "Hashes"],
    [
      ["Blanco", "5 dB / 0 dB", "10.4 / 5.4 dB", "60 % / 42 %", "36 % / 18 %"],
      ["Rosa", "5 dB / 0 dB", "6.4 / 1.4 dB", "50 % / 31 %", "25 % / 10 %"],
      ["Marrón", "5 dB / 0 dB", "11.7 / 6.7 dB", "82 % / 70 %", "65 % / 49 %"],
      ["Murmullo", "5 dB / 0 dB", "3.9 / −1.1 dB", "46 % / 26 %", "22 % / 8 %"],
    ],
    [2.2, 2, 2.2, 2.2, 2.2],
  ),
  ...figure("canal_ruidoso_vs_snr.png", "Entropía de la mezcla y supervivencia de picos y hashes en función de la SNR."),
  h3("Capacidad del canal"),
  ...table(
    "Capacidad de Shannon-Hartley para la banda completa y para la banda de análisis con la SNR medida en esa banda.",
    ["SNR global", "C banda completa (22 050 Hz)", "C banda de análisis, rosa (4 940 Hz)", "Bits disponibles en 5 s"],
    [["20 dB", "146.8 kbit/s", "35.2 kbit/s", "176 039"], ["10 dB", "76.3 kbit/s", "19.3 kbit/s", "96 451"], ["5 dB", "45.4 kbit/s", "12.0 kbit/s", "59 969"], ["0 dB", "22.1 kbit/s", "6.2 kbit/s", "31 026"], ["−5 dB", "8.7 kbit/s", "2.6 kbit/s", "12 972"]],
    [2, 3, 3.4, 2.6],
  ),
  p("Identificar un par (canción, posición) entre las 104 364 ventanas de la base de datos requiere log₂(104 364) ≈ **16.7 bits**."),
  h2("5.6 Pruebas con micrófono real"),
  p("Una canción de la biblioteca (*Sunset Lover*) se reprodujo desde el parlante de un celular y se captó con el micrófono del computador (Tabla 11)."),
  ...table(
    "Pruebas acústicas reales con el script de línea de comandos y con la aplicación web.",
    ["Intento", "Micrófono / modo", "Nivel", "Resultado"],
    [
      ["1", "Externo, modo compartido", "−42.7 dBFS", "No reconocida (primera, score 8 < 10)"],
      ["2", "Externo, WASAPI exclusivo", "−58.6 dBFS", "No reconocida (score 4)"],
      ["3", "Integrado, más ganancia en Windows", "−49.8 dBFS", "**Reconocida** (score 23, 111 ms)"],
      ["Web", "Navegador (AudioWorklet)", "—", "**Reconocida**"],
    ],
    [1.2, 3.4, 1.8, 4.2],
  ),
  p("Para entender los fallos se analizó la grabación del intento 2. Su entropía espectral (0.52) y la prominencia de sus picos indican que la música sí llegó al micrófono. Sin embargo, frente a la canción original, los graves (< 300 Hz) llegaban entre 25 y 30 dB más débiles, porque el parlante del celular casi no los reproduce, y los agudos (> 2.5 kHz), donde están los golpes de percusión, quedaban bajo el ruido propio del micrófono. Se descartó un desajuste de velocidad o de versión de la canción. Para aislar las causas se simularon sobre audio limpio (Tabla 12)."),
  ...table(
    "Simulación de las degradaciones del canal real (10 canciones, fragmentos de 10 s).",
    ["Condición simulada", "Reconocidas", "Score mediano", "Score mínimo"],
    [["Limpio", "10/10", "565", "285"], ["Parlante de celular (pasa-banda 300 Hz – 4 kHz)", "10/10", "506", "193"], ["Reverberación (0.5 s)", "10/10", "100", "41"], ["Celular + reverberación", "10/10", "82", "46"], ["Celular + reverberación + ruido a 10 dB", "10/10", "77", "50"]],
    [4.6, 1.8, 1.8, 1.8],
  ),
  p("Ninguna degradación simulada impide el reconocimiento por sí sola. La causa decisiva en las pruebas reales fue el **nivel de grabación**: por debajo de unos −50 dBFS, el ruido propio del micrófono domina las bandas donde la música llega débil. Por eso la interfaz web incluye un medidor de nivel con la zona recomendada (−35 a −15 dBFS)."),
];

const discusion = [
  h1("6. Discusión"),
  h2("6.1 La hipótesis de la entropía, refinada"),
  p("El planteamiento inicial suponía que la música tiene baja entropía espectral y el ruido alta, y que filtrar los picos separa una del otro. Los resultados lo confirman para el ruido blanco (0.93) y el rosa (0.82), cuya energía dispersa queda bajo el umbral. Pero el ruido marrón tiene una entropía **menor** que la de la música (0.54) y aun así es el menos dañino: concentra su energía por debajo de 60 Hz, en el borde de la banda de análisis, sin tapar los picos del resto del espectro. Y el murmullo de voces, con entropía cercana a la de la música (0.63), es el **más** dañino: sus armónicos crean picos que compiten por los máximos locales y desplazan a los de la canción. La conclusión precisa es que el filtrado por picos resiste el ruido de energía dispersa y es vulnerable a interferencias estructuradas que comparten banda con la señal. Lo que importa no es solo la entropía del ruido, sino cuánto se parece a la señal y dónde concentra su energía."),
  h2("6.2 Especificidad frente a robustez en el hashing"),
  p("La supervivencia de los hashes es aproximadamente el cuadrado de la de los picos: con ruido blanco a 5 dB, 0.60² ≈ 0.36, lo que coincide con lo medido. Combinar dos picos multiplica la especificidad del hash, pero cada hash depende de que sobrevivan los dos. El sistema compensa ese costo con redundancia: un fragmento de 5 s produce unos 1 100 hashes, así que aunque sobreviva solo el 10 %, quedan del orden de 100 coincidencias alineadas, muy por encima del umbral de 10 y del ruido de fondo de las canciones ajenas, que nunca superó 7."),
  h2("6.3 Capacidad del canal frente a información necesaria"),
  p("A −5 dB, el canal puede transportar unos 13 000 bits en 5 s dentro de la banda de análisis, mientras que identificar una canción y su posición requiere unos 16.7 bits. Hay un margen de casi tres órdenes de magnitud. El límite práctico, entonces, no está en la capacidad del canal sino en la capacidad del algoritmo para extraer de forma consistente la parte de la señal que identifica a la canción. La huella hace justamente esa compresión: conserva unos 7 kbit/s de información identificadora y descarta timbre, fase y detalle espectral."),
  h2("6.4 Limitaciones"),
  bullet("El canal acústico real (parlante pequeño, reverberación, ganancia del micrófono) resultó más exigente que el ruido aditivo simulado. Los intentos con micrófono quedaron cerca del umbral cuando el nivel fue bajo."),
  bullet("El corpus tiene 20 canciones. La tasa de falsos positivos y el umbral de decisión se calibraron con 5 canciones fuera de la base de datos; con una biblioteca mucho mayor convendría recalibrarlos."),
  bullet("En secciones repetidas de forma idéntica, la posición estimada puede corresponder a otra repetición, aunque la canción se identifique bien."),
  bullet("El ambiente ruidoso de la evaluación principal es simulado; las pruebas en entornos reales se registran con una herramienta de pruebas de campo."),
];

const conclusiones = [
  h1("7. Conclusiones"),
  numbered("Se implementó un sistema completo de reconocimiento de música por huellas acústicas: STFT propia validada contra scipy, mapa de constelación, hashing combinatorio, almacenamiento en SQLite, matching por coherencia temporal, API REST e interfaz web con captura de micrófono sin procesamiento.", "conclusiones"),
  numbered("Se cumplen los cinco requerimientos no funcionales: muestreo a 44.1 kHz, huella del 2.56 % del audio original, latencia máxima de 456 ms, acierto de al menos 98 % con ruido moderado y ejecución en CPU con herramientas abiertas.", "conclusiones"),
  numbered("La reducción de datos es drástica: de 705.6 kbit/s de PCM a unos 7 kbit/s de huella, conservando la información necesaria para identificar la canción incluso a −5 dB.", "conclusiones"),
  numbered("El análisis de entropía muestra que el algoritmo resiste el ruido disperso, pero es vulnerable a interferencias con estructura armónica en la misma banda, como el murmullo de voces.", "conclusiones"),
  numbered("El umbral de picos debe ser local en el tiempo para que una canción completa y un fragmento suyo generen la misma huella; esta corrección fue clave para reconocer pasajes suaves.", "conclusiones"),
  numbered("En condiciones reales, el factor más importante resultó ser el nivel de grabación. Como trabajo futuro se propone ampliar el corpus y evaluar una huella más resistente a canales de banda limitada, usando las grabaciones de campo como banco de pruebas.", "conclusiones"),
];

const referencias = [
  h1("Referencias"),
  p("[1] A. Wang, “An Industrial-Strength Audio Search Algorithm,” en *Proc. 4th International Conference on Music Information Retrieval (ISMIR)*, Baltimore, 2003."),
  p("[2] W. Drevo, “Dejavu: Audio fingerprinting and recognition in Python,” 2014. [En línea]. Disponible: https://github.com/worldveil/dejavu"),
  p("[3] C. E. Shannon, “A Mathematical Theory of Communication,” *Bell System Technical Journal*, vol. 27, pp. 379–423, 623–656, 1948."),
  p("[4] C. E. Shannon, “Communication in the Presence of Noise,” *Proceedings of the IRE*, vol. 37, no. 1, pp. 10–21, 1949."),
  p("[5] A. V. Oppenheim y R. W. Schafer, *Discrete-Time Signal Processing*, 3.ª ed. Pearson, 2010."),
];

const anexo = [
  h1("Anexo A. Verificación de requerimientos"),
  ...table(
    "Estado de cada requerimiento y evidencia en el repositorio.",
    ["Req.", "Resultado", "Evidencia"],
    [
      ["RF1", "20 MP3 cargados; WAV/FLAC/OGG y otros formatos vía FFmpeg; ingesta idempotente", "scripts/ingest_folder, POST /api/ingest, pruebas automáticas"],
      ["RF2", "STFT propia; error relativo 10⁻⁷ frente a scipy", "fingerprint/spectrogram.py, test_spectrogram.py, Figura 2"],
      ["RF3", "Picos y hashes (f₁, f₂, Δt) invariantes a desplazamiento y ganancia", "fingerprint/peaks.py, hashing.py, Figura 3"],
      ["RF4", "Captura de 5–10 s por línea de comandos y navegador", "scripts/record_and_recognize, frontend/"],
      ["RF5", "400/400 fragmentos limpios; reconocimiento con micrófono real", "fingerprint/matcher.py, Tabla 3, Tabla 11"],
      ["RNF1", "Todo el audio a 44.1 kHz", "fingerprint/audio_io.py"],
      ["RNF2", "2.56 % (SQLite completo 3.93 %)", "Tabla 2, scripts/fingerprint_stats"],
      ["RNF3", "Máx. 456 ms de procesamiento; ≤ 747 ms vía HTTP", "Sección 5.3"],
      ["RNF4", "≥ 98 % con SNR ≥ 5 dB; 0/1 000 falsos positivos", "Tablas 4–6, Figura 5"],
      ["RNF5", "Python, numpy/scipy, SQLite, FastAPI, React; solo CPU", "requirements.txt, package.json"],
    ],
    [1, 5, 4.4],
  ),
  p("El código fuente, las pruebas automáticas (51 del backend y 3 del frontend), los scripts de evaluación y la documentación técnica detallada (`docs/DOCUMENTACION.md`) están en el repositorio del proyecto."),
];

// ---------------------------------------------------------------- documento
const doc = new Document({
  creator: "Juan David Patarroyo Sánchez, Laura Natalia Duarte Acero",
  title: "Sistema de Reconocimiento de Huellas Acústicas (STFT) — Informe técnico",
  features: { updateFields: false },
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 30, bold: true, color: "1F3864", font: FONT }, paragraph: { spacing: { before: 360, after: 160 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 25, bold: true, color: "2F5496", font: FONT }, paragraph: { spacing: { before: 240, after: 120 }, keepNext: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 22, bold: true, italics: true, color: "2F5496", font: FONT }, paragraph: { spacing: { before: 200, after: 100 }, keepNext: true, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
      ...["numbers", "conclusiones"].map((reference) => ({ reference, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] })),
    ],
  },
  sections: [
    {
      properties: { titlePage: true, page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
      headers: {
        first: new Header({ children: [new Paragraph({ children: [] })] }),
        default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Reconocimiento de huellas acústicas (STFT) — Informe técnico", size: 16, color: "808080" })] })] }),
      },
      footers: {
        first: new Footer({ children: [new Paragraph({ children: [] })] }),
        default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ["Página ", PageNumber.CURRENT, " de ", PageNumber.TOTAL_PAGES], size: 18, color: "808080" })] })] }),
      },
      children: [...portada, ...resumen, ...introduccion, ...marco, ...diseno, ...metodologia, ...resultados, ...discusion, ...conclusiones, ...referencias, ...anexo],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`OK ${OUT} (${(buf.length / 1024).toFixed(0)} KB, ${tableCount} tablas, ${figureCount} figuras, ${eqCount} ecuaciones)`);
});

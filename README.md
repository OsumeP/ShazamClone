# ShazamClone — Reconocimiento de música por huellas acústicas (STFT)

Sistema que identifica una canción a partir de una grabación corta (5–10 s)
tomada con el micrófono, incluso con ruido ambiental, al estilo de Shazam. Usa
la Transformada de Fourier de Tiempo Reducido, un mapa de constelación de
picos espectrales, hashing combinatorio y verificación de coherencia temporal.

Proyecto de **Teoría de la Información y Sistemas de Comunicación** —
Universidad Nacional de Colombia, sede Bogotá, 2026-II. Profesor: Oswaldo Rojas
Camacho.
Autores: **Juan David Patarroyo Sánchez** y **Laura Natalia Duarte Acero**.

```
grabación ─► normalización ─► STFT ─► picos (constelación) ─► hashes (f1, f2, Δt) ─► BD SQLite
 (5–10 s)    44.1 kHz mono    Hann     máx. locales 15×15       fan-out 10              │
                                                                                         ▼
                              canción + posición ◄── histograma de Δ = t_canción − t_fragmento
```

## Resultados principales

| Requerimiento | Meta | Resultado |
|---|---|---|
| RNF1 Muestreo | ≥ 44.1 kHz | Todo el audio se normaliza a 44.1 kHz mono |
| RNF2 Tamaño de la huella | ≤ 5 % del WAV | **2.56 %** (archivo SQLite completo: 3.93 %) |
| RNF3 Latencia | < 3 s desde el fin de la grabación | **≤ 456 ms** en el servidor; ≤ 747 ms de ida y vuelta HTTP |
| RNF4 Ruido moderado | > 80 % de acierto | **≥ 98 %** (5 s) y **100 %** (10 s) con SNR ≥ 5 dB, para ruido blanco, rosa, marrón y murmullo de voces; 0 falsos positivos en 1 000 consultas |
| RNF5 Portabilidad | Python, sin GPU | Python + numpy/scipy, solo CPU |
| Audio limpio | — | 400/400 fragmentos de 5 y 10 s reconocidos |

El detalle de cada módulo, las decisiones de diseño y los experimentos está en
[`docs/DOCUMENTACION.md`](docs/DOCUMENTACION.md). Los requerimientos originales,
en [`Requirements.md`](Requirements.md).

## Requisitos

- **Python 3.11+** (probado con 3.14.5)
- **Node.js 22+** (para el frontend; probado con 22.13)
- **FFmpeg** en el PATH, para leer MP3 y otros formatos comprimidos. En Windows:
  `winget install Gyan.FFmpeg`. Después hay que abrir una terminal nueva.
- Un micrófono, para reconocer en tiempo real.

No se necesita GPU ni servicios externos.

## Instalación

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

## Uso

Los comandos de Python se ejecutan desde `backend/` con el entorno virtual
activo.

### 1. Construir la base de datos de canciones

Copia tus archivos de audio (`.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`) a
`data/raw/`, idealmente con el nombre `Artista - Título.mp3`, y ejecuta:

```bash
python -m scripts.ingest_folder          # normaliza, calcula huellas y las guarda en data/fingerprints.db
python -m scripts.ingest_folder --list   # lista la biblioteca y el tamaño de la huella
```

Los metadatos salen, en orden de prioridad, de `data/raw/metadata.json`, del
nombre del archivo y de los tags del archivo. Repetir la ingesta no duplica
canciones.

### 2. Reconocer desde la línea de comandos

```bash
python -m scripts.recognize_file "../data/raw/Artista - Título.mp3" --start 60 --duration 10
python -m scripts.record_and_recognize --duration 10      # graba del micrófono y reconoce
```

### 3. Aplicación web

```bash
# Terminal 1 (backend/): API en http://127.0.0.1:8000  (documentación: /docs)
uvicorn api.main:app --reload

# Terminal 2 (frontend/): interfaz en http://localhost:5173
npm run dev
```

Pulsa **Escuchar** con la canción sonando cerca del micrófono. La interfaz
muestra el nivel de la señal, un espectrograma en vivo, la canción reconocida,
su posición, la latencia y un diagnóstico de la grabación. La pestaña
**Biblioteca** permite ver y agregar canciones.

### Consejos para grabar

- Apunta a un nivel entre **−35 y −15 dBFS**. El medidor lo indica. Con niveles
  por debajo de −50 dBFS el ruido propio del micrófono tapa la huella.
- Desactiva las "mejoras de audio" del micrófono en Windows (Configuración >
  Sistema > Sonido). El navegador y los scripts ya piden el audio sin
  cancelación de eco, supresión de ruido ni control automático de ganancia.
- Un parlante pequeño, como el de un celular, casi no reproduce graves: acércalo
  al micrófono (10–30 cm).

## Pruebas y evaluación

```bash
# Pruebas automáticas
cd backend && python -m pytest          # 51 pruebas (DSP, BD, matching, API)
cd frontend && npm test                 # codificador WAV

# Experimentos (desde backend/; resultados en evaluation/results/ y docs/figures/)
python -m scripts.fingerprint_stats                       # tamaño de la huella (RNF2)
python ../evaluation/eval_matching.py --per-song 10       # audio limpio + negativos
python ../evaluation/eval_noise.py --per-song 5           # acierto vs. SNR, 4 ruidos (RNF4, ~25 min)
python ../evaluation/info_theory.py                       # entropía espectral, supervivencia, Shannon-Hartley
python ../evaluation/tune_params.py                       # comparación de parámetros bajo ruido

# Pruebas de campo con micrófono real
python -m scripts.field_test --expected "Sunset Lover" --condition cafe --trials 5
python -m scripts.field_test --summary     # acierto por condición
python -m scripts.field_test --replay      # re-evaluar grabaciones guardadas
```

Para corridas largas, evita que el equipo entre en suspensión: infla la latencia
medida.

## Estructura

```
backend/
  fingerprint/   núcleo DSP: audio_io, spectrogram (STFT), peaks, hashing, matcher, metadata, config
  db/            SQLite (database.py) e ingesta de archivos (ingest.py)
  api/           API REST con FastAPI
  scripts/       CLI: ingesta, reconocimiento, micrófono, pruebas de campo, figuras
  tests/         pruebas con pytest
frontend/        React + TypeScript + Vite (captura con AudioWorklet, PCM sin compresión)
evaluation/      experimentos de robustez y Teoría de la Información; results/
docs/            DOCUMENTACION.md y figures/
data/            raw/ (audio propio), normalized/ (WAV de referencia), fingerprints.db — no versionados
```

## Referencias

- A. Wang, *"An Industrial-Strength Audio Search Algorithm"*, ISMIR 2003.
- W. Drevo, *Dejavu* — Audio fingerprinting and recognition in Python.
  https://github.com/worldveil/dejavu
- C. E. Shannon, *"A Mathematical Theory of Communication"*, Bell System
  Technical Journal, 1948.

# Documentación técnica — Sistema de Reconocimiento de Huellas Acústicas

Este documento describe **qué hace cada componente del sistema y por qué**, con
los resultados obtenidos en cada fase. Se actualiza al cerrar cada fase.
El plan de trabajo y el estado del proyecto están en `PLAN.md`; los
requerimientos, en `Requirements.md`.

**Referencias base:** A. Wang, *"An Industrial-Strength Audio Search Algorithm"*,
ISMIR 2003; W. Drevo, *Dejavu* (https://github.com/worldveil/dejavu).

---

## 1. Visión general del flujo

```
 Archivo (.mp3/.wav)                          Micrófono (Fases 6–7)
        │                                              │
        ▼                                              ▼
 ┌──────────────┐   x[n] mono, 44.1 kHz, float32
 │  audio_io    │──────────────────────────────┐
 └──────────────┘                              │
        │                                      ▼
        │                              ┌──────────────┐   S_dB(k, m)
        │                              │ spectrogram  │──────────────┐
        │                              └──────────────┘              │
        ▼                                                            ▼
 data/normalized/*.wav                                       ┌──────────────┐  (m, k)
 (referencia de tamaño, RNF2)                                │    peaks     │──────────┐
                                                             └──────────────┘          │
                                                                                       ▼
                                                                               ┌──────────────┐
                                                                               │   hashing    │
                                                                               └──────────────┘
                                                                                       │ (hash, offset)
                                                                                       ▼
                                                                         BD SQLite (Fase 3) / matcher (Fase 4)
```

Cada etapa reduce la cantidad de datos y conserva la información que identifica
a la canción:

| Etapa | Representación | Datos por segundo de audio |
|---|---|---|
| WAV normalizado | 44 100 muestras de 16 bits | 88 200 B |
| Espectrograma | 21.5 ventanas × 2 049 bins (float32) | ~176 000 B (se descarta) |
| Mapa de constelación | ~24.8 picos `(m, k)` | — |
| Huella | ~226 hashes × 10 B | **~2 260 B (2.56 %)** |

---

## 2. Núcleo DSP — `backend/fingerprint/`

### 2.1 `config.py` — parámetros globales

Reúne en un solo lugar los parámetros del sistema para que todos los módulos
(y los experimentos de la Fase 5) usen los mismos valores:

| Grupo | Parámetro | Valor | Significado |
|---|---|---|---|
| Normalización | `SAMPLE_RATE` | 44 100 Hz | Cumple Nyquist para 20 kHz (RNF1) |
| | `WAV_SUBTYPE` | PCM_16 | WAV de referencia: 88 200 B/s |
| STFT | `N_FFT` | 4 096 | ≈ 93 ms por ventana, resolución Δf = fs/N ≈ 10.8 Hz |
| | `HOP` (R) | 2 048 | ≈ 46 ms entre ventanas (50 % de solape) |
| | `WINDOW` | Hann | Reduce la fuga espectral |
| Constelación | `PEAK_FMIN_HZ`–`PEAK_FMAX_HZ` | 60 Hz – 5 kHz | Banda donde se buscan picos |
| | `PEAK_NEIGHBORHOOD_*` | 15 × 15 | Vecindario del máximo local (~161 Hz × ~0.7 s); 21×21 hasta la Fase 5 |
| | `PEAK_MIN_PROMINENCE_DB` | 10 dB | Altura mínima sobre la mediana de la propia ventana |
| Hashing | `FAN_OUT` | 10 | Pares por punto ancla |
| | `TARGET_DT_MIN/MAX` | 1 – 63 ventanas | Zona objetivo (hasta ~2.9 s) |
| | `HASH_FREQ_BITS` / `HASH_DT_BITS` | 10 / 12 | Distribución de bits del hash de 32 bits |
| | `FINGERPRINT_RECORD_BYTES` | 10 | hash (4) + offset (4) + song_id (2) |
| Matching | `MATCH_DELTA_TOLERANCE` | 1 ventana | Suma los bins Δ y Δ+1 del histograma |
| | `MATCH_MIN_SCORE` | 10 | Hashes alineados mínimos para aceptar |
| | `MATCH_MIN_RATIO` | 2.0 | El mejor candidato debe duplicar al segundo |

También define las rutas del proyecto (`data/raw`, `data/normalized`,
`docs/figures`).

### 2.2 `audio_io.py` — carga y normalización (RF1, RNF1)

Toda señal que entra al sistema, ya sea una canción de la base de datos o una
grabación del micrófono, se lleva a la misma **forma canónica**: float32 en
[−1, 1], mono, 44.1 kHz. Así el resto del pipeline no depende del formato de
origen.

- **Lectura:** WAV, FLAC y OGG se leen con `soundfile` (libsndfile). MP3 y otros
  formatos se decodifican con **FFmpeg**, que entrega PCM float32 en su frecuencia
  y número de canales originales (consultados antes con `ffprobe`).
- **Mezcla a mono (`to_mono`):** se promedian los canales.
- **Remuestreo (`resample`):** remuestreo polifásico racional con
  `scipy.signal.resample_poly`, que incluye un filtro anti-aliasing. Por ejemplo,
  48 000 → 44 100 Hz equivale a interpolar por 147 y diezmar por 160. La
  conversión a mono y el remuestreo se hacen siempre con numpy/scipy, nunca con
  FFmpeg, para que el procesamiento sea idéntico sin importar el formato.
- **`save_wav`:** guarda el WAV normalizado en PCM de 16 bits. Ese archivo es la
  **referencia para medir el tamaño de la huella** (acuerdo A1, RNF2).

### 2.3 `spectrogram.py` — STFT y espectrograma (RF2)

Implementación propia con numpy de la Transformada de Fourier de Tiempo Reducido:

$$X(m, k) = \sum_{n} x[n]\, w[n - mR]\, e^{-j 2\pi k n / N}$$

1. **`frame_signal`:** divide la señal en ventanas solapadas de N muestras con
   salto R. Usa `sliding_window_view`, que crea una vista sin copiar memoria. La
   ventana m cubre las muestras [mR, mR + N) y no se rellena la señal en los
   bordes.
2. **`stft`:** multiplica cada ventana por una Hann periódica y aplica `rfft`.
   Como la señal es real, su espectro es simétrico y basta con los N/2 + 1 bins
   de frecuencias no negativas (0 a 22 050 Hz). Devuelve una matriz
   (bins × ventanas).
3. **`power_spectrogram` y `to_db`:** S = |X|² y S_dB = 10·log₁₀(S + ε). La
   escala logarítmica comprime el rango dinámico y hace que una variación de
   volumen equivalga a sumar una constante.
4. **`frequency_axis` / `time_axis`:** f_k = k·fs/N; t_m = (mR + N/2)/fs (centro
   de la ventana).

**Validación:** la STFT propia coincide con `scipy.signal.ShortTimeFFT`, con un
error relativo de ~1e-7. Detalle a tener en cuenta: scipy mide la fase respecto
al **centro** de la ventana, un desplazamiento de N/2 muestras. Eso multiplica
cada bin por e^{jπk} = (−1)^k, así que las fases difieren en ese factor mientras
que las magnitudes, que son lo que usa el sistema, son idénticas.

### 2.4 `peaks.py` — mapa de constelación (RF3)

Reduce el espectrograma a un conjunto disperso de puntos (m, k) de máxima
energía. Un punto es pico si cumple dos condiciones:

1. **Es máximo local** en un vecindario rectangular de 15 bins × 15 ventanas
   (`scipy.ndimage.maximum_filter`). El tamaño del vecindario controla la
   densidad: como mucho un pico por cada ~161 Hz × ~0.7 s. Hasta la Fase 5 era
   21×21; se redujo porque más picos por segundo dan más hashes que sobreviven
   al ruido (ver §6.4).
2. **Supera en al menos 10 dB la mediana de su propia ventana**, es decir, de la
   columna m del espectrograma dentro de la banda.

Decisiones de diseño:

- **Umbral relativo, no absoluto.** Una grabación más fuerte o más débil solo
  suma una constante a S_dB. El máximo local y la mediana se desplazan igual, así
  que **los picos no cambian con la ganancia del micrófono** (hay una prueba que
  lo verifica con −20 dB).
- **Umbral local en el tiempo (mediana por ventana), no global.** En la Fase 2 el
  umbral era la mediana de *todo* el espectrograma, y la evaluación de la Fase 4
  mostró el problema. La intro de *Bad Apple* tiene una mediana 16 dB menor que
  la de la canción completa. Al ingestar la canción entera, el umbral global
  dejaba solo 35 picos en ese tramo; al consultar un fragmento de la intro, su
  propio umbral producía 157, los mismos 35 más 122 adicionales. Esos picos de
  más rompen casi todos los pares de hashing, y el fragmento obtenía apenas 8
  coincidencias alineadas. Con la mediana por ventana, el umbral depende solo
  del contenido de esa ventana, que es idéntico en la canción y en cualquier
  fragmento suyo. Así la detección de picos es coherente entre ingesta y
  consulta.
- **Banda 60 Hz – 5 kHz.** La música concentra ahí su energía armónica. La
  frecuencia de muestreo sigue siendo 44.1 kHz (RNF1); solo se ignoran los bins
  altos al buscar picos.
- **Banda extendida al evaluar el vecindario.** El filtro de máximos se aplica
  sobre la banda ampliada medio vecindario a cada lado. Así, un punto en el borde
  de la banda solo es pico si también domina a sus vecinos de fuera, y no
  aparecen filas artificiales de picos en 60 Hz o 5 kHz.

**Relación con la entropía (marco teórico §3.5):** el piso de ruido, con
energía repartida de forma uniforme (alta entropía), queda casi todo por debajo
del umbral. Sobreviven los pocos puntos donde se concentra la energía musical
(baja entropía). Es una reducción de ~176 000 B/s del espectrograma a ~25 puntos
por segundo. La Fase 5 (§6.2) muestra que esta hipótesis se cumple para el ruido
blanco y el rosa, pero no para todo ruido.

**Hallazgo:** en regiones que solo contienen ruido, la potencia de cada bin
sigue una distribución exponencial. El máximo esperado de N de esas muestras es
≈ ln N veces la media, es decir, ≈ ln N / ln 2 veces la mediana: ~9.7 dB sobre
la mediana para 21×21 = 441 muestras y ~8.9 dB para 15×15 = 225. Con un umbral
de +10 dB algunos picos de ruido pasan el filtro. Esos picos producen hashes
que no se alinean en el tiempo con ninguna canción: en la Fase 5 los negativos
nunca superaron una puntuación de 7, frente al umbral de aceptación de 10.

### 2.5 `hashing.py` — hashing combinatorio (RF3, RNF2)

Un pico aislado (f, t) no sirve para buscar: su frecuencia sola es poco
específica y su tiempo absoluto se desconoce en una grabación. Wang (2003) lo
resuelve **combinando pares de picos**:

- Cada pico actúa como **ancla** (t₁, f₁) y se empareja con los siguientes
  `FAN_OUT = 10` picos de su **zona objetivo**, es decir, con
  Δt = t₂ − t₁ ∈ [1, 63] ventanas.
- Cada par produce:
  ```
  hash   = f1 · 2^22 + f2 · 2^12 + Δt      (10 + 10 + 12 bits = uint32)
  offset = t1                               (ventana del ancla)
  ```
- **El hash solo usa diferencias de tiempo**, así que es invariante a
  desplazamientos. Un fragmento que empieza en la ventana s de la canción
  produce los mismos hashes con `offset − s`. En eso se basa la alineación
  temporal del matching (Fase 4).
- **Especificidad:** un hash combina 3 valores (~30 bits efectivos) en vez de 1
  (~10 bits), así que una coincidencia casual es mucho menos probable. A cambio,
  un par sobrevive al ruido solo si sobreviven sus dos picos.

Implementación: vectorizada con numpy. Para cada k = 1…10 se emparejan todos
los picos con su k-ésimo vecino siguiente a la vez y se filtra por Δt. Al final
se eliminan los pares (hash, offset) repetidos. Funciones auxiliares:
`pack_hash`/`unpack_hash`, `fingerprint_signal`/`fingerprint_file` (pipeline
completo) y `fingerprint_size_bytes` (tamaño lógico para RNF2).

### 2.6 `metadata.py` — título, artista y álbum (acuerdo A4)

Determina los metadatos de cada archivo propio, en este orden de prioridad:

1. **`data/raw/metadata.json`**: corrección manual explícita, por ejemplo
   `{"Archivo.mp3": {"title": "...", "artist": "...", "album": "..."}}`.
2. **Nombre de archivo** con el patrón `Artista - Título`. Se separa en el
   primer guion seguido de espacio, así que `Shiro SAGISU - Number One - Bankai`
   da el artista *Shiro SAGISU* y el título *Number One - Bankai*. También acepta
   `東方- Bad Apple`, y un guion sin espacio después (`Jay-Z`) no separa.
3. **Tags del archivo**, leídos con `ffprobe`.
4. El nombre de archivo completo como título.

El nombre de archivo va antes que los tags por una razón práctica: en el corpus
real los tags del MP3 traen el nombre del canal que subió el video
("FLOWofficialVEVO", "Dan Music") y títulos con ruido ("(Lyrics)", "AMV"),
mientras que los nombres de archivo los eligió el equipo.

### 2.7 `matcher.py` — matching y coherencia temporal (RF5, RNF3)

Implementa el Proceso 5.2, pasos 5 y 6, siguiendo Wang (2003) §2.3:

1. **`find_matches`:** busca en la BD (`FingerprintDB.lookup`) todas las
   apariciones de los hashes del fragmento. Un hash puede repetirse en el
   fragmento y en la BD, así que se generan todas las combinaciones de forma
   vectorizada (`searchsorted` + `repeat`). Cada coincidencia queda como
   `(song_id, t_canción, t_fragmento)`.
2. **`score_candidates`:** para cada coincidencia calcula
   **Δ = t_canción − t_fragmento**. Si el fragmento proviene de una canción, sus
   coincidencias verdaderas comparten el mismo Δ, es decir, forman una recta de
   pendiente 1 en el plano (t_fragmento, t_canción). Las coincidencias casuales
   con otras canciones tienen Δ dispersos. Se arma el histograma de Δ por
   canción (codificando cada par (canción, Δ) como un entero y contándolos con
   `np.unique`). **La puntuación es la altura del pico**, y ese Δ indica en qué
   punto de la canción empieza el fragmento.
   - **Tolerancia de ±1 ventana:** un fragmento real casi nunca empieza en un
     múltiplo exacto de R. Sus ventanas quedan desplazadas hasta R/2 (≈ 23 ms)
     respecto a las de la canción, y algunos pares alineados caen en el Δ
     vecino. Por eso se suman los bins Δ y Δ+1. En la práctica el efecto es
     pequeño: la puntuación mediana pasó de 366 a 370.
3. **`is_confident` (regla de decisión):** se acepta el mejor candidato si
   `score ≥ 10` **y** `score ≥ 2 × score del segundo`. La primera condición
   descarta audio que no está en la BD, donde el pico casual máximo observado fue
   7. La segunda descarta casos ambiguos.
4. **`recognize`:** pipeline completo para un fragmento ya normalizado: huella
   → búsqueda → puntuación → decisión. Devuelve la canción (o `None`), los
   candidatos ordenados, el número de hashes de la consulta y los tiempos de
   cada etapa. **La latencia se mide desde que el audio está en memoria**, que
   equivale al fin de la grabación (acuerdo A3).

**Ambigüedad de la posición en canciones repetitivas:** cuando una sección se
repite de forma idéntica (loops de producción electrónica, estribillos
copiados), el fragmento aparece realmente en varias posiciones y el histograma
tiene varios picos. La canción se identifica bien, pero la posición estimada
puede ser la de otra repetición. Por ejemplo, en *Sunset Lover* el error es
siempre 10.56 s, la duración de un loop, y en la figura de *Crawling* aparece un
segundo pico en el estribillo repetido.

---

## 2b. Base de datos — `backend/db/database.py` (Proceso 5.1, paso 6)

Base de datos SQLite en `data/fingerprints.db`, con dos tablas:

```sql
songs (id, title, artist, album, duration_s, file_name, file_sha1 UNIQUE,
       n_hashes, wav_bytes, created_at)

fingerprints (hash, song_id → songs ON DELETE CASCADE, offset_frame,
              PRIMARY KEY (hash, song_id, offset_frame)) WITHOUT ROWID
```

Decisiones de diseño:

- **`WITHOUT ROWID` con clave primaria que empieza por `hash`.** En una tabla
  normal, SQLite guarda las filas por un `rowid` oculto, y buscar por `hash`
  requiere un índice secundario que vuelve a copiar `hash` y el `rowid` de cada
  fila. Con `WITHOUT ROWID`, la tabla misma es un B-tree ordenado por
  `(hash, song_id, offset_frame)`: buscar todas las apariciones de un hash es un
  recorrido de rango sobre la tabla, sin índice adicional. Por eso el archivo en
  disco ocupa el 2.65 % del WAV en lugar de cerca del doble. La prueba
  `test_consulta_por_hash_usa_la_clave_primaria` verifica con
  `EXPLAIN QUERY PLAN` que SQLite usa esa clave.
- **`file_sha1` único:** el SHA-1 del archivo original identifica canciones ya
  cargadas, así que repetir la ingesta no duplica nada (igual que en Dejavu).
- **Una transacción por canción:** la fila de `songs` y sus ~37 000 huellas se
  insertan juntas con `executemany`. Si algo falla, no quedan datos a medias. Las
  huellas se insertan ordenadas por la clave para que el B-tree crezca de forma
  secuencial.
- **`ON DELETE CASCADE`:** borrar una canción borra sus huellas.
- **`wav_bytes`:** guarda el tamaño del WAV normalizado de cada canción para el
  reporte de RNF2 (A1).
- La columna se llama `offset_frame` porque `OFFSET` es una palabra reservada de
  SQL. Su unidad es la ventana de la STFT (≈ 46 ms).
- PRAGMAs: `journal_mode = WAL` y `synchronous = NORMAL` para escrituras
  rápidas, y `foreign_keys = ON` para que funcione el borrado en cascada.

Clase `FingerprintDB` (context manager): `add_song`, `delete_song`,
`song_by_sha1`, `get_song`, `list_songs`, `lookup` y `stats`. `lookup` carga los
hashes únicos de la consulta en una tabla temporal y la cruza con
`fingerprints` por su clave primaria: una búsqueda de rango en el B-tree por
hash, sin el límite de parámetros de una cláusula `IN (...)`.

### `backend/db/ingest.py` — ingesta de un archivo

`ingest_file(path, db, overrides)` concentra el Proceso 5.1 para un solo
archivo: SHA-1 (si ya existe, devuelve la canción existente) → metadatos →
normalización (guarda el WAV de referencia) → huella → inserción. Lo usan
tanto la CLI `ingest_folder` como el endpoint `POST /api/ingest`, así que ambos
caminos producen exactamente la misma huella.

---

## 2c. API REST — `backend/api/main.py` (Fase 6)

API con FastAPI. Se ejecuta desde `backend/` con `uvicorn api.main:app --reload`;
la documentación interactiva queda en `http://127.0.0.1:8000/docs`.

| Método y ruta | Entrada | Respuesta |
|---|---|---|
| `GET /api/health` | — | `{status, songs, hashes}` |
| `GET /api/songs` | — | Lista de canciones (`id, title, artist, album, duration_s, n_hashes`) |
| `POST /api/recognize` | `multipart/form-data` con `file` (grabación de 1–30 s; se recomienda WAV PCM) | `recognized`, `song`, `score`, `confidence` (mejor / segundo), `offset_s`, `query_duration_s`, `n_query_hashes`, los 5 mejores `candidates` y `timings_ms` (`decode`, `fingerprint`, `lookup`, `scoring`, `total`, `server_total`) |
| `POST /api/ingest` | `file` + opcionalmente `title`, `artist`, `album` | `song`, `already_existed`, `metadata_source` |

Decisiones de diseño:

- **Decodificación en memoria (`audio_io.load_audio_bytes`).** WAV, FLAC y OGG
  se leen directamente desde los bytes. Cualquier otro formato, o un archivo con
  extensión engañosa, pasa por FFmpeg mediante un archivo temporal. El resultado
  siempre se normaliza a mono a 44.1 kHz, así que el navegador puede enviar
  audio a 48 kHz y estéreo.
- **Una conexión SQLite por petición** (dependencia `get_db`): `sqlite3` no
  comparte conexiones entre hilos, y FastAPI ejecuta los endpoints síncronos en
  un pool de hilos.
- **Errores con mensaje claro:**
  - 400: audio vacío o que no se puede decodificar.
  - 413: archivo mayor a 20 MB (reconocer) o 200 MB (ingestar).
  - 422: duración fuera de 1–30 s.
  - 409: ya existe en `data/raw/` otro archivo distinto con el mismo nombre.
  - 500: FFmpeg no instalado; además, al iniciar el servidor se registra un aviso
    si no está en el PATH.
- **Latencia en la respuesta (`timings_ms`).** El servidor reporta su parte, y
  el cliente le suma el tiempo de subida para medir la latencia desde el fin de
  la grabación (A3).
- **CORS:** por defecto solo se permite el servidor de desarrollo de Vite
  (`localhost:5173`). Se configura con `SHAZAM_CORS_ORIGINS`; la ruta de la BD,
  con `SHAZAM_DB_PATH`.
- **Ingesta por API:** guarda el archivo en `data/raw/` con su nombre original
  (sin rutas, para evitar escrituras fuera de la carpeta). Si se envía `title`,
  los metadatos del formulario tienen prioridad sobre el nombre de archivo.

---

## 2d. Frontend — `frontend/` (Fase 7)

React 19 + TypeScript con Vite 8. Para desarrollo: `npm install` y luego
`npm run dev` en `frontend/`, con el backend corriendo en el puerto 8000. Se
abre http://localhost:5173. El servidor de Vite redirige `/api` al backend
(`vite.config.ts`), así el navegador ve un solo origen.

| Archivo | Función |
|---|---|
| `src/audio/recorder.ts` | **Captura del micrófono (RF4, A2).** Pide `getUserMedia` con `echoCancellation`, `noiseSuppression` y `autoGainControl` en `false`, y conecta el micrófono a un AudioWorklet que entrega **PCM crudo**. No usa `MediaRecorder`, que comprimiría con Opus/AAC, un códec con pérdidas. Graba exactamente N segundos, reporta el nivel en vivo y marca `endedAt` al terminar, que es el inicio de la latencia (A3). Devuelve también `getSettings()` de la pista, para mostrar qué procesamiento aplicó realmente el navegador. |
| `public/recorder-worklet.js` | AudioWorklet que copia el canal 0 en bloques de 2048 muestras. Va en `public/` porque algunos navegadores no aceptan módulos de worklet incrustados como URL `data:`. |
| `src/audio/wav.ts` | Codificación WAV PCM de 16 bits mono y nivel RMS en dBFS. Probado con Vitest (`wav.test.ts`: cabecera, cuantización con saturación, −3 dBFS de una senoide). |
| `src/api.ts` | Tipos y llamadas a la API, con mensajes de error legibles (incluido "backend sin conexión"). |
| `src/components/Recognizer.tsx` | Botón *Escuchar* con duración de 5, 7 o 10 s, progreso, medidor de nivel, espectrograma en vivo y la opción de reconocer un archivo. Calcula la **latencia desde el fin de la grabación** hasta la respuesta. Maneja la cancelación y el permiso de micrófono denegado. |
| `src/components/LevelMeter.tsx` | Medidor en dBFS con la zona recomendada (−35 a −15 dBFS) y avisos. Responde a la lección de la Fase 6: un nivel bajo era la causa principal de fallo. |
| `src/components/LiveSpectrogram.tsx` | Espectrograma desplazable de 0 a 5 kHz dibujado con un `AnalyserNode`: la STFT de RF2 vista en tiempo real. |
| `src/components/ResultCard.tsx` | Canción, artista, posición dentro de la canción, hashes alineados frente al segundo candidato, latencia total y por etapa del servidor, diagnóstico de la grabación (nivel, frecuencia y procesamiento del navegador) y tabla de candidatos. |
| `src/components/Library.tsx` | Biblioteca de canciones y formulario para agregar una (`POST /api/ingest`) con título y artista opcionales. |

**Decisión — remuestreo en el servidor y no en el navegador.** El plan (7.3)
proponía remuestrear a 44.1 kHz en el cliente. Se optó por enviar el WAV a la
frecuencia nativa del `AudioContext` (normalmente 48 kHz, que cumple RNF1:
≥ 44.1 kHz). El backend lo remuestrea con el mismo filtro polifásico
anti-aliasing (`resample_poly`) que usa para las canciones de la BD, así la
consulta y la BD pasan por una normalización idéntica. Además se evita un
remuestreo en JavaScript de menor calidad, y crear un `AudioContext` a
44.1 kHz falla en algunos navegadores cuando el micrófono trabaja a otra
frecuencia. Este último devuelve los
totales y el tamaño en disco, calculado como `page_size × page_count` después de
un checkpoint del WAL.

---

## 3. Scripts — `backend/scripts/`

Se ejecutan desde `backend/` con el venv activo: `python -m scripts.<nombre>`.

| Script | Función |
|---|---|
| `normalize_corpus` | `data/raw/*` → `data/normalized/*.wav` (44.1 kHz, mono, 16 bits). Omite los ya normalizados (`--force` para rehacer). |
| `plot_spectrogram` | Figura del espectrograma en dB de un fragmento (`--start`, `--duration`, `--fmax`). |
| `plot_constellation` | Espectrograma con los picos superpuestos y, debajo, los pares ancla → objetivo de algunos anclas (como la fig. 1 de Wang). |
| `fingerprint_stats` | Por canción: picos/s, hashes/s y tamaño de la huella vs. WAV normalizado (RNF2). |
| `ingest_folder` | **Proceso 5.1 completo.** Por archivo: SHA-1 (omite los ya cargados) → metadatos → normalización (guarda el WAV de referencia) → huella → inserción. Al final reporta el tamaño de la huella lógica y del archivo SQLite frente al WAV. `--list` lista el contenido de la BD; `--folder` y `--db` cambian las rutas. |
| `recognize_file` | Reconoce un fragmento (`--start`, `--duration`) de un archivo contra la BD. Muestra la canción, la posición estimada, los mejores candidatos y la latencia por etapa. |
| `record_and_recognize` | **Proceso 5.2 completo con micrófono (RF4).** Cuenta regresiva, graba 5–10 s mono a 44.1 kHz (si el dispositivo no lo admite, graba a su frecuencia nativa y remuestrea), informa el nivel (dBFS) con avisos de saturación o señal débil, reconoce y muestra la latencia desde el fin de la grabación. `--exclusive` usa la versión WASAPI del micrófono en modo exclusivo, que salta el procesamiento de audio de Windows (A2), pero también su ganancia (ver resultados de la Fase 6); `--save` guarda la grabación; `--list-devices` lista los micrófonos. |
| `plot_matches` | Coherencia temporal de un fragmento. Para la canción reconocida y la segunda candidata muestra el diagrama t_fragmento vs. t_canción, una ampliación alrededor del mejor Δ (con la recta de pendiente 1) y el histograma de Δ. |

Las figuras se guardan en `docs/figures/`. `plot_style.py` configura
matplotlib para todos los scripts de figuras: backend sin ventana y fuentes de
respaldo (Yu Gothic, MS Gothic…) para que títulos como *東方 - Bad Apple* no
salgan con recuadros vacíos.

### Evaluación — `evaluation/`

| Script | Función |
|---|---|
| `eval_matching.py` | **Positivos:** N fragmentos por canción y duración, en posiciones aleatorias con resolución de una muestra. **Negativos:** arma una BD temporal sin 1 de cada 4 canciones y consulta fragmentos de esas canciones excluidas, donde lo correcto es rechazar. Reporta top-1, acierto con la regla de decisión, puntuaciones, error de posición, latencia y falsos positivos. El detalle queda en `evaluation/results/fase4_matching.csv`. Se ejecuta desde `backend/` con `python ../evaluation/eval_matching.py [--per-song 10] [--tolerance 1]`. |
| `common.py` | Utilidades compartidas: cargar canciones y audio de la BD, recortar fragmentos aleatorios, separar canciones de la BD y canciones fuera, y armar una BD temporal con una función de huella cualquiera. |
| `noise.py` | Generadores de ruido y mezcla a una SNR dada (ver §6.1). |
| `eval_noise.py` | **Acierto vs. SNR (RNF4).** Diseño pareado: los mismos fragmentos limpios reciben cada tipo de ruido a cada SNR. Incluye negativos y un barrido del umbral `MATCH_MIN_SCORE`, que recalcula la decisión sin repetir consultas. Salidas: `results/fase5_ruido.csv` y `docs/figures/ruido_acierto_vs_snr.png`. |
| `info_theory.py` | Entropía espectral (música vs. ruidos), supervivencia de picos y hashes vs. SNR, y capacidad de Shannon-Hartley. Salidas: `results/fase5_teoria.md`, `docs/figures/entropia_espectral.png` y `docs/figures/canal_ruidoso_vs_snr.png`. |
| `tune_params.py` | Compara configuraciones de la huella (vecindario, umbral, fan-out) en condiciones de ruido difíciles. Mide acierto, falsos positivos, tamaño (RNF2) y latencia, con una BD temporal por configuración. |

---

## 4. Pruebas — `backend/tests/`

Se ejecutan con `python -m pytest` desde `backend/`.

| Archivo | Qué verifica |
|---|---|
| `test_audio_io.py` | Mezcla a mono; remuestreo 48 → 44.1 kHz que conserva la duración y la frecuencia; normalización de estéreo; WAV de 16 bits que se guarda y se relee sin cambios; decodificación de MP3 con FFmpeg. |
| `test_spectrogram.py` | Dimensiones de la STFT; tono puro → pico en su bin exacto; dos tonos → dos picos separados 6 dB; coincidencia con `scipy.signal.ShortTimeFFT`; eje temporal. |
| `test_fingerprint.py` | `pack`/`unpack` de ida y vuelta; los picos del tono puro son los dominantes; picos dentro de la banda sin acumularse en el borde; **invariancia a la ganancia**; zona objetivo y fan-out; determinismo; **invariancia temporal** (un fragmento comparte > 50 % de hashes alineados); huella < 5 % del WAV. |

| `test_database.py` | Insertar y leer; hashes uint32 altos (≥ 2³¹) se conservan; SHA-1 duplicado rechazado sin dejar datos a medias; borrado en cascada; la búsqueda por hash usa la clave primaria; estadísticas; SHA-1 de archivo; separación `Artista - Título` en 6 casos reales; prioridad de `metadata.json`. |
| `test_matcher.py` | Expansión de hashes repetidos en `find_matches`; pico del histograma con y sin tolerancia; regla de decisión (aceptar, ambiguo, insuficiente); reconocimiento de fragmentos no alineados con R, con error de posición ≤ 1 ventana y latencia < 3 s; rechazo de audio fuera de la BD; búsqueda vacía. |
| `test_api.py` | Health y lista de canciones; reconocimiento de un WAV **estéreo a 48 kHz** (como el del navegador) con posición y tiempos; "no reconocida"; errores 400 (vacío o basura) y 422 (muy corto); 500 con mensaje si falta FFmpeg; ingesta → reconocimiento de la canción nueva; re-ingesta idempotente; metadatos del formulario; extensión inválida (400) y conflicto de nombre (409); WAV con extensión engañosa. Usa una BD y carpetas temporales. |

Las pruebas usan señales sintéticas (tonos, acordes aleatorios) y bases de datos
temporales, así que no dependen del corpus, que no se versiona.

---

## 5. Resultados por fase

### Fase 1 — Normalización y STFT
- Corpus de 20 canciones: 81.7 MB en MP3 → 427.5 MB en WAV normalizado, a ~1 s
  por canción.
- Espectrograma de *Petit Biscuit – Sunset Lover*
  (`docs/figures/espectrograma_*.png`): armónicos horizontales de la melodía,
  líneas verticales de la percusión, energía concentrada por debajo de 2 kHz.

### Fase 2 — Constelación y hashing
- Con el umbral global original: 16.6 picos/s, 152 hashes/s, huella = 1.72 %
  del WAV. **Con el umbral por ventana adoptado en la Fase 4: 14.2 picos/s,
  134 hashes/s, huella = 1.52 %** (peor caso 1.74 %; límite de RNF2: 5 %). Unos
  0.8 s por canción.
- **Configuración final (vecindario 15×15, Fase 5): 24.8 picos/s, 226 hashes/s,
  huella = 2.56 % del WAV (peor caso 3.06 %).**
- Exploración de robustez (con el umbral global original, como referencia
  histórica): fragmentos de 10 s de 10 canciones con ruido blanco a
  SNR = 5 dB, comparando sus hashes con los de la canción completa:

  | Vecindario | Umbral | Hashes/s | Supervivencia | Hashes alineados por consulta |
  |---|---|---|---|---|
  | 21×21 | med + 10 dB | 152 | 32 % | **414** |
  | 15×15 | med + 20 dB | 115 | 46 % | 276 |
  | 21×21 | med + 20 dB | 74 | 50 % | 183 |
  | 21×21 | med + 25 dB | 45 | 56 % | 116 |

  Un umbral más alto aumenta el **porcentaje** de hashes que sobreviven, pero
  reduce la cantidad **absoluta** de coincidencias alineadas. Esa cantidad
  absoluta es la altura del pico en el histograma de offsets, lo que realmente
  identifica la canción, así que se eligió 21×21 / +10 dB.

### Fase 3 — Base de datos e ingesta
- 20 canciones (80.8 min) cargadas en ~35 s. Las 20 tomaron sus metadatos del
  nombre de archivo.
- Tamaños frente al WAV normalizado (427.5 MB) según la configuración de cada
  momento:

  | Configuración | Hashes | Huella lógica (10 B/hash) | Archivo SQLite en disco |
  |---|---|---|---|
  | Fase 3: 21×21, umbral global | 737 321 | 7.37 MB = 1.72 % | 11.35 MB = 2.65 % |
  | Fase 4: 21×21, umbral por ventana | 649 001 | 6.49 MB = 1.52 % | 9.95 MB = 2.33 % |
  | **Final (Fase 5): 15×15, umbral por ventana** | **1 094 427** | **10.94 MB = 2.56 %** | **16.80 MB = 3.93 %** |

  RNF2 (≤ 5 %) se cumple en todas, incluso contando el archivo completo de la BD.
- Repetir la ingesta no agrega nada (20 omitidas en 0.1 s).

### Fase 4 — Matching y coherencia temporal (audio limpio)
Evaluación final (`eval_matching.py --per-song 10`): 20 canciones × 10
fragmentos × 2 duraciones, en posiciones aleatorias no alineadas con R, más 100
consultas de canciones fuera de la BD.

| Config. | Duración | Consultas | Top-1 correcto | Acierto (regla de decisión) | Score mín. | Score mediano | Latencia mediana | Latencia máx. |
|---|---|---|---|---|---|---|---|---|
| 21×21 (Fase 4) | 5 s | 200 | 100 % | **100 %** | 26 | 186 | 143 ms | 193 ms |
| 21×21 (Fase 4) | 10 s | 200 | 100 % | **100 %** | 57 | 378 | 170 ms | 235 ms |
| **15×15 (final)** | 5 s | 200 | 100 % | **100 %** | 50 | 342 | 244 ms | 342 ms |
| **15×15 (final)** | 10 s | 200 | 100 % | **100 %** | 145 | 612 | 279 ms | 373 ms |

- **Negativos:** 100 consultas, **0 % de falsos positivos**, con un score máximo
  de 7 frente a un umbral de 10.
- **RNF3:** latencia máxima de 373 ms, muy por debajo de 3 s. La mayor parte se va
  en la búsqueda en SQLite; la huella toma ~20 ms y la puntuación unos pocos ms.
- **Antes y después del umbral por ventana** (5 fragmentos por canción): top-1
  de 5 s pasó de 99 % a 100 % y el score mínimo de 1 a 13. El fallo restante
  con umbral global era *Bad Apple* desde 3 s (8 alineados). Otro fallo,
  *Geoxor* a 310 s, era el final que se desvanece a −70 dBFS, 60 dB por debajo
  de la canción.
- Figura `docs/figures/matching_Linkin Park - Crawling.png` (configuración
  final): en la ampliación, las coincidencias alineadas forman la recta
  t_canción = t_fragmento + 73.4 s y el histograma tiene un pico de **1016**. La
  segunda candidata (*Bad Apple*) tiene 128 coincidencias dispersas con un pico
  de **4**. Se ve además un pico secundario de ~105 en el estribillo repetido
  (~128 s). Con la configuración 21×21 los picos eran 648 y 3.

### Fase 5 — Robustez ante ruido
Ver la sección 6 completa. En resumen, con la configuración final y ruido
moderado (SNR ≥ 5 dB), el acierto es **≥ 98 % con 5 s y 100 % con 10 s** para
los cuatro tipos de ruido (RNF4 exige > 80 %). No hubo falsos positivos en 1 000
consultas negativas, y la latencia máxima fue de 456 ms.

### Fase 6 — Captura por micrófono y API
- 50 pruebas automáticas OK, 9 de ellas de la API.
- **Prueba de punta a punta con el servidor real** (uvicorn y un cliente HTTP),
  con fragmentos de 8 s de 10 canciones enviados como WAV a 48 kHz, igual que
  los enviará el navegador: **10/10 reconocidas**, con una ida y vuelta HTTP
  mediana de 631 ms y máxima de 747 ms (RNF3 < 3 s). Un MP3 a 64 kbit/s también
  se reconoce (score 750).
- Hallazgo: con un servidor iniciado sin FFmpeg en el PATH, un archivo inválido
  producía un error 500 genérico (sin JSON). Ahora la API responde con un
  mensaje claro y avisa al iniciar.
- Posible optimización (no necesaria para RNF3): la búsqueda en SQLite domina la
  latencia del servidor. Se probó `PRAGMA mmap_size` sin mejora apreciable.
- **Prueba con micrófono real** (parlante del celular → aire → micrófono,
  *Sunset Lover*, 10 s):

  | Intento | Micrófono / modo | Nivel | Resultado |
  |---|---|---|---|
  | 1 | Externo, MME | −42.7 dBFS | No reconocida: Sunset Lover primera con score 8 (< 10) |
  | 2 | Externo, WASAPI exclusivo | −58.6 dBFS | No reconocida (score 4) |
  | 3 | Integrado del portátil, MME, más volumen en Windows | −49.8 dBFS | **Reconocida, score 23, 111 ms** |

  Diagnóstico con `prueba.wav` (intento 2):
  - **La música sí llegó.** La entropía espectral fue 0.52, como la de la música
    (0.57) y lejos de la del ruido (≥ 0.82), y se ven las líneas melódicas.
  - **El canal recorta mucho.** Respecto a la banda de 600–1200 Hz, los graves
    (< 300 Hz) llegan 25–30 dB más débiles que en la canción: el parlante del
    celular no los reproduce. Los agudos (> 2.5 kHz), donde están los golpes de
    percusión, quedan bajo el ruido propio del micrófono por el nivel tan bajo.
    La BD toma muchos de sus picos justamente de los graves y de esos golpes.
  - **Simulación** de las causas sobre audio limpio (10 canciones, 10 s): filtro
    de celular 300 Hz–4 kHz → 10/10, score mediano 506; reverberación de 0.5 s →
    10/10, score 100; celular + reverberación + ruido a 10 dB → 10/10, score
    mínimo 46. Por separado ninguna explica el fallo: **la causa decisiva fue el
    nivel bajo**, que hace que el ruido del micrófono domine las bandas débiles.
  - **Se descartó un desajuste de versión o velocidad**: remuestrear la grabación
    entre ×0.90 y ×1.10 no aumentó la puntuación.
  - **El modo WASAPI exclusivo** salta la supresión de ruido de Windows, pero
    también su ganancia de software. En este equipo bajó el nivel ~16 dB, así que
    no se recomienda aquí. Para usarlo, el script tuvo que buscar la versión
    WASAPI del micrófono (el dispositivo por defecto es MME) y aceptar su formato
    nativo de 48 kHz estéreo.
  - **Lección para la Fase 8:** el canal real (parlante pequeño, reverberación,
    ganancia del micrófono) es más exigente que el ruido aditivo de la Fase 5. Una
    puntuación de 23 deja un margen modesto sobre el umbral; conviene evaluar más
    canciones y, si hace falta, hacer la huella más resistente a canales de banda
    limitada.

### Fase 7 — Frontend
- `npm run build` (comprobación de tipos con TypeScript y compilación con
  Vite): OK, 233 kB de JavaScript (74 kB comprimido). `npm test`: 3 pruebas del
  codificador WAV OK.
- Con los servidores corriendo: la página, el worklet y el proxy `/api` (health,
  songs) responden. Un WAV de 7 s a 48 kHz subido a través del proxy de Vite se
  reconoce (*稲葉曇 - ラグトレイン*, score 165, 111 ms en el servidor).
- La prueba con el micrófono en el navegador la hace el equipo (ver `PLAN.md`,
  tarea 7.7).

---

## 6. Robustez ante ruido y Teoría de la Información (Fase 5)

### 6.1 Modelo del canal ruidoso

Se simula el canal *Fuente → Aire con ruido → Micrófono* sumando ruido al
fragmento limpio a una SNR dada:
SNR = 10·log₁₀(P_música / P_ruido), con potencias medias sobre todo el fragmento
y toda la banda (0–22.05 kHz). Si la mezcla satura, se reduce la ganancia total,
lo que no altera la SNR ni los picos.

| Ruido | Modelo | Representa |
|---|---|---|
| `white` | Densidad espectral plana | Ruido térmico y electrónico |
| `pink` | Potencia ∝ 1/f (igual energía por octava) | Ruido ambiental genérico |
| `brown` | Potencia ∝ 1/f² | Retumbe grave: tráfico, aire acondicionado |
| `babble` | 6 voces simuladas: serie armónica con f0 = 100–250 Hz variable, más ruido en banda vocal (300–3400 Hz), moduladas por una envolvente silábica (~4 Hz) | Murmullo de gente (café, multitud) |

Una misma SNR global no daña igual a todos los ruidos. Lo que importa es cuánta
potencia de ruido cae en la banda de análisis (60 Hz–5 kHz):

| SNR global | Blanco (en banda) | Rosa (en banda) | Marrón (en banda) | Murmullo (en banda) |
|---|---|---|---|---|
| 5 dB | 10.4 dB | 6.4 dB | 11.7 dB | **3.9 dB** |
| 0 dB | 5.4 dB | 1.4 dB | 6.7 dB | **−1.1 dB** |

El ruido blanco reparte su potencia hasta 22 kHz, así que casi tres cuartas
partes caen fuera de la banda. El marrón concentra su potencia en los primeros
bins, por debajo de los 60 Hz. El murmullo pone toda su potencia justo en la
banda de la música.

### 6.2 Entropía espectral: música vs. ruido

Entropía de Shannon de cada ventana, normalizada a [0, 1]:
p_k = S(m,k)/Σ S(m,k), H = −Σ p_k log₂ p_k / log₂ K, en la banda de análisis
(`docs/figures/entropia_espectral.png`):

| Señal | Mediana | P10–P90 |
|---|---|---|
| Música (20 canciones) | **0.566** | 0.371–0.714 |
| Ruido blanco | 0.931 | 0.925–0.937 |
| Ruido rosa | 0.822 | 0.779–0.855 |
| Ruido marrón | 0.544 | 0.466–0.613 |
| Murmullo | 0.630 | 0.561–0.676 |

**Interpretación.** La hipótesis del marco teórico (§3.5: música de baja
entropía, ruido de alta entropía) se cumple para el ruido blanco y el rosa, pero
**no** para el marrón ni el murmullo:
- El ruido marrón tiene una entropía *menor* que la música porque concentra su
  energía en pocos bins graves. Aun así es el menos dañino: esos bins están en el
  borde de la banda y no tapan los picos del resto del espectro.
- El murmullo tiene una entropía parecida a la de la música porque, como ella,
  está hecho de armónicos. **Es el ruido más dañino**, no por ser aleatorio sino
  porque *se parece a la música*: produce picos espectrales que compiten por los
  máximos locales y desplazan a los picos de la canción.

La conclusión, más precisa que la hipótesis inicial: el filtrado por picos es
robusto frente a ruido de **energía dispersa** (alta entropía), que queda por
debajo del umbral. Es más vulnerable frente a interferencias **estructuradas**
(baja entropía) que caen en la misma banda que la música.

### 6.3 Supervivencia de picos y hashes

Fracción de los picos y hashes del fragmento limpio que siguen presentes, en la
misma posición, tras sumar el ruido (10 fragmentos de 10 s;
`docs/figures/canal_ruidoso_vs_snr.png`). Configuración final:

| SNR | Blanco: picos / hashes | Rosa: picos / hashes | Marrón: picos / hashes | Murmullo: picos / hashes |
|---|---|---|---|---|
| 20 dB | 89 % / 77 % | 87 % / 74 % | 96 % / 92 % | 87 % / 72 % |
| 10 dB | 72 % / 50 % | 66 % / 43 % | 89 % / 76 % | 67 % / 43 % |
| 5 dB | 60 % / 36 % | 50 % / 25 % | 82 % / 65 % | 46 % / 22 % |
| 0 dB | 42 % / 18 % | 31 % / 10 % | 70 % / 49 % | 26 % / 8 % |
| −5 dB | 25 % / 7 % | 15 % / 3 % | 56 % / 32 % | 10 % / 1 % |

- **Supervivencia de hashes ≈ (supervivencia de picos)².** Por ejemplo, con ruido
  blanco a 5 dB: 0.60² = 0.36. Un hash sobrevive solo si sobreviven sus dos
  picos, así que el hashing combinatorio gana especificidad a costa de robustez
  (Wang 2003 §2.2).
- Aun con solo un 10 % de hashes vivos el sistema reconoce: un fragmento de 5 s
  tiene ~1 100 hashes, así que el 10 % da ~110 coincidencias alineadas, muy por
  encima del umbral de 10 y del ruido de fondo de los negativos (≤ 7).

### 6.4 Ajuste de parámetros (`tune_params.py`)

Fragmentos de 5 s en condiciones difíciles; BD temporal con 15 canciones; 240
positivos y 80 negativos por configuración:

| Configuración | Hashes/s | % WAV | Murmullo 0 dB | Murmullo −5 dB | Rosa −5 dB | Blanco −5 dB | FP |
|---|---|---|---|---|---|---|---|
| 21×21, +10 dB, fan-out 10 (anterior) | 133 | 1.51 | 76.7 % | 20.0 % | 61.7 % | 93.3 % | 0 |
| Umbral +15 dB | 101 | 1.15 | 68.3 % | 18.3 % | 36.7 % | 58.3 % | 0 |
| Umbral +6 dB | 156 | 1.77 | 78.3 % | 28.3 % | 61.7 % | 83.3 % | 0 |
| Fan-out 5 | 63 | 0.71 | 53.3 % | 5.0 % | 40.0 % | 58.3 % | 0 |
| Fan-out 15 | 204 | 2.31 | 86.7 % | 30.0 % | 70.0 % | 96.7 % | 0 |
| Vecindario 21×11 | 229 | 2.60 | 88.3 % | 41.7 % | 76.7 % | 95.0 % | 0 |
| **Vecindario 15×15 (elegida)** | **227** | **2.57** | **90.0 %** | 38.3 % | 75.0 % | 95.0 % | 0 |
| 15×15, fan-out 15 | 351 | 3.98 | 91.7 % | 48.3 % | 80.0 % | 98.3 % | 0 |
| 15×15, umbral +6 dB | 275 | 3.11 | 90.0 % | 50.0 % | 73.3 % | 91.7 % | 0 |

- **Subir el umbral empeora todo.** Se pierden picos verdaderos, no solo picos de
  ruido.
- **Más densidad mejora la robustez.** Aumentar el número de picos (vecindario
  más pequeño) rinde más que aumentar el fan-out con la misma huella: 15×15 da
  90 % con 227 hashes/s, contra 86.7 % del fan-out 15 con 204 hashes/s.
- Se eligió **15×15 con fan-out 10**. Las variantes más densas solo ganan en
  −5 dB, fuera del rango de RNF4, y la de fan-out 15 llevaría la huella cerca
  del límite (3.98 % lógico, ~6 % en disco).
- Ningún cambio produjo falsos positivos.

### 6.5 Tasa de acierto vs. SNR (RNF4)

`eval_noise.py` con la configuración final: 20 canciones × 5 fragmentos × 4
ruidos × 5 SNR × 2 duraciones = 4 000 consultas positivas y 1 000 negativas
(`docs/figures/ruido_acierto_vs_snr.png`).

**Fragmentos de 5 s** (acierto con la regla de decisión):

| Ruido | 20 dB | 10 dB | **5 dB** | 0 dB | −5 dB |
|---|---|---|---|---|---|
| Blanco | 100 % | 100 % | **100 %** | 100 % | 94 % |
| Rosa | 100 % | 100 % | **99 %** | 96 % | 76 % |
| Marrón | 100 % | 100 % | **100 %** | 100 % | 99 % |
| Murmullo | 100 % | 99 % | **98 %** | 82 % | 29 % |

**Fragmentos de 10 s:**

| Ruido | 20 dB | 10 dB | **5 dB** | 0 dB | −5 dB |
|---|---|---|---|---|---|
| Blanco | 100 % | 100 % | **100 %** | 100 % | 100 % |
| Rosa | 100 % | 100 % | **100 %** | 100 % | 88 % |
| Marrón | 100 % | 100 % | **100 %** | 100 % | 100 % |
| Murmullo | 100 % | 100 % | **100 %** | 97 % | 62 % |

- **RNF4 se cumple:** en ruido moderado (SNR ≥ 5 dB) el peor caso es 98 %
  (murmullo, 5 s). El sistema incluso supera el 80 % hasta 0 dB con todos los
  ruidos.
- Comparado con la configuración anterior (21×21), el murmullo a 0 dB subió de
  74 % a 82 % (5 s) y de 91 % a 97 % (10 s), y el rosa a −5 dB de 59 % a 76 %
  (5 s).
- 10 s siempre es mejor que 5 s: el doble de hashes da el doble de coincidencias
  alineadas para separarse del ruido de fondo.
- **Falsos positivos: 0 de 1 000.** Score de los negativos: mediana 4, máximo 7.
  El barrido del umbral muestra que con 8 todavía hay 0 falsos positivos y con 6
  aparecen 15. Se mantiene `MATCH_MIN_SCORE = 10` como margen de seguridad, con
  un costo de solo 0.1 puntos de acierto en SNR ≥ 5 dB.
- **Latencia (RNF3):** mediana de 234 ms y máximo de 456 ms en 4 998 consultas.
  Se excluyeron dos consultas que midieron 1 343 s y 1 673 s porque la
  computadora entró en suspensión (Modern Standby) durante la corrida; el
  registro de eventos de Windows lo confirma.

### 6.6 Capacidad del canal (Shannon-Hartley)

C = B·log₂(1 + SNR), con B = 4 940 Hz (banda de análisis) y la SNR medida en
esa banda:

| SNR global | C banda completa (22 050 Hz) | C banda de análisis, ruido rosa | Bits disponibles en 5 s (rosa) |
|---|---|---|---|
| 20 dB | 146.8 kbit/s | 35.2 kbit/s | 176 039 |
| 5 dB | 45.4 kbit/s | 12.0 kbit/s | 59 969 |
| 0 dB | 22.1 kbit/s | 6.2 kbit/s | 31 026 |
| −5 dB | 8.7 kbit/s | 2.6 kbit/s | 12 972 |

- **Información necesaria para identificar** un par (canción, posición) entre las
  104 364 ventanas de la BD: log₂(104 364) ≈ **16.7 bits**.
- Incluso a −5 dB el canal transporta ~13 000 bits en 5 s, unas 780 veces lo
  necesario. **El límite práctico no es la capacidad del canal**, sino la
  capacidad del algoritmo para extraer de forma consistente la parte de la señal
  que identifica a la canción. La enorme redundancia explica por qué basta con
  que sobreviva el 1–10 % de los hashes.
- **Compresión:** la huella de la consulta ocupa ~226 hashes/s × 32 bits ≈
  7.2 kbit/s, contra 705.6 kbit/s del PCM de 16 bits (≈ 1 %). Guarda la
  información identificadora y descarta el resto (timbre, fase, detalle
  espectral).

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
| Mapa de constelación | ~16.6 picos `(m, k)` | — |
| Huella | ~152 hashes × 10 B | **~1 520 B (1.72 %)** |

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
| | `PEAK_NEIGHBORHOOD_*` | 21 × 21 | Vecindario del máximo local (~226 Hz × ~1 s) |
| | `PEAK_MIN_PROMINENCE_DB` | 10 dB | Altura mínima sobre la mediana |
| Hashing | `FAN_OUT` | 10 | Pares por punto ancla |
| | `TARGET_DT_MIN/MAX` | 1 – 63 ventanas | Zona objetivo (hasta ~2.9 s) |
| | `HASH_FREQ_BITS` / `HASH_DT_BITS` | 10 / 12 | Distribución de bits del hash de 32 bits |
| | `FINGERPRINT_RECORD_BYTES` | 10 | hash (4) + offset (4) + song_id (2) |

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

1. **Es máximo local** en un vecindario rectangular de 21 bins × 21 ventanas
   (`scipy.ndimage.maximum_filter`). El tamaño del vecindario controla la
   densidad: como mucho un pico por cada ~226 Hz × ~1 s.
2. **Supera la mediana del espectrograma en al menos 10 dB.**

Decisiones de diseño:

- **Umbral relativo, no absoluto.** Una grabación más fuerte o más débil solo
  suma una constante a S_dB. El máximo local y la mediana se desplazan igual, así
  que **los picos no cambian con la ganancia del micrófono** (hay una prueba que
  lo verifica con −20 dB).
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
(baja entropía). Es una reducción de ~176 000 B/s del espectrograma a ~17 puntos
por segundo.

**Hallazgo:** en regiones que solo contienen ruido, la potencia de cada bin
sigue una distribución exponencial. El máximo esperado de 21×21 = 441 de esas
muestras supera a la mediana en ~9.7 dB, por lo que con un umbral de +10 dB
algunos picos de ruido pasan el filtro. Esos picos producen hashes que no se
alinean en el tiempo con ninguna canción; su efecto se evaluará en la Fase 5.

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
`song_by_sha1`, `get_song`, `list_songs` y `stats`. Este último devuelve los
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

Las figuras se guardan en `docs/figures/`.

---

## 4. Pruebas — `backend/tests/`

Se ejecutan con `python -m pytest` desde `backend/`.

| Archivo | Qué verifica |
|---|---|
| `test_audio_io.py` | Mezcla a mono; remuestreo 48 → 44.1 kHz que conserva la duración y la frecuencia; normalización de estéreo; WAV de 16 bits que se guarda y se relee sin cambios; decodificación de MP3 con FFmpeg. |
| `test_spectrogram.py` | Dimensiones de la STFT; tono puro → pico en su bin exacto; dos tonos → dos picos separados 6 dB; coincidencia con `scipy.signal.ShortTimeFFT`; eje temporal. |
| `test_fingerprint.py` | `pack`/`unpack` de ida y vuelta; los picos del tono puro son los dominantes; picos dentro de la banda sin acumularse en el borde; **invariancia a la ganancia**; zona objetivo y fan-out; determinismo; **invariancia temporal** (un fragmento comparte > 50 % de hashes alineados); huella < 5 % del WAV. |

| `test_database.py` | Insertar y leer; hashes uint32 altos (≥ 2³¹) se conservan; SHA-1 duplicado rechazado sin dejar datos a medias; borrado en cascada; la búsqueda por hash usa la clave primaria; estadísticas; SHA-1 de archivo; separación `Artista - Título` en 6 casos reales; prioridad de `metadata.json`. |

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
- **16.6 picos/s, 152 hashes/s, huella = 1.72 % del WAV normalizado** (peor
  caso 1.87 %; límite de RNF2: 5 %). Unos 0.8 s por canción.
- Exploración de robustez: fragmentos de 10 s de 10 canciones con ruido blanco a
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
- 20 canciones (80.8 min) cargadas en 37 s → **737 321 hashes**. Las 20 tomaron
  sus metadatos del nombre de archivo.
- Tamaños frente al WAV normalizado (427.5 MB):

  | Medida | Tamaño | % del WAV |
  |---|---|---|
  | Huella lógica (10 B/hash) | 7.37 MB | **1.72 %** |
  | Archivo SQLite en disco (con estructura del B-tree) | 11.35 MB | **2.65 %** |

  RNF2 (≤ 5 %) se cumple incluso contando el archivo completo de la BD.
- Repetir la ingesta no agrega nada (20 omitidas en 0.1 s).

# Fase 5 — Teoría de la Información (resultados generados por `info_theory.py`)

## A. Entropía espectral normalizada por ventana

| Señal | Mediana | P10 | P90 |
|---|---|---|---|
| música | 0.566 | 0.371 | 0.714 |
| white | 0.931 | 0.925 | 0.937 |
| pink | 0.822 | 0.779 | 0.855 |
| brown | 0.544 | 0.466 | 0.613 |
| babble | 0.630 | 0.561 | 0.676 |

## B. Canal ruidoso (promedio de 10 fragmentos de 10 s)

Entropía mediana de la música limpia: 0.558

| Ruido | SNR global (dB) | SNR en banda 60 Hz–5 kHz (dB) | Entropía mezcla | Picos que sobreviven | Hashes que sobreviven |
|---|---|---|---|---|---|
| white | 20 | 25.4 | 0.561 | 89.4 % | 77.3 % |
| white | 10 | 15.4 | 0.585 | 72.2 % | 50.4 % |
| white | 5 | 10.4 | 0.626 | 59.7 % | 35.5 % |
| white | 0 | 5.4 | 0.707 | 41.7 % | 17.9 % |
| white | -5 | 0.4 | 0.816 | 24.6 % | 6.7 % |
| pink | 20 | 21.4 | 0.564 | 86.9 % | 73.5 % |
| pink | 10 | 11.5 | 0.597 | 66.4 % | 43.0 % |
| pink | 5 | 6.4 | 0.644 | 49.6 % | 24.5 % |
| pink | 0 | 1.4 | 0.717 | 31.1 % | 10.3 % |
| pink | -5 | -3.6 | 0.778 | 14.7 % | 2.6 % |
| brown | 20 | 26.6 | 0.560 | 96.4 % | 91.6 % |
| brown | 10 | 16.8 | 0.563 | 88.8 % | 76.3 % |
| brown | 5 | 11.7 | 0.568 | 82.1 % | 65.0 % |
| brown | 0 | 6.7 | 0.580 | 70.1 % | 48.7 % |
| brown | -5 | 1.6 | 0.588 | 55.5 % | 31.5 % |
| babble | 20 | 18.9 | 0.564 | 86.5 % | 72.3 % |
| babble | 10 | 8.9 | 0.596 | 66.7 % | 42.6 % |
| babble | 5 | 3.9 | 0.627 | 45.7 % | 21.5 % |
| babble | 0 | -1.1 | 0.645 | 25.8 % | 7.5 % |
| babble | -5 | -6.1 | 0.649 | 9.8 % | 1.1 % |

## C. Capacidad de Shannon-Hartley  C = B·log2(1 + SNR)

- Banda completa B = 22,050 Hz; banda de análisis B = 4,940 Hz.
- Información necesaria para identificar (canción, posición) entre las 104,364 ventanas de la BD: log2(104,364) ≈ **16.7 bits**.
- Huella de la consulta: ~226 hashes/s × 32 bits ≈ 7.2 kbit/s (vs. PCM 16 bits a 44.1 kHz = 705.6 kbit/s).

| SNR (dB) | C banda completa (kbit/s) | C banda análisis, ruido blanco (kbit/s) | C banda análisis, ruido rosa (kbit/s) | Bits en 5 s (rosa, banda) |
|---|---|---|---|---|
| 20 | 146.8 | 41.6 | 35.2 | 176,039 |
| 10 | 76.3 | 25.4 | 19.3 | 96,451 |
| 5 | 45.4 | 17.6 | 12.0 | 59,969 |
| 0 | 22.1 | 10.6 | 6.2 | 31,026 |
| -5 | 8.7 | 5.2 | 2.6 | 12,972 |

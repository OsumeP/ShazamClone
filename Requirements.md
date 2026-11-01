\# Contexto de Proyecto: Sistema de Reconocimiento y Codificación de Huellas Acústicas (STFT)



\## 📌 1. Información General del Proyecto

\* \*\*Nombre del Proyecto:\*\* Desarrollo de un Sistema de Reconocimiento y Codificación de Huellas Acústicas mediante Análisis de Fourier de Tiempo Reducido (STFT).

\* \*\*Institución:\*\* Universidad Nacional de Colombia - Sede Bogotá (Facultad de Ingeniería).

\* \*\*Asignatura:\*\* Teoría De La Información Y Sistemas De Comunicación (Periodo 2026-02).

\* \*\*Profesor:\*\* Oswaldo Rojas Camacho.

\* \*\*Autores:\*\* Juan David Patarroyo Sanchez, Laura Natalia Duarte Acero.

\* \*\*Inspiración Técnica:\*\* Algoritmo Shazam (referencia open-source: `shazam-build`, Danztee, 2026).



\---



\## 🎯 2. Objetivos



\### 2.1. Objetivo General

Diseñar e implementar un sistema digital de identificación de señales de audio en tiempo real basado en la extracción de huellas acústicas mediante la Transformada de Fourier, evaluando la robustez del canal ante la presencia de ruido ambiental bajo los principios de la Teoría de la Información de Claude Shannon.



\### 2.2. Objetivos Específicos

1\. Descomponer señales de audio multidimensionales (música) en el dominio tiempo-frecuencia mediante la \*\*Transformada de Fourier de Tiempo Reducido (STFT)\*\* para generar espectrogramas.

2\. Implementar un algoritmo de reducción de datos que extraiga los picos espectrales de máxima energía (Mapa de Constelación), minimizando la entropía de almacenamiento.

3\. Desarrollar un módulo de comparación estadística/hashing para contrastar muestras de audio ruidosas en tiempo real contra la base de datos preexistente.

4\. Identificar y retornar el nombre de la canción correcta en tiempo real con alta coherencia temporal.



\---



\## 🧠 3. Marco Teórico y Fundamentos Matemáticos



\### 3.1. Digitalización del Sonido y Teorema de Nyquist-Shannon

\* \*\*Frecuencia de Muestreo ($f\_s$):\*\* Cantidad de muestras tomadas por segundo.

\* \*\*Criterio de Nyquist:\*\* $f\_s \\ge 2 \\cdot f\_{max}$.

\* \*\*Aplicación en el sistema:\*\* Dado que el rango auditivo humano llega a los 20 kHz, se establece una tasa estándar de \*\*$f\_s = 44.1 \\text{ kHz}$\*\* (frecuencia de Nyquist resultante de $22.05 \\text{ kHz}$), garantizando ausencia de distorsión por \*aliasing\*.



\### 3.2. Transformada Discreta de Fourier (DFT)

Mapea del dominio discreto del tiempo al dominio discreto de la frecuencia:

$$X\[k] = \\sum\_{n=0}^{N-1} x\[n] \\cdot e^{-j \\frac{2\\pi}{N} kn}, \\quad k=0,1,\\dots,N-1$$



\### 3.3. Transformada de Fourier de Tiempo Reducido (STFT)

Dado que la música es no estacionaria, se aplica una ventana deslizante $w\[n]$ (p. ej., Hann, Hamming o Blackman) para analizar variaciones espectrales temporales:

$$X(m, \\omega) = \\sum\_{n=-\\infty}^{\\infty} x\[n] \\cdot w\[n - mR] \\cdot e^{-j\\omega n}$$

\*Donde $m$ es el índice de ventana y $R$ es el tamaño del salto (hop size).\*



\### 3.4. Espectrograma

Representación tridimensional (Tiempo, Frecuencia, Magnitud):

$$S(m, \\omega) = |X(m, \\omega)|^2$$

Expresado en decibelios (escala logarítmica):

$$S\_{dB}(m, \\omega) = 10 \\cdot \\log\_{10}(|X(m, \\omega)|^2 + \\epsilon)$$



\### 3.5. Entropía de Shannon y Ruido en el Canal

\* \*\*Entropía de Shannon:\*\* $H(X) = -\\sum\_{i=1}^{n} p(x\_i) \\log\_2 p(x\_i)$.

\* \*\*Música (Entropía Espectral Baja):\*\* Energía concentrada en pocos picos espectrales predecibles.

\* \*\*Ruido del Canal (Entropía Espectral Alta):\*\* Distribución uniforme y aleatoria de la energía en el espectro.

\* \*\*Modelo del Canal:\*\*

&#x20; $$\\text{\[Fuente: Música]} \\longrightarrow \\text{\[Canal: Aire (con Ruido)]} \\longrightarrow \\text{\[Receptor: Micrófono]} \\longrightarrow \\text{\[Procesamiento (DSP)]}$$

\* \*\*Capacidad del Canal (Shannon-Hartley):\*\*

&#x20; $$C = B \\cdot \\log\_2\\left(1 + \\frac{S}{N}\\right)$$

\* \*\*Resiliencia por Fourier:\*\* Al ignorar el "piso de ruido" plano de alta entropía y filtrar solo los picos de mayor amplitud (baja entropía), el algoritmo recupera la información útil en entornos de baja SNR.



\---



\## 📋 4. Requerimientos del Sistema



\### 4.1. Requerimientos Funcionales (RF)

\* \*\*RF1 (Carga e Indexación):\*\* Lectura e ingesta de archivos `.wav` o `.mp3`.

\* \*\*RF2 (Análisis Espectral):\*\* Cálculo de la STFT para mapear coordenadas tiempo-frecuencia.

\* \*\*RF3 (Generación de Huellas / Fingerprinting):\*\* Filtrado de picos de máxima amplitud y creación de códigos hashes combinatorios con sus distancias temporales ($\\Delta t$).

\* \*\*RF4 (Captura en Tiempo Real):\*\* Grabación desde micrófono en ráfagas cortas de 5 a 10 segundos.

\* \*\*RF5 (Matching / Coincidencia):\*\* Comparación de hashes de la muestra con la base de datos y retorno del resultado correcto.



\### 4.2. Requerimientos No Funcionales (RNF)

\* \*\*RNF1 (Nyquist):\*\* Muestreo estricto a $\\ge 44.1 \\text{ kHz}$.

\* \*\*RNF2 (Eficiencia de Almacenamiento):\*\* La huella digital no debe superar el \*\*5%\*\* del tamaño del archivo de audio original.

\* \*\*RNF3 (Latencia):\*\* Respuesta de búsqueda y emparejamiento en menos de \*\*3 segundos\*\*.

\* \*\*RNF4 (Tolerancia al Ruido):\*\* Tasa de acierto superior al \*\*80%\*\* en entornos con ruido ambiental moderado.

\* \*\*RNF5 (Portabilidad):\*\* Ejecutable en Python o MATLAB mediante librerías open-source, sin hardware especializado/GPU obligatorio.



\---



\## 🔄 5. Flujos de Procesamiento y Algoritmos



\### 5.1. Proceso 1: Preparación e Ingesta de la Base de Datos (Se ejecuta 1 vez)

1\. \*\*Ingesta de Datos:\*\* Obtención de metadatos mediante Spotify API y descarga de audio limpio en alta calidad (vía YouTube).

2\. \*\*Normalización (DSP):\*\* Conversión a formato estándar $44.1 \\text{ kHz}$, Mono, `.wav`.

3\. \*\*Fourier (STFT):\*\* Generación del espectrograma (Matriz Tiempo vs. Frecuencia).

4\. \*\*Filtrado de Entropía:\*\* Extracción de máximos locales / picos de alta energía (\*\*Mapa de Constelación\*\*).

5\. \*\*Hashing Combinatorio:\*\* Emparejamiento de picos calculando distancias temporales ($\\Delta t$) para generar hashes únicos.

6\. \*\*Almacenamiento:\*\* Guardado masivo de pares `(hash, offset\_tiempo\_cancion)` vinculados al `ID\_cancion` en la BD.



\### 5.2. Proceso 2: Consulta y Reconocimiento en Tiempo Real (Uso de la App)

1\. \*\*Captura:\*\* Grabación de 5 a 10 segundos de audio ambiental con ruido mediante micrófono.

2\. \*\*Normalización:\*\* Transformación a $44.1 \\text{ kHz}$, Mono, `.wav`.

3\. \*\*Fourier (STFT) \& Filtrado:\*\* Generación de espectrograma y extracción del mapa de constelación de la muestra.

4\. \*\*Hashing Combinatorio:\*\* Generación de huellas/hashes de la ráfaga capturada.

5\. \*\*Matching (Consulta BD):\*\* Búsqueda directa de coincidencias exactas entre hashes de la muestra y la base de datos.

6\. \*\*Alineación Diagonal (Coherencia Temporal):\*\* Verificación de que las distancias de tiempo entre coincidencias mantengan una relación constante ($\\Delta t\_{muestra} = \\Delta t\_{original}$). Si las coincidencias forman una línea recta en un histograma de deltas temporales, la canción es identificada exitosamente.



\---



\## 🛠️ 6. Stack Tecnológico



\* \*\*Backend / Engine DSP:\*\* Python (con bibliotecas DSP / STFT) o Django.

\* \*\*Frontend:\*\* React + TypeScript (o HTML/JS plano).

\* \*\*Base de Datos:\*\* PostgreSQL o SQLite (optimizada para búsquedas masivas de pares llave-valor/hashes).

\* \*\*Control de Versiones:\*\* Git \& GitHub.


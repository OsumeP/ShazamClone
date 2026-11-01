// Cliente de la API FastAPI (backend/api/main.py). Las rutas son relativas:
// en desarrollo el proxy de Vite las envía a http://127.0.0.1:8000.

export interface Song {
  id: number;
  title: string;
  artist: string | null;
  album: string | null;
  duration_s: number;
  n_hashes: number;
}

export interface Candidate {
  song_id: number;
  title: string;
  artist: string | null;
  score: number;
  n_matches: number;
  offset_s: number;
}

export interface Recognition {
  recognized: boolean;
  song: Song | null;
  score: number;
  confidence: number;
  offset_s: number | null;
  query_duration_s: number;
  n_query_hashes: number;
  candidates: Candidate[];
  timings_ms: Record<string, number>;
}

export interface Health {
  status: string;
  songs: number;
  hashes: number;
}

export interface IngestResult {
  song: Song;
  already_existed: boolean;
  metadata_source: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error("No hay conexión con el backend. ¿Está corriendo `uvicorn api.main:app`?");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const getHealth = () => request<Health>("/api/health");

export const getSongs = () => request<Song[]>("/api/songs");

export function recognize(audio: Blob, filename = "grabacion.wav") {
  const form = new FormData();
  form.append("file", audio, filename);
  return request<Recognition>("/api/recognize", { method: "POST", body: form });
}

export function ingest(file: File, meta: { title?: string; artist?: string; album?: string }) {
  const form = new FormData();
  form.append("file", file, file.name);
  for (const [k, v] of Object.entries(meta)) if (v) form.append(k, v);
  return request<IngestResult>("/api/ingest", { method: "POST", body: form });
}

import { describe, expect, it } from "vitest";
import { encodeWav, rmsDbfs } from "./wav";

describe("encodeWav", () => {
  const fs = 48000;
  const samples = new Float32Array(fs / 10).map((_, i) => 0.5 * Math.sin((2 * Math.PI * 1000 * i) / fs));
  const view = new DataView(encodeWav(samples, fs));
  const ascii = (o: number, n: number) => String.fromCharCode(...Array.from({ length: n }, (_, i) => view.getUint8(o + i)));

  it("escribe una cabecera RIFF/WAVE PCM 16 bits mono válida", () => {
    expect(ascii(0, 4)).toBe("RIFF");
    expect(ascii(8, 4)).toBe("WAVE");
    expect(ascii(12, 4)).toBe("fmt ");
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(fs);
    expect(view.getUint32(28, true)).toBe(fs * 2);
    expect(view.getUint16(34, true)).toBe(16);
    expect(ascii(36, 4)).toBe("data");
    expect(view.getUint32(40, true)).toBe(samples.length * 2);
    expect(view.getUint32(4, true)).toBe(36 + samples.length * 2);
    expect(view.byteLength).toBe(44 + samples.length * 2);
  });

  it("cuantiza a int16 y satura fuera de [-1, 1]", () => {
    const v = new DataView(encodeWav(new Float32Array([0, 1, -1, 2, -2, 0.5]), fs));
    const got = [0, 1, 2, 3, 4, 5].map((i) => v.getInt16(44 + 2 * i, true));
    expect(got).toEqual([0, 32767, -32768, 32767, -32768, 16383]);
  });
});

describe("rmsDbfs", () => {
  it("una senoide de amplitud 1 está a −3 dBFS", () => {
    const s = new Float32Array(4800).map((_, i) => Math.sin((2 * Math.PI * 100 * i) / 4800));
    expect(rmsDbfs(s)).toBeCloseTo(-3.01, 1);
  });
});

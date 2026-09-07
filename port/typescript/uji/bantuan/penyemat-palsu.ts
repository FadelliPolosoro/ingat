// SPDX-License-Identifier: Apache-2.0
// Penyemat deterministik untuk uji: hash kata → vektor. Tanpa jaringan, tanpa model.
import { normalisasiL2 } from '../../src/inti/cosinus.ts';
import type { Penyemat, PeranTeks } from '../../src/sematkan/antarmuka.ts';

export class PenyematPalsu implements Penyemat {
  readonly model = 'palsu@uji';
  readonly dimensi: number;
  constructor(dimensi = 64) {
    this.dimensi = dimensi;
  }
  async sematkan(teks: string[], _peran: PeranTeks): Promise<Float32Array[]> {
    return teks.map((t) => {
      const v = new Float32Array(this.dimensi);
      for (const kata of t.toLowerCase().split(/\W+/).filter(Boolean)) {
        let h = 2166136261;
        for (let i = 0; i < kata.length; i++) h = (h ^ kata.charCodeAt(i)) * 16777619;
        v[Math.abs(h) % this.dimensi] += 1;
      }
      return normalisasiL2(v);
    });
  }
}

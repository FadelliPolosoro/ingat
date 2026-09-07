// SPDX-License-Identifier: Apache-2.0
// Adapter Ollama: POST /api/embed. Host harus eksplisit; tidak ada fallback ke API eksternal.

import { normalisasiL2 } from '../inti/cosinus.ts';
import { potongUntukSemat, type Penyemat, type PeranTeks } from './antarmuka.ts';

export interface OpsiOllama {
  host?: string;         // default http://127.0.0.1:11434
  model?: string;        // default ingat-e5-base (dibangun sendiri, lihat model/README.md)
  dimensi?: number;      // default 768
  prefiks?: boolean;     // e5 dilatih dengan 'query: ' / 'passage: '; default true
  fetchImpl?: typeof fetch;
}

export class PenyematOllama implements Penyemat {
  readonly model: string;
  readonly dimensi: number;
  private readonly host: string;
  private readonly prefiks: boolean;
  private readonly f: typeof fetch;

  constructor(opsi: OpsiOllama = {}) {
    this.host = opsi.host ?? 'http://127.0.0.1:11434';
    this.model = opsi.model ?? 'ingat-e5-base';
    this.dimensi = opsi.dimensi ?? 768;
    this.prefiks = opsi.prefiks ?? true;
    this.f = opsi.fetchImpl ?? fetch;
  }

  async sematkan(teks: string[], peran: PeranTeks): Promise<Float32Array[]> {
    if (teks.length === 0) return [];
    const input = teks.map((t) => (this.prefiks ? `${peran}: ` : '') + potongUntukSemat(t));
    const res = await this.f(`${this.host}/api/embed`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: this.model, input }),
    });
    if (!res.ok) throw new Error(`Ollama /api/embed gagal: HTTP ${res.status}`);
    const data = (await res.json()) as { embeddings?: number[][] };
    if (!data.embeddings || data.embeddings.length !== teks.length) {
      throw new Error(`Ollama mengembalikan ${data.embeddings?.length ?? 0} vektor untuk ${teks.length} teks`);
    }
    return data.embeddings.map((e) => {
      if (e.length !== this.dimensi) throw new Error(`dimensi ${e.length} ≠ ${this.dimensi} (${this.model})`);
      return normalisasiL2(Float32Array.from(e));
    });
  }
}

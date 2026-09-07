// SPDX-License-Identifier: Apache-2.0
// Pemeriksa lisensi dependensi (CONTRIBUTING.md aturan 3). Membaca node_modules/*/package.json.
// Tanpa dependensi. Keluar dengan kode 1 bila ada lisensi di luar daftar putih.
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const PUTIH = new Set(['MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'ISC', '0BSD', 'CC0-1.0', 'PostgreSQL', 'Unlicense', 'BlueOak-1.0.0', 'Python-2.0', 'MIT-0']);
const HITAM = [/SSPL/i, /BSL/i, /Business Source/i, /Elastic/i, /Commons Clause/i];

const akar = join(process.cwd(), 'node_modules');
if (!existsSync(akar)) {
  console.log('node_modules tidak ada — tidak ada dependensi untuk diperiksa (v0 memang nol dependensi runtime).');
  process.exit(0);
}
let gagal = 0;
function periksa(dir: string, nama: string) {
  const pj = join(dir, 'package.json');
  if (!existsSync(pj)) return;
  const p = JSON.parse(readFileSync(pj, 'utf8')) as { license?: string | { type?: string } };
  const lis = typeof p.license === 'string' ? p.license : p.license?.type ?? 'TIDAK-ADA';
  const hitam = HITAM.some((h) => h.test(lis));
  const ok = !hitam && (PUTIH.has(lis) || lis.split(/\s*(?:OR|AND)\s*/i).map((s) => s.replace(/[()]/g, '')).some((s) => PUTIH.has(s)));
  if (!ok) {
    gagal++;
    console.log(`✗ ${nama}: ${lis}`);
  }
}
for (const n of readdirSync(akar)) {
  if (n.startsWith('.')) continue;
  if (n.startsWith('@')) {
    for (const m of readdirSync(join(akar, n))) periksa(join(akar, n, m), `${n}/${m}`);
  } else periksa(join(akar, n), n);
}
if (gagal) {
  console.log(`${gagal} paket di luar daftar putih.`);
  process.exit(1);
}
console.log('Semua dependensi berlisensi permisif.');

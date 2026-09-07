// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { redaksi } from '../src/tangkap/redaksi.ts';
import { tandaiTier } from '../src/tangkap/tier.ts';

test('kunci API dan token diganti penanda; nilainya tidak tersisa', () => {
  const masuk = 'export ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789 dan gh token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef0123456789';
  const h = redaksi(masuk);
  assert.ok(!h.teks.includes('sk-ant-api03'), 'kunci Anthropic harus hilang');
  assert.ok(!h.teks.includes('ghp_ABCDEF'), 'token GitHub harus hilang');
  assert.ok(h.teks.includes('[REDAKSI:kunci-anthropic]'));
  assert.ok(h.teks.includes('[REDAKSI:token-github]'));
  assert.deepEqual(h.jenis, ['kunci-anthropic', 'token-github']);
  assert.equal(h.jumlah, 2);
});

test('pasangan kunci=nilai (password, KUNCI_ENKRIPSI) diredaksi, kuncinya tetap terbaca', () => {
  const h = redaksi('KUNCI_ENKRIPSI=abcd1234efgh5678\npassword: "R4has1aBanget!"\n');
  assert.ok(h.teks.includes('KUNCI_ENKRIPSI=[REDAKSI:pasangan-rahasia]'), h.teks);
  assert.ok(h.teks.includes('password: "[REDAKSI:pasangan-rahasia]"'), h.teks);
  assert.ok(!h.teks.includes('R4has1aBanget'));
});

test('Bearer token diredaksi; prosa dengan kata "token" tanpa pemisah tidak', () => {
  const h = redaksi('Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop');
  assert.ok(!h.teks.includes('eyJhbGci'), h.teks);
  const prosa = redaksi('token dikembalikan ke pemanggil setelah validasi');
  assert.equal(prosa.jumlah, 0, 'kata token dalam prosa bukan rahasia');
});

test('blok private key diredaksi utuh', () => {
  const pem = '-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\nabc\n-----END RSA PRIVATE KEY-----';
  const h = redaksi(`config:\n${pem}\nselesai`);
  assert.equal(h.teks, 'config:\n[REDAKSI:kunci-privat]\nselesai');
});

test('teks tanpa rahasia tidak diubah sama sekali', () => {
  const t = 'Deploy manual via SSH tidak terlihat oleh VPS_getProjectListV1. Token bus habis.';
  const h = redaksi(t);
  assert.equal(h.teks, t);
  assert.equal(h.jumlah, 0);
});

test('NIK dan NPWP TIDAK diredaksi (K10) tetapi menaikkan tier ke S', () => {
  const t = 'NIK 3175012345678901 atas nama X, NPWP 01.234.567.8-901.000';
  assert.equal(redaksi(t).teks, t, 'data pribadi tidak diredaksi');
  const h = tandaiTier(t);
  assert.equal(h.tier, 'S');
  assert.deepEqual(h.alasan, ['nik', 'npwp']);
});

test('episode coding biasa tetap tier I', () => {
  const h = tandaiTier('npm ci --ignore-scripts gagal karena postinstall playwright diblokir jaga.mjs');
  assert.equal(h.tier, 'I');
  assert.deepEqual(h.alasan, []);
});

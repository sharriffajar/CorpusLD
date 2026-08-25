# Benchmark Corpus Directory

Tempatkan file PDF yang ingin Anda uji/evaluasi ke dalam folder ini.

### Cara Penggunaan:
1. Salin (copy) file PDF yang ingin Anda benchmark ke dalam folder ini (`benchmark_corpus/`).
2. Jalankan skrip runner:
   ```bash
   python benchmark_runner.py
   ```
   Atau untuk menguji satu file tertentu secara spesifik:
   ```bash
   python benchmark_runner.py --file nama_dokumen.pdf
   ```
3. Hasil ekstraksi JSON-LD dan laporan evaluasi otomatis (*Quality Invariants Check*) akan tersimpan di folder `benchmark_results/`.

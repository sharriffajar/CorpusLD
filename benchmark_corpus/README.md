# Benchmark Corpus Directory

Place target PDF documents that you want to evaluate and benchmark into this folder.

### Usage Instructions:

1. **Add Target Documents**: Copy the PDF files you wish to benchmark into this directory (`benchmark_corpus/`).
2. **Run the Benchmark Suite**:
   ```bash
   # Benchmark all documents in the corpus
   python benchmark_runner.py

   # Or benchmark a specific file (recommended to conserve API quota)
   python benchmark_runner.py --file "sample_document.pdf"

   # Clean reset and benchmark the entire corpus from scratch
   python benchmark_runner.py --clean
   ```
3. **Inspect Output & Visual Dashboard**:
   - Extracted Schema.org JSON-LD files and Google Scholar meta tags will be saved in `benchmark_results/`.
   - Open the Master-Detail Visual Studio dashboard in your browser:
     ```text
     benchmark_results/dashboard.html
     ```

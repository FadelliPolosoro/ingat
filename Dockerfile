# ingat — sistem memori agent · dibuat oleh Fadelli Polosoro
FROM python:3.12-slim

# Non-root (temuan audit: jangan jalankan layanan sebagai root)
RUN useradd --create-home --uid 10001 ingat
WORKDIR /app

# Inti stdlib-only. PyYAML opsional (frontmatter lebih rapi). Tanpa pip install lain.
RUN pip install --no-cache-dir --disable-pip-version-check pyyaml==6.0.2

COPY ingat/ ./ingat/
COPY static/ ./static/
COPY uji/ ./uji/
COPY docs/ ./docs/
COPY konfigurasi.contoh.json ./konfigurasi.contoh.json

RUN mkdir -p /data /vault && chown -R ingat:ingat /app /data /vault
USER ingat

ENV INGAT_KONFIG=/app/konfigurasi.json \
    INGAT_DIR_DATA=/data \
    INGAT_VAULT=/vault \
    PYTHONUNBUFFERED=1

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/sehat',timeout=4).status==200 else 1)"

CMD ["python3", "-m", "ingat", "serve"]

# Dua tahap: tahap pertama memasang dependensi ke /install, tahap kedua hanya
# membawa hasilnya. Tanpa pemisahan ini, image akhir memuat compiler dan cache
# pip — ratusan MB untuk kode yang tidak membutuhkannya.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /src
COPY pyproject.toml README.md ./
COPY horus_graph ./horus_graph
RUN pip install --prefix=/install ".[api]"


FROM python:3.12-slim

# Tanpa ini, `python` di image tetap memakai locale C dan nama berkas non-ASCII
# (label entitas) bisa gagal dicetak di log.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8

COPY --from=builder /install /usr/local

# Bundle tidak dibawa ke image: data berubah lebih sering daripada kode.
# Mount ke /data lalu set HORUS_BUNDLE=/data/bundles/<nama>.
WORKDIR /data
EXPOSE 8000

# Bind ke 0.0.0.0 di dalam container mengharuskan HORUS_API_TOKEN disetel;
# tanpa itu server menolak start. Itu disengaja.
ENTRYPOINT ["horus-graph", "serve", "--host", "0.0.0.0", "--port", "8000"]

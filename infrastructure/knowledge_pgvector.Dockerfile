# Fixed build preparation only. Image build and PG startup require Root's separate window.
# Build context: repository root. Pin evidence: infrastructure/knowledge_pgvector.pins.json.
FROM postgres:17.11-bookworm@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826 AS extension-build
ARG TARGETARCH
ENV SOURCE_DATE_EPOCH=0 TZ=UTC LC_ALL=C
# Authenticate the frozen Debian snapshot through APT signatures. HTTP permits bootstrapping
# ca-certificates without disabling TLS verification for any subsequent source/package download.
# PGDG headers are checksum-verified and extracted only in this disposable builder. Installing
# their dependency graph would add unused LLVM/clang; PGXS receives with_llvm=no explicitly.
RUN set -eu; \
    printf '%s\n' 'M3_IMAGE_STAGE ENTER BASE_PACKAGE'; \
    test "$PG_MAJOR" = 17; \
    test "$(dpkg-query -W -f='${Version}' postgresql-17)" = '17.11-1.pgdg12+2'; \
    printf '%s\n' 'M3_IMAGE_STAGE DONE BASE_PACKAGE'; \
    printf '%s\n' 'M3_IMAGE_STAGE ENTER APT_UPDATE'; \
    rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*; \
    printf '%s\n' 'deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://snapshot.debian.org/archive/debian/20261101T000000Z/ bookworm main' > /etc/apt/sources.list; \
    apt-get update; \
    printf '%s\n' 'M3_IMAGE_STAGE DONE APT_UPDATE'; \
    printf '%s\n' 'M3_IMAGE_STAGE ENTER APT_INSTALL'; \
    apt-get install -y --no-install-recommends \
      gcc=4:12.2.0-3 make=4.3-4.1 libc6-dev=2.36-9+deb12u14 \
      curl=7.88.1-10+deb12u15 ca-certificates=20230311+deb12u1; \
    printf '%s\n' 'M3_IMAGE_STAGE DONE APT_INSTALL'; \
    test "$(dpkg --print-architecture)" = "$TARGETARCH"; \
    printf '%s\n' 'M3_IMAGE_STAGE ENTER DEV_HEADERS'; \
    case "$TARGETARCH" in \
      arm64) dev_sha=f870d7ee16b14997b5f732eb2561157c53b773d36e380417a1c24ed06252ca13; \
        pq_sha=c5a1cef1e70de76e89bcca4b7866a6721f096e60edc7b58ecedd65058bda3dfc ;; \
      amd64) dev_sha=007cb38813dc9277edc1ee2e6f1efbed25f3078c6a89f0d9bc02212efefc367e; \
        pq_sha=1537cce8c942cfbba02dee1627542a2f05ff1de54404dd4d50f00f39cf0ff778 ;; \
      *) exit 1 ;; \
    esac; \
    curl --fail --location --proto '=https' --proto-redir '=https' --connect-timeout 10 --max-time 120 \
      "https://apt-archive.postgresql.org/pub/repos/apt/pool/main/p/postgresql-17/postgresql-server-dev-17_17.11-1.pgdg12+2_${TARGETARCH}.deb" -o /tmp/pg-server-dev.deb; \
    printf '%s  %s\n' "$dev_sha" /tmp/pg-server-dev.deb | sha256sum --check --strict; \
    printf '%s\n' 'M3_IMAGE_STAGE DONE DEV_HEADERS'; \
    printf '%s\n' 'M3_IMAGE_STAGE ENTER LIBPQ'; \
    curl --fail --location --proto '=https' --proto-redir '=https' --connect-timeout 10 --max-time 120 \
      "https://apt-archive.postgresql.org/pub/repos/apt/pool/17/p/postgresql-17/libpq-dev_17.11-1.pgdg12+2_${TARGETARCH}.deb" -o /tmp/libpq-dev.deb; \
    printf '%s  %s\n' "$pq_sha" /tmp/libpq-dev.deb | sha256sum --check --strict; \
    printf '%s\n' 'M3_IMAGE_STAGE DONE LIBPQ'; \
    dpkg-deb --extract /tmp/pg-server-dev.deb /; \
    dpkg-deb --extract /tmp/libpq-dev.deb /; \
    test "$(/usr/lib/postgresql/17/bin/pg_config --version)" = 'PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2)'; \
    printf '%s\n' 'M3_IMAGE_STAGE ENTER PGVECTOR'; \
    curl --fail --location --proto '=https' --proto-redir '=https' --connect-timeout 10 --max-time 120 \
      https://codeload.github.com/pgvector/pgvector/tar.gz/f37c13f68b57d2c3472b2214fbcff699d6d34876 -o /tmp/pgvector.tar.gz; \
    printf '%s  %s\n' '83d673c3b287cddbf3879f86215f043f2c2b56c69d37b2a77504910db1ed6e56' /tmp/pgvector.tar.gz | sha256sum --check --strict; \
    printf '%s\n' 'M3_IMAGE_STAGE DONE PGVECTOR'; \
    mkdir /tmp/pgvector; \
    tar -xzf /tmp/pgvector.tar.gz --strip-components=1 -C /tmp/pgvector; \
    cd /tmp/pgvector; \
    grep -Fx "default_version = '0.8.7'" vector.control; \
    printf '%s\n' 'M3_IMAGE_STAGE ENTER COMPILE'; \
    make -j1 OPTFLAGS="" with_llvm=no PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config; \
    printf '%s\n' 'M3_IMAGE_STAGE DONE COMPILE'; \
    printf '%s\n' 'M3_IMAGE_STAGE ENTER INSTALL'; \
    make install OPTFLAGS="" with_llvm=no PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config DESTDIR=/opt/pgvector-output; \
    install -D -m 0644 LICENSE /opt/pgvector-output/usr/share/doc/pgvector/LICENSE; \
    install -D -m 0644 README.md /opt/pgvector-output/usr/share/doc/pgvector/README.md; \
    dpkg-query -W -f='${binary:Package}=${Version}\n' > /opt/pgvector-output/usr/share/doc/pgvector/builder-packages.txt; \
    printf '%s\n' 'M3_IMAGE_STAGE DONE INSTALL';

# Runtime keeps the original PG binaries/libraries and entrypoint. No compiler/dev package or
# new DB is installed here; extension activation remains an owner-only migration operation.
FROM postgres:17.11-bookworm@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826
LABEL org.opencontainers.image.source="https://github.com/pgvector/pgvector" \
      commerceops.pgvector.version="0.8.7" \
      commerceops.pgvector.commit="f37c13f68b57d2c3472b2214fbcff699d6d34876"
COPY --from=extension-build /opt/pgvector-output/usr/lib/postgresql/17/lib/vector.so /usr/lib/postgresql/17/lib/vector.so
COPY --from=extension-build /opt/pgvector-output/usr/share/postgresql/17/extension/vector* /usr/share/postgresql/17/extension/
COPY --from=extension-build /opt/pgvector-output/usr/share/doc/pgvector/ /usr/share/doc/pgvector/

# PostgreSQL 16 + pgvector + Apache AGE for ContextMap
FROM pgvector/pgvector:pg16

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ca-certificates \
    flex \
    bison \
    postgresql-server-dev-16 \
    && rm -rf /var/lib/apt/lists/*

# Apache AGE release for PG16
ARG AGE_VERSION=PG16/1.5.0
RUN git clone --branch release/${AGE_VERSION} --depth 1 https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make install \
    && rm -rf /tmp/age

# Preload AGE so sessions do not need LOAD 'age' every time
RUN echo "shared_preload_libraries = 'age'" >> /usr/share/postgresql/postgresql.conf.sample

USER postgres

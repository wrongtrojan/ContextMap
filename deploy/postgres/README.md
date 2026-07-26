# PostgreSQL (pgvector + Apache AGE)

Schema is defined entirely by `init/*.sql`. Scripts run **once** when the data directory is first created.

```
deploy/postgres/
├── init/
│   ├── 01_extensions.sql   # pgcrypto, vector, age
│   ├── 02_schema.sql       # enums, tables, indexes, triggers
│   └── 03_age_graph.sql    # create_graph('contextmap')
└── Dockerfile
```

Keep SQLAlchemy models in `database/models.py` in sync with `02_schema.sql`.

## Fresh deploy

```bash
cd deploy
docker compose build postgres
docker compose up -d postgres
```

Verify:

```sql
\dx
\d chat_turn_events
SELECT * FROM cypher('contextmap', $$ MATCH (n) RETURN count(n) $$) AS (c agtype);
```

## Schema change

1. Edit `init/02_schema.sql` (and `01` / `03` if extensions or graph change).
2. Wipe the data directory and recreate the cluster:

```bash
cd deploy
docker compose down
rm -rf ../storage/db_data/postgres/*
docker compose up -d --build postgres
```

There is no in-place migration path — rebuild the volume when the schema changes.

## AutoRE models

**Mistral 基座** 第一次跑 KG 抽取时从魔搭下载到 `models/autore/base/Mistral-7B-v0.1/`。

**LoRA 适配器** 魔搭暂无镜像时从 HuggingFace（`dante123/AutoRE`）下载；国内可配置 `kg.autore.hf_endpoint: https://hf-mirror.com`。

可选：`python -m services.kg.download_models --status`

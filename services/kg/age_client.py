"""Apache AGE Cypher client for ContextMap knowledge graph."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.kg.config import load_kg_config
from services.kg.types import TextChunk, Triple


def _cypher_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _escape_cypher_colons(cypher: str) -> str:
    """SQLAlchemy text() treats :Identifier as bind params; escape Cypher labels/rels."""
    return re.sub(r":([A-Za-z_]\w*)", r"\\:\1", cypher)


def _normalize_entity_name(name: str, *, normalize: bool) -> str:
    cleaned = " ".join(name.split()).strip()
    if not cleaned:
        return cleaned
    return cleaned.lower() if normalize else cleaned


class AgeClient:
    def __init__(self, session: AsyncSession, graph_name: str | None = None) -> None:
        cfg = load_kg_config()
        self.session = session
        self.graph_name = graph_name or str(cfg["age"]["graph_name"])
        self.normalize_entities = bool(cfg["age"].get("entity_merge_normalize", True))

    async def prepare(self) -> None:
        await self.session.execute(text("LOAD 'age'"))
        await self.session.execute(text("SET search_path = ag_catalog, public"))

    async def _cypher(self, query: str, *, columns: list[tuple[str, str]]) -> list[dict[str, Any]]:
        await self.prepare()
        col_defs = ", ".join(f"{name} {ctype}" for name, ctype in columns)
        sql = f"SELECT * FROM cypher('{self.graph_name}', $$ {query} $$) AS ({col_defs})"
        conn = await self.session.connection()
        result = await conn.exec_driver_sql(sql)
        rows = result.mappings().all()
        parsed: list[dict[str, Any]] = []
        for row in rows:
            item: dict[str, Any] = {}
            for key in row.keys():
                val = row[key]
                if val is None:
                    item[key] = None
                else:
                    item[key] = str(val)
            parsed.append(item)
        return parsed

    async def delete_asset_subgraph(self, asset_id: uuid.UUID) -> None:
        aid = _cypher_str(str(asset_id))
        await self._cypher(
            f"""
            MATCH (a:Asset {{id: {aid}}})-[:HAS_CHUNK]->(c:Chunk)
            DETACH DELETE c
            RETURN count(c) AS deleted
            """,
            columns=[("deleted", "agtype")],
        )
        await self._cypher(
            f"""
            MATCH ()-[r:RELATED]->()
            WHERE r.asset_id = {aid}
            DELETE r
            RETURN count(r) AS deleted
            """,
            columns=[("deleted", "agtype")],
        )
        await self._cypher(
            f"""
            MATCH (a:Asset {{id: {aid}}})
            DETACH DELETE a
            RETURN count(a) AS deleted
            """,
            columns=[("deleted", "agtype")],
        )

    async def write_asset_graph(
        self,
        *,
        asset_id: uuid.UUID,
        asset_name: str,
        modality: str,
        chunks: list[TextChunk],
        triples: list[Triple],
    ) -> int:
        await self.delete_asset_subgraph(asset_id)
        aid = _cypher_str(str(asset_id))
        name = _cypher_str(asset_name)
        mod = _cypher_str(modality)

        await self._cypher(
            f"CREATE (a:Asset {{id: {aid}, name: {name}, modality: {mod}}}) RETURN a",
            columns=[("a", "agtype")],
        )

        for chunk in chunks:
            unit_id = _cypher_str(str(chunk.source_unit_id))
            text_val = _cypher_str(chunk.text[:2000])
            ts = chunk.timestamp
            cidx = chunk.chunk_index
            await self._cypher(
                f"""
                MATCH (a:Asset {{id: {aid}}})
                CREATE (a)-[:HAS_CHUNK]->(c:Chunk {{
                    unit_id: {unit_id},
                    asset_id: {aid},
                    modality: {mod},
                    text: {text_val},
                    timestamp: {ts},
                    chunk_index: {cidx}
                }})
                RETURN c
                """,
                columns=[("c", "agtype")],
            )

        written = 0
        for triple in triples:
            head = _normalize_entity_name(triple.head, normalize=self.normalize_entities)
            tail = _normalize_entity_name(triple.tail, normalize=self.normalize_entities)
            if not head or not tail or head == tail:
                continue
            relation = " ".join(triple.relation.split()).strip()
            if not relation:
                continue

            head_s = _cypher_str(head)
            tail_s = _cypher_str(tail)
            rel_s = _cypher_str(relation)
            evidence = _cypher_str(triple.evidence_span[:500])
            unit_id = _cypher_str(str(triple.source_unit_id or ""))
            src_mod = _cypher_str(triple.source_modality)
            conf = triple.confidence

            await self._cypher(
                f"""
                MERGE (h:Entity {{name: {head_s}}})
                MERGE (t:Entity {{name: {tail_s}}})
                CREATE (h)-[:RELATED {{
                    relation: {rel_s},
                    confidence: {conf},
                    evidence_span: {evidence},
                    source_unit_id: {unit_id},
                    source_modality: {src_mod},
                    asset_id: {aid}
                }}]->(t)
                """,
                columns=[("r", "agtype")],
            )

            if triple.source_unit_id:
                uid = _cypher_str(str(triple.source_unit_id))
                await self._cypher(
                    f"""
                    MATCH (c:Chunk {{unit_id: {uid}, asset_id: {aid}}})
                    MATCH (h:Entity {{name: {head_s}}})
                    MERGE (c)-[:MENTIONS]->(h)
                    """,
                    columns=[("m", "agtype")],
                )
                await self._cypher(
                    f"""
                    MATCH (c:Chunk {{unit_id: {uid}, asset_id: {aid}}})
                    MATCH (t:Entity {{name: {tail_s}}})
                    MERGE (c)-[:MENTIONS]->(t)
                    """,
                    columns=[("m", "agtype")],
                )
            written += 1
        return written

    async def subgraph_by_asset(self, asset_id: uuid.UUID, depth: int = 2) -> dict[str, Any]:
        aid = _cypher_str(str(asset_id))
        depth = max(1, min(depth, 3))
        rows = await self._cypher(
            f"""
            MATCH (a:Asset {{id: {aid}}})-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e:Entity)
            OPTIONAL MATCH path = (e)-[:RELATED*1..{depth}]-(e2:Entity)
            RETURN e.name AS head, e2.name AS tail, relationships(path) AS rels
            LIMIT 500
            """,
            columns=[("head", "agtype"), ("tail", "agtype"), ("rels", "agtype")],
        )
        return self._rows_to_graph(rows, asset_id=str(asset_id))

    async def subgraph_full(self, depth: int = 2, limit: int = 500) -> dict[str, Any]:
        depth = max(1, min(depth, 3))
        limit = max(1, min(limit, 2000))
        rows = await self._cypher(
            f"""
            MATCH (e:Entity)-[r:RELATED*1..{depth}]-(e2:Entity)
            RETURN e.name AS head, e2.name AS tail, r AS rels
            LIMIT {limit}
            """,
            columns=[("head", "agtype"), ("tail", "agtype"), ("rels", "agtype")],
        )
        return self._rows_to_graph(rows)

    async def search_entities(self, query: str, asset_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        needle = query.strip()
        if not needle:
            return []
        if self.normalize_entities:
            needle = needle.lower()
        needle_s = _cypher_str(needle)
        if asset_id:
            aid = _cypher_str(str(asset_id))
            rows = await self._cypher(
                f"""
                MATCH (a:Asset {{id: {aid}}})-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(e:Entity)
                WHERE e.name CONTAINS {needle_s}
                RETURN DISTINCT e.name AS name
                LIMIT 50
                """,
                columns=[("name", "agtype")],
            )
        else:
            rows = await self._cypher(
                f"""
                MATCH (e:Entity)
                WHERE e.name CONTAINS {needle_s}
                RETURN e.name AS name
                LIMIT 50
                """,
                columns=[("name", "agtype")],
            )
        return [{"name": self._clean_agtype(row.get("name", ""))} for row in rows if row.get("name")]

    async def resolve_units_for_entities(
        self,
        entity_names: list[str],
        *,
        asset_id: uuid.UUID | None = None,
        depth: int = 1,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Map entity names to content unit IDs via Chunk-MENTIONS-Entity (+ RELATED expansion)."""
        names = [self._clean_agtype(n) for n in entity_names if n and n.strip()]
        if not names:
            return []
        if self.normalize_entities:
            names = [n.lower() for n in names]

        depth = max(1, min(depth, 3))
        limit = max(1, min(limit, 500))
        results: list[dict[str, Any]] = []
        seen_units: set[str] = set()

        for name in names:
            name_s = _cypher_str(name)
            if asset_id:
                aid = _cypher_str(str(asset_id))
                query = f"""
                MATCH (a:Asset {{id: {aid}}})-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(seed:Entity)
                WHERE seed.name CONTAINS {name_s}
                OPTIONAL MATCH (seed)-[:RELATED*1..{depth}]-(related:Entity)
                WITH c, seed, related, 0 AS hop
                RETURN c.unit_id AS unit_id, seed.name AS entity, hop AS hop, 1.0 AS confidence
                UNION
                MATCH (a:Asset {{id: {aid}}})-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(seed:Entity)
                WHERE seed.name CONTAINS {name_s}
                MATCH (seed)-[:RELATED*1..{depth}]-(related:Entity)
                MATCH (c2:Chunk)-[:MENTIONS]->(related)
                WHERE c2.asset_id = {aid}
                RETURN c2.unit_id AS unit_id, related.name AS entity, 1 AS hop, 0.8 AS confidence
                LIMIT {limit}
                """
            else:
                query = f"""
                MATCH (c:Chunk)-[:MENTIONS]->(seed:Entity)
                WHERE seed.name CONTAINS {name_s}
                RETURN c.unit_id AS unit_id, seed.name AS entity, 0 AS hop, 1.0 AS confidence
                UNION
                MATCH (seed:Entity)
                WHERE seed.name CONTAINS {name_s}
                MATCH (seed)-[:RELATED*1..{depth}]-(related:Entity)
                MATCH (c:Chunk)-[:MENTIONS]->(related)
                RETURN c.unit_id AS unit_id, related.name AS entity, 1 AS hop, 0.8 AS confidence
                LIMIT {limit}
                """

            try:
                rows = await self._cypher(
                    query,
                    columns=[
                        ("unit_id", "agtype"),
                        ("entity", "agtype"),
                        ("hop", "agtype"),
                        ("confidence", "agtype"),
                    ],
                )
            except Exception:
                continue

            for row in rows:
                unit_id = self._clean_agtype(str(row.get("unit_id", "")))
                if not unit_id or unit_id in seen_units:
                    continue
                seen_units.add(unit_id)
                hop_raw = row.get("hop", "0")
                try:
                    hop = int(str(hop_raw).strip('"'))
                except ValueError:
                    hop = 1
                conf_raw = row.get("confidence", "0.8")
                try:
                    confidence = float(str(conf_raw).strip('"'))
                except ValueError:
                    confidence = 0.8
                hop_decay = 1.0 / (1.0 + hop * 0.5)
                results.append(
                    {
                        "unit_id": unit_id,
                        "entity": self._clean_agtype(str(row.get("entity", ""))),
                        "hop": hop,
                        "confidence": confidence * hop_decay,
                    }
                )
                if len(results) >= limit:
                    return results
        return results

    def _rows_to_graph(self, rows: list[dict[str, Any]], asset_id: str | None = None) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []

        def add_node(name: str) -> None:
            if not name or name in nodes:
                return
            nodes[name] = {"id": name, "label": "Entity", "name": name}

        for row in rows:
            head = self._clean_agtype(row.get("head", ""))
            tail = self._clean_agtype(row.get("tail", ""))
            if head:
                add_node(head)
            if tail:
                add_node(tail)
            if head and tail and head != tail:
                edges.append(
                    {
                        "source": head,
                        "target": tail,
                        "relation": "RELATED",
                        "asset_id": asset_id,
                    }
                )
        return {"nodes": list(nodes.values()), "edges": edges, "asset_id": asset_id}

    @staticmethod
    def _clean_agtype(value: str) -> str:
        if not value:
            return ""
        cleaned = value.strip().strip('"')
        if cleaned.startswith("{") and "name" in cleaned:
            try:
                data = json.loads(cleaned.replace("'", '"'))
                return str(data.get("name", ""))
            except json.JSONDecodeError:
                pass
        return cleaned

# -*- coding: utf-8 -*-
"""
CorpusLD Enterprise Knowledge Graph Database Live Streaming Connector
Supports direct streaming to:
1. Neo4j (Bolt protocol & HTTP Transactional API)
2. SPARQL 1.1 Graph Stores (Apache Jena, OpenLink Virtuoso, GraphDB, Stardog, Amazon Neptune)
"""

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("corpusld.enterprise.graphdb_connector")


def _sanitize_cypher_str(s: Any) -> str:
    """Escapes strings for safe Cypher query interpolation."""
    if s is None:
        return ""
    val = str(s).replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
    return val.replace("\r", " ").replace("\n", " ").strip()


def _sanitize_cypher_id(s: str) -> str:
    """Sanitizes identifiers for Cypher node IDs."""
    if not s:
        return "kg_node_anon"
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(s))


def generate_batch_cypher_queries(data: Dict[str, Any]) -> List[str]:
    """
    Generates a deterministic sequence of Cypher MERGE queries from
    extracted JSON-LD and Deep Knowledge Graph representations.
    """
    if not data:
        return []

    # Unwrap if wrapped
    if isinstance(data, dict) and "schema_json_ld" in data and isinstance(data["schema_json_ld"], dict):
        data = data["schema_json_ld"]

    queries = []

    doc_id = _sanitize_cypher_id(data.get("@id") or f"doc_{int(time.time())}")
    doc_title = _sanitize_cypher_str(data.get("name") or data.get("headline") or "Untitled Document")
    doc_desc = _sanitize_cypher_str(data.get("description") or "")
    doc_lang = _sanitize_cypher_str(data.get("inLanguage") or "en")
    doc_date = _sanitize_cypher_str(data.get("datePublished") or "")
    doc_doi = ""

    doi_val = data.get("identifier")
    if isinstance(doi_val, list):
        for item in doi_val:
            if isinstance(item, dict) and str(item.get("propertyID", "")).upper() == "DOI" and item.get("value"):
                doc_doi = _sanitize_cypher_str(item["value"])
                break
    elif isinstance(doi_val, dict) and doi_val.get("value"):
        doc_doi = _sanitize_cypher_str(doi_val["value"])
    elif isinstance(doi_val, str):
        doc_doi = _sanitize_cypher_str(doi_val.replace("https://doi.org/", ""))

    if not doc_doi and data.get("sameAs"):
        m = re.search(r'10\.\d{4,9}/[^\s"\]\[}<>]+', str(data.get("sameAs")))
        if m:
            doc_doi = _sanitize_cypher_str(m.group(0).rstrip('.'))

    # 1. Root Paper Node
    queries.append(
        f"MERGE (p:Paper {{id: '{doc_id}'}}) "
        f"ON CREATE SET p.title = '{doc_title}', p.abstract = '{doc_desc}', p.doi = '{doc_doi}', p.language = '{doc_lang}', p.datePublished = '{doc_date}' "
        f"ON MATCH SET p.title = '{doc_title}', p.doi = '{doc_doi}'"
    )

    # 2. Authors & Organizations
    authors = data.get("author") or []
    if isinstance(authors, dict):
        authors = [authors]
    for idx, auth in enumerate(authors):
        if isinstance(auth, dict):
            a_name = _sanitize_cypher_str(auth.get("name") or f"Author_{idx+1}")
            a_id = _sanitize_cypher_id(auth.get("identifier") or f"auth_{a_name.lower()}")
            a_orcid = _sanitize_cypher_str(auth.get("identifier") or "")
            queries.append(
                f"MERGE (a:Person {{id: '{a_id}'}}) "
                f"ON CREATE SET a.name = '{a_name}', a.orcid = '{a_orcid}'"
            )
            queries.append(
                f"MATCH (p:Paper {{id: '{doc_id}'}}), (a:Person {{id: '{a_id}'}}) "
                f"MERGE (p)-[:AUTHORED_BY]->(a)"
            )

            affil = auth.get("affiliation")
            if affil:
                aff_name = _sanitize_cypher_str(affil.get("name") if isinstance(affil, dict) else affil)
                aff_id = _sanitize_cypher_id(f"inst_{aff_name.lower()}")
                aff_ror = _sanitize_cypher_str(affil.get("sameAs") if isinstance(affil, dict) else "")
                queries.append(
                    f"MERGE (o:Organization {{id: '{aff_id}'}}) "
                    f"ON CREATE SET o.name = '{aff_name}', o.ror = '{aff_ror}'"
                )
                queries.append(
                    f"MATCH (a:Person {{id: '{a_id}'}}), (o:Organization {{id: '{aff_id}'}}) "
                    f"MERGE (a)-[:AFFILIATED_WITH]->(o)"
                )

    # 3. Knowledge Graph Nodes and Relations ($G = (V, E)$)
    kg = data.get("knowledge_graph") or {}
    nodes = kg.get("nodes") or []
    edges = kg.get("edges") or []

    for n in nodes:
        if isinstance(n, dict):
            n_id = _sanitize_cypher_id(n.get("id") or n.get("@id") or f"node_{time.time()}")
            n_label = _sanitize_cypher_str(n.get("name") or n.get("label") or n_id)
            n_type = re.sub(r'[^a-zA-Z0-9]', '', str(n.get("type") or n.get("node_type") or "Concept").replace("kg:", ""))
            if not n_type:
                n_type = "Concept"
            same_as = _sanitize_cypher_str(n.get("sameAs") or n.get("same_as") or "")
            desc = _sanitize_cypher_str(n.get("description") or "")

            queries.append(
                f"MERGE (n:{n_type} {{id: '{n_id}'}}) "
                f"ON CREATE SET n.name = '{n_label}', n.sameAs = '{same_as}', n.description = '{desc}' "
                f"ON MATCH SET n.name = '{n_label}'"
            )
            queries.append(
                f"MATCH (p:Paper {{id: '{doc_id}'}}), (n:{n_type} {{id: '{n_id}'}}) "
                f"MERGE (p)-[:CONTAINS_CONCEPT]->(n)"
            )

    valid_edge_types = {
        "causes": "CAUSES", "requires": "REQUIRES", "contradicts": "CONTRADICTS",
        "supports": "SUPPORTS", "contains": "CONTAINS", "precedes": "PRECEDES",
        "similar_to": "SIMILAR_TO", "derived_from": "DERIVED_FROM",
        "influences": "INFLUENCES", "instance_of": "INSTANCE_OF"
    }

    for e in edges:
        if isinstance(e, dict):
            src_id = _sanitize_cypher_id(e.get("source") or "")
            tgt_id = _sanitize_cypher_id(e.get("target") or "")
            raw_rel = str(e.get("type") or e.get("relation") or "relates_to").lower().replace("kg:", "")
            rel_type = valid_edge_types.get(raw_rel, re.sub(r'[^A-Z0-9_]', '_', raw_rel.upper()) or "RELATES_TO")
            evidence = _sanitize_cypher_str(e.get("evidence") or "")
            weight = float(e.get("weight") or 1.0)

            if src_id and tgt_id:
                queries.append(
                    f"MATCH (s {{id: '{src_id}'}}), (t {{id: '{tgt_id}'}}) "
                    f"MERGE (s)-[r:{rel_type}]->(t) "
                    f"ON CREATE SET r.evidence = '{evidence}', r.weight = {weight}"
                )

    # 4. Quantitative Metrics (additionalProperty)
    metrics = data.get("additionalProperty") or []
    for idx, m in enumerate(metrics):
        if isinstance(m, dict):
            m_name = _sanitize_cypher_str(m.get("name") or f"Metric_{idx+1}")
            m_val = _sanitize_cypher_str(m.get("value") if m.get("value") is not None else "")
            m_unit = _sanitize_cypher_str(m.get("unitText") or "")
            m_id = _sanitize_cypher_id(f"metric_{doc_id}_{idx+1}")

            queries.append(
                f"MERGE (m:Metric {{id: '{m_id}'}}) "
                f"ON CREATE SET m.name = '{m_name}', m.value = '{m_val}', m.unit = '{m_unit}'"
            )
            queries.append(
                f"MATCH (p:Paper {{id: '{doc_id}'}}), (m:Metric {{id: '{m_id}'}}) "
                f"MERGE (p)-[:MEASURES]->(m)"
            )

    return queries


def generate_sparql_update_query(data: Dict[str, Any]) -> str:
    """
    Generates a standard SPARQL 1.1 INSERT DATA update block from extracted data.
    """
    from json_ld_extractor.validation import export_to_turtle_rdf
    turtle_rdf = export_to_turtle_rdf(data)
    
    # Strip prefix lines from turtle body and format prefixes for SPARQL
    prefix_lines = []
    triple_lines = []
    
    for line in turtle_rdf.splitlines():
        if line.startswith("@prefix "):
            # Convert '@prefix schema: <https://schema.org/> .' -> 'PREFIX schema: <https://schema.org/>'
            cleaned = line.replace("@prefix ", "").rstrip(" .").strip()
            prefix_lines.append(f"PREFIX {cleaned}")
        elif line.strip():
            triple_lines.append(line)

    sparql_body = "\n".join(triple_lines)
    sparql_prefixes = "\n".join(prefix_lines)

    return f"{sparql_prefixes}\n\nINSERT DATA {{\n{sparql_body}\n}}"


def test_graphdb_connection(
    target_type: str = "neo4j",
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "password",
    endpoint_url: Optional[str] = None,
    timeout: float = 3.0
) -> Dict[str, Any]:
    """
    Tests connectivity to an external Graph Database or SPARQL endpoint.
    """
    start = time.time()
    
    if target_type.lower() == "sparql":
        target = endpoint_url or uri
        if not target.startswith("http"):
            target = f"http://{target}"
        try:
            req = urllib.request.Request(
                target,
                headers={"Accept": "application/sparql-results+json, text/turtle, */*"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                elapsed = round(time.time() - start, 3)
                return {
                    "success": True,
                    "status_code": resp.status,
                    "latency_seconds": elapsed,
                    "target_type": "SPARQL 1.1 Graph Store",
                    "url": target,
                    "message": f"Connected to SPARQL Store ({resp.status} OK in {elapsed}s)"
                }
        except Exception as e:
            elapsed = round(time.time() - start, 3)
            return {
                "success": False,
                "latency_seconds": elapsed,
                "target_type": "SPARQL 1.1 Graph Store",
                "url": target,
                "message": f"Connection failed: {str(e)}"
            }

    # Neo4j Testing
    # 1. Try official Python driver if available
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=timeout)
        with driver.session() as session:
            result = session.run("RETURN 1 AS connected")
            record = result.single()
            if record and record["connected"] == 1:
                elapsed = round(time.time() - start, 3)
                driver.close()
                return {
                    "success": True,
                    "latency_seconds": elapsed,
                    "target_type": "Neo4j (Bolt Protocol)",
                    "uri": uri,
                    "message": f"Connected to Neo4j via Bolt Protocol in {elapsed}s"
                }
    except ImportError:
        pass
    except Exception as e:
        elapsed = round(time.time() - start, 3)
        return {
            "success": False,
            "latency_seconds": elapsed,
            "target_type": "Neo4j (Bolt Protocol)",
            "uri": uri,
            "message": f"Neo4j Bolt connection failed: {str(e)}"
        }

    # 2. Try HTTP Transactional API Fallback (Port 7474)
    http_host = re.sub(r'bolt://|neo4j://', 'http://', uri)
    if ":7687" in http_host:
        http_host = http_host.replace(":7687", ":7474")
    elif not re.search(r':\d+', http_host):
        http_host = f"{http_host}:7474"

    tx_endpoint = f"{http_host.rstrip('/')}/db/neo4j/tx/commit"
    try:
        import base64
        auth_header = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        payload = json.dumps({"statements": [{"statement": "RETURN 1 AS test"}]}).encode('utf-8')
        req = urllib.request.Request(
            tx_endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": auth_header
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = round(time.time() - start, 3)
            return {
                "success": True,
                "latency_seconds": elapsed,
                "target_type": "Neo4j (HTTP Transaction API)",
                "uri": tx_endpoint,
                "message": f"Connected to Neo4j HTTP API in {elapsed}s"
            }
    except Exception as e:
        elapsed = round(time.time() - start, 3)
        return {
            "success": False,
            "latency_seconds": elapsed,
            "target_type": "Neo4j",
            "uri": uri,
            "message": f"Neo4j connection test failed: {str(e)}"
        }


def sync_graph_to_neo4j(
    data: Dict[str, Any],
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "password",
    database: str = "neo4j",
    timeout: float = 8.0
) -> Dict[str, Any]:
    """
    Executes generated Cypher queries against a live Neo4j database.
    """
    start = time.time()
    queries = generate_batch_cypher_queries(data)
    if not queries:
        return {"success": False, "message": "No Cypher statements generated from document data."}

    # Attempt 1: Neo4j Python Driver
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=timeout)
        with driver.session(database=database) as session:
            for q in queries:
                session.run(q)
        driver.close()
        elapsed = round(time.time() - start, 3)
        return {
            "success": True,
            "driver": "bolt",
            "queries_executed": len(queries),
            "duration_seconds": elapsed,
            "message": f"Successfully synchronized {len(queries)} graph statements to Neo4j in {elapsed}s."
        }
    except ImportError:
        logger.debug("neo4j python package not installed; falling back to HTTP transactional endpoint.")
    except Exception as e:
        logger.debug("Bolt sync failed: %s; attempting HTTP transactional fallback...", e)

    # Attempt 2: HTTP Transactional API
    http_host = re.sub(r'bolt://|neo4j://', 'http://', uri)
    if ":7687" in http_host:
        http_host = http_host.replace(":7687", ":7474")
    elif not re.search(r':\d+', http_host):
        http_host = f"{http_host}:7474"

    tx_endpoint = f"{http_host.rstrip('/')}/db/{database}/tx/commit"
    try:
        import base64
        auth_header = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        payload = json.dumps({
            "statements": [{"statement": q} for q in queries]
        }).encode('utf-8')

        req = urllib.request.Request(
            tx_endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": auth_header
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            errors = res_data.get("errors", [])
            elapsed = round(time.time() - start, 3)
            if errors:
                return {
                    "success": False,
                    "errors": errors,
                    "message": f"Neo4j returned {len(errors)} execution errors."
                }
            return {
                "success": True,
                "driver": "http_transactional",
                "queries_executed": len(queries),
                "duration_seconds": elapsed,
                "message": f"Successfully committed {len(queries)} statements via Neo4j HTTP API in {elapsed}s."
            }
    except Exception as e:
        elapsed = round(time.time() - start, 3)
        return {
            "success": False,
            "error": str(e),
            "queries_executed": 0,
            "duration_seconds": elapsed,
            "message": f"Sync to Neo4j failed: {str(e)}"
        }


def sync_graph_to_sparql_endpoint(
    data: Dict[str, Any],
    endpoint_url: str,
    auth_token: Optional[str] = None,
    timeout: float = 8.0
) -> Dict[str, Any]:
    """
    Pushes extracted graph triples to any standard SPARQL 1.1 Update endpoint.
    """
    start = time.time()
    sparql_update = generate_sparql_update_query(data)
    
    headers = {
        "Content-Type": "application/sparql-update; charset=utf-8",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}" if not auth_token.startswith("Basic ") else auth_token

    try:
        req = urllib.request.Request(
            endpoint_url,
            data=sparql_update.encode('utf-8'),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = round(time.time() - start, 3)
            return {
                "success": True,
                "status_code": resp.status,
                "duration_seconds": elapsed,
                "endpoint": endpoint_url,
                "message": f"Successfully updated SPARQL Graph Store ({resp.status} in {elapsed}s)."
            }
    except Exception as e:
        elapsed = round(time.time() - start, 3)
        return {
            "success": False,
            "error": str(e),
            "duration_seconds": elapsed,
            "endpoint": endpoint_url,
            "message": f"SPARQL 1.1 Update failed: {str(e)}"
        }

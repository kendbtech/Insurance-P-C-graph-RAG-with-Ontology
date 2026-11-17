"""
graphdb_client.py - minimal GraphDB client using only the RDF4J REST protocol + two GraphDB REST endpoints.

Standards-based (RDF4J protocol, works for any RDF4J server):
    GET  /repositories                                  list repositories
    POST /repositories/{id}/statements?context=<iri>    add RDF (Content-Type: text/turtle)
    PUT  /repositories/{id}/statements?context=<iri>    replace a named graph
    DELETE /repositories/{id}/statements?context=<iri>  clear a named graph
    POST /repositories/{id}                             SPARQL query (application/x-www-form-urlencoded, query=...)
    POST /repositories/{id}/statements                  SPARQL update (update=...)
GraphDB-specific (Workbench REST API):
    POST /rest/repositories   (multipart 'config' = repository config Turtle)   create repository
    DELETE /rest/repositories/{id}                                             delete repository
"""
import json
import requests
from common import GRAPHDB_URL, GRAPHDB_REPO, QUERIES


class GraphDB:
    def __init__(self, base=GRAPHDB_URL, repo=GRAPHDB_REPO, timeout=120):
        self.base, self.repo, self.timeout = base.rstrip("/"), repo, timeout

    # --- repository lifecycle -------------------------------------------------
    def alive(self):
        try:
            return requests.get(f"{self.base}/rest/repositories", timeout=5).ok
        except requests.RequestException:
            return False

    def repositories(self):
        return [r["id"] for r in requests.get(f"{self.base}/rest/repositories", timeout=self.timeout).json()]

    def create_repository(self, config_ttl_path):
        with open(config_ttl_path, "rb") as f:
            r = requests.post(f"{self.base}/rest/repositories", files={"config": ("config.ttl", f, "text/turtle")},
                              timeout=self.timeout)
        r.raise_for_status()
        return r.status_code

    def delete_repository(self):
        return requests.delete(f"{self.base}/rest/repositories/{self.repo}", timeout=self.timeout).status_code

    # --- data -----------------------------------------------------------------
    def _ctx(self, graph_iri):
        return {"context": f"<{graph_iri}>"} if graph_iri else {}

    def load_turtle(self, path, graph_iri=None, replace=False):
        """Returns (status_code, body). ShaclSail: a 500 with a validation report means the commit was rejected."""
        with open(path, "rb") as f:
            fn = requests.put if replace else requests.post
            r = fn(f"{self.base}/repositories/{self.repo}/statements", params=self._ctx(graph_iri),
                   data=f, headers={"Content-Type": "text/turtle"}, timeout=self.timeout)
        return r.status_code, r.text

    def add_turtle_text(self, turtle, graph_iri=None):
        r = requests.post(f"{self.base}/repositories/{self.repo}/statements", params=self._ctx(graph_iri),
                          data=turtle.encode("utf-8"), headers={"Content-Type": "text/turtle"}, timeout=self.timeout)
        return r.status_code, r.text

    def clear_graph(self, graph_iri):
        return requests.delete(f"{self.base}/repositories/{self.repo}/statements", params=self._ctx(graph_iri),
                               timeout=self.timeout).status_code

    def size(self):
        return int(requests.get(f"{self.base}/repositories/{self.repo}/size", timeout=self.timeout).text)

    # --- SPARQL ---------------------------------------------------------------
    def select(self, query, with_prefixes=True):
        if with_prefixes:
            query = (QUERIES / "_prefixes.rq").read_text() + "\n" + query
        r = requests.post(f"{self.base}/repositories/{self.repo}", data={"query": query},
                          headers={"Accept": "application/sparql-results+json"}, timeout=self.timeout)
        r.raise_for_status()
        res = r.json()
        cols = res["head"]["vars"]
        rows = [{c: b.get(c, {}).get("value") for c in cols} for b in res["results"]["bindings"]]
        return cols, rows

    def update(self, update, with_prefixes=True):
        if with_prefixes:
            update = (QUERIES / "_prefixes.rq").read_text() + "\n" + update
        r = requests.post(f"{self.base}/repositories/{self.repo}/statements", data={"update": update}, timeout=self.timeout)
        return r.status_code, r.text


def print_table(cols, rows, max_rows=25, width=28):
    line = " | ".join(c[:width].ljust(min(width, max(len(c), 8))) for c in cols)
    print(line); print("-" * len(line))
    for row in rows[:max_rows]:
        print(" | ".join(str(row[c] or "")[:width].ljust(min(width, max(len(c), 8))) for c in cols))
    if len(rows) > max_rows:
        print(f"... {len(rows) - max_rows} more rows")

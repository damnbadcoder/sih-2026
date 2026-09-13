import networkx as nx
from typing import Dict, List, Any
import uuid


class CorrelationEngine:
    def __init__(self):
        self.graph = nx.Graph()

    def build_graph(self, grounding_context: Dict[str, Any]) -> Dict[str, Any]:
        self.graph.clear()
        iocs = grounding_context.get("iocs", [])

        for ioc in iocs:
            value = ioc.get("value")
            ioc_type = ioc.get("type", "unknown")
            source = ioc.get("source", "unknown")

            if not value:
                continue

            if not self.graph.has_node(value):
                self.graph.add_node(
                    value,
                    type=ioc_type,
                    sources=set(),
                    source_count=0,
                    cross_source_confidence=0.0,
                    is_novel=False,
                )

            self.graph.nodes[value]["sources"].add(source)

        for node_id, data in self.graph.nodes(data=True):
            sources_list = list(data["sources"])
            data["sources"] = sources_list
            data["source_count"] = len(sources_list)
            data["cross_source_confidence"] = min(1.0, data["source_count"] * 0.35)
            data["is_novel"] = data["source_count"] > 1

        for ioc_a in iocs:
            for ioc_b in iocs:
                val_a = ioc_a.get("value")
                val_b = ioc_b.get("value")
                if val_a and val_b and val_a != val_b:
                    if ioc_a.get("source") == ioc_b.get("source"):
                        if self.graph.has_edge(val_a, val_b):
                            self.graph[val_a][val_b]["weight"] += 1
                        else:
                            self.graph.add_edge(val_a, val_b, weight=1, source=ioc_a.get("source"))

        data = nx.node_link_data(self.graph)
        edges = data.pop("edges", data.get("links", []))
        data["links"] = edges
        return data
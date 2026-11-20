"""Containerlab Topology Viewer layout and annotations."""

import re


def topology_layout(names, links=()):
    """Lay out fabric roles, grouping member leaves beneath their uplinks."""
    rows = {"bb": 0, "border": 180, "spine": 360, "leaf": 540, "mleaf": 720}
    groups, roles = {}, {}
    for name in names:
        match = re.search(
            r"(?:^|-)(?:([A-D])-)?(bb|border|spine|leaf|mleaf)([0-9]+)$", name
        )
        if not match:
            continue
        site, role, number = match.groups()
        group = "core" if role == "bb" else f"site {site or 'A'}"
        groups.setdefault(group, {}).setdefault(role, []).append((int(number), name))
        roles[name] = (group, role)

    parents = {}
    for link in links:
        endpoints = link.get("connection", [])
        if len(endpoints) != 2:
            continue
        left, right = (str(endpoint).split(":", 1)[0] for endpoint in endpoints)
        for child, parent in ((left, right), (right, left)):
            if (
                roles.get(child, (None, None))[1] == "mleaf"
                and roles.get(parent, (None, None))[1] == "leaf"
                and roles[child][0] == roles[parent][0]
            ):
                parents.setdefault(child, set()).add(parent)

    labels = {}
    sites = sorted(group for group in groups if group != "core")
    cursor = 0
    for group in sites:
        role_nodes = groups[group]
        leaves = [name for _, name in sorted(role_nodes.get("leaf", []))]
        members = [name for _, name in sorted(role_nodes.get("mleaf", []))]
        remaining = list(leaves)
        segments = []
        while remaining:
            leaf = remaining[0]
            connected = next(
                (
                    parents[member]
                    for member in members
                    if leaf in parents.get(member, set())
                    and parents[member].issubset(set(remaining))
                ),
                None,
            )
            selected = (
                [item for item in remaining if item in connected]
                if connected
                else remaining[:2]
            )
            for item in selected:
                remaining.remove(item)
            children = [
                member
                for member in members
                if parents.get(member) and parents[member].issubset(set(selected))
            ]
            segments.append(
                (selected, children, max(320, 200 + max(0, len(children) - 1) * 140))
            )
        loose = [member for member in members if not parents.get(member)]
        leaf_width = sum(segment[2] for segment in segments)
        width = max(
            320,
            leaf_width,
            len(loose) * 160,
            *(
                len(items) * 160
                for role, items in role_nodes.items()
                if role not in ("leaf", "mleaf")
            ),
        )
        center = cursor + width // 2
        for role, items in role_nodes.items():
            if role in ("leaf", "mleaf"):
                continue
            for index, (_, name) in enumerate(sorted(items)):
                x = center + (2 * index - len(items) + 1) * 80
                labels[name] = {
                    "graph-group": group,
                    "graph-posX": str(x),
                    "graph-posY": str(rows[role]),
                }
        segment_cursor = center - leaf_width // 2
        for segment_leaves, children, segment_width in segments:
            midpoint = segment_cursor + segment_width // 2
            for index, name in enumerate(segment_leaves):
                x = midpoint + (2 * index - len(segment_leaves) + 1) * 80
                labels[name] = {
                    "graph-group": group,
                    "graph-posX": str(x),
                    "graph-posY": str(rows["leaf"]),
                }
            for index, name in enumerate(children):
                x = midpoint + (2 * index - len(children) + 1) * 70
                labels[name] = {
                    "graph-group": group,
                    "graph-posX": str(x),
                    "graph-posY": str(rows["mleaf"]),
                }
            segment_cursor += segment_width
        for index, name in enumerate(loose):
            x = center + (2 * index - len(loose) + 1) * 80
            labels[name] = {
                "graph-group": group,
                "graph-posX": str(x),
                "graph-posY": str(rows["mleaf"]),
            }
        cursor += width + 240
    if "core" in groups:
        core = sorted(groups["core"]["bb"])
        center = max(0, cursor - 240) // 2
        for index, (_, name) in enumerate(core):
            x = center + (2 * index - len(core) + 1) * 80
            labels[name] = {
                "graph-group": "core",
                "graph-posX": str(x),
                "graph-posY": "0",
            }
    return labels


def viewer_annotations(layout, node_names):
    """Create explicit Topology Viewer group boxes and node memberships."""
    annotations = {
        "freeTextAnnotations": [],
        "freeShapeAnnotations": [],
        "trafficRateAnnotations": [],
        "scriptButtonAnnotations": [],
        "groupStyleAnnotations": [],
        "networkNodeAnnotations": [],
        "nodeAnnotations": [],
        "edgeAnnotations": [],
        "aliasEndpointAnnotations": [],
        "viewerSettings": {},
    }
    groups = {}
    for name, labels in sorted(layout.items()):
        group = labels["graph-group"]
        point = {"x": int(labels["graph-posX"]), "y": int(labels["graph-posY"])}
        groups.setdefault(group, []).append(point)
        annotations["nodeAnnotations"].append(
            {
                "id": node_names[name],
                "position": point,
                "level": "1",
                "groupId": f"{group}:1",
            }
        )
    for group, points in sorted(groups.items()):
        xmin, xmax = min(p["x"] for p in points), max(p["x"] for p in points)
        ymin, ymax = min(p["y"] for p in points), max(p["y"] for p in points)
        annotations["groupStyleAnnotations"].append(
            {
                "id": f"{group}:1",
                "name": group,
                "level": "1",
                "position": {"x": xmin - 100, "y": ymin - 75},
                "width": xmax - xmin + 200,
                "height": ymax - ymin + 150,
                "backgroundColor": "#d9d9d9",
                "backgroundOpacity": 20,
                "borderColor": "#dddddd",
                "borderWidth": 0.5,
                "borderStyle": "solid",
                "borderRadius": 0,
                "zIndex": -1,
            }
        )
    return annotations


# Containerlab renders the management fields in this shared cEOS template.
# License: docs/licenses/containerlab-ceos-template.txt

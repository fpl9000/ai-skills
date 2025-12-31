#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "drawpyo>=0.2.0",
# ]
# ///
"""
from_data.py - Generate draw.io diagrams from generic node/edge data.

This script creates diagrams from a simple JSON format specifying nodes
and edges. Supports automatic layout or explicit positioning.

USAGE (CLI):
    python from_data.py input.json output.drawio [--layout grid|vertical|horizontal]

USAGE (Module):
    from from_data import create_from_data
    
    data = {
        "nodes": [
            {"id": "a", "label": "Node A"},
            {"id": "b", "label": "Node B"},
            {"id": "c", "label": "Node C"}
        ],
        "edges": [
            {"from": "a", "to": "b", "label": "connects"},
            {"from": "b", "to": "c"}
        ]
    }
    create_from_data(data, "/mnt/user-data/outputs/diagram.drawio")

INPUT FORMAT:
    JSON object with two arrays:
    
    nodes: List of node objects
        - id (required): Unique identifier
        - label (required): Display text
        - x, y (optional): Position coordinates
        - width, height (optional): Dimensions (defaults: 120x60)
        - shape (optional): Shape type (rectangle, ellipse, cylinder, etc.)
        - style (optional): Custom style string
    
    edges: List of edge objects
        - from (required): Source node ID
        - to (required): Target node ID
        - label (optional): Edge label text
        - style (optional): Custom style string

SUPPORTED SHAPES:
    rectangle (default), ellipse, cylinder, cloud, diamond,
    hexagon, triangle, parallelogram, document

AUTO-LAYOUT OPTIONS:
    - grid: Arrange nodes in a grid pattern (default)
    - vertical: Arrange nodes in a vertical column
    - horizontal: Arrange nodes in a horizontal row

EXAMPLE INPUT:
    {
        "nodes": [
            {"id": "lb", "label": "Load Balancer", "shape": "ellipse"},
            {"id": "web1", "label": "Web Server 1"},
            {"id": "web2", "label": "Web Server 2"},
            {"id": "db", "label": "Database", "shape": "cylinder"}
        ],
        "edges": [
            {"from": "lb", "to": "web1"},
            {"from": "lb", "to": "web2"},
            {"from": "web1", "to": "db"},
            {"from": "web2", "to": "db"}
        ]
    }
"""

import json
import sys
import math

# Default node dimensions
DEFAULT_WIDTH = 120
DEFAULT_HEIGHT = 60

# Spacing for auto-layout
GRID_SPACING_X = 180
GRID_SPACING_Y = 120
LINEAR_SPACING = 150

# Shape to library mapping
# Maps user-friendly names to (library, obj_name) tuples
SHAPE_MAPPING = {
    "rectangle": ("general", "rectangle"),
    "ellipse": ("general", "ellipse"),
    "circle": ("general", "ellipse"),
    "cylinder": ("general", "cylinder"),
    "database": ("general", "cylinder"),
    "cloud": ("general", "cloud"),
    "diamond": ("general", "diamond"),
    "hexagon": ("general", "hexagon"),
    "triangle": ("general", "triangle"),
    "parallelogram": ("general", "parallelogram"),
    "document": ("general", "document"),
    "process": ("flowchart", "process"),
    "decision": ("flowchart", "decision"),
    "terminator": ("flowchart", "terminator"),
    "data": ("flowchart", "data"),
    "actor": ("general", "actor"),
}

# Default styles by shape type (fill, stroke)
SHAPE_STYLES = {
    "rectangle": ("#dae8fc", "#6c8ebf"),
    "ellipse": ("#d5e8d4", "#82b366"),
    "circle": ("#d5e8d4", "#82b366"),
    "cylinder": ("#fff2cc", "#d6b656"),
    "database": ("#fff2cc", "#d6b656"),
    "cloud": ("#f5f5f5", "#666666"),
    "diamond": ("#fff2cc", "#d6b656"),
    "hexagon": ("#e1d5e7", "#9673a6"),
    "triangle": ("#ffe6cc", "#d79b00"),
    "parallelogram": ("#e1d5e7", "#9673a6"),
    "document": ("#f8cecc", "#b85450"),
    "process": ("#dae8fc", "#6c8ebf"),
    "decision": ("#fff2cc", "#d6b656"),
    "terminator": ("#d5e8d4", "#82b366"),
    "data": ("#e1d5e7", "#9673a6"),
    "actor": ("#dae8fc", "#6c8ebf"),
}


def apply_layout(nodes, layout="grid", start_x=50, start_y=50):
    """
    Apply automatic positioning to nodes that don't have explicit coordinates.
    
    Args:
        nodes: List of node dictionaries
        layout: Layout type - 'grid', 'vertical', 'horizontal'
        start_x: Starting X coordinate
        start_y: Starting Y coordinate
    
    Returns:
        List of nodes with positions filled in
    """
    # Count nodes that need positioning
    unpositioned = [n for n in nodes if "x" not in n or "y" not in n]
    
    if not unpositioned:
        return nodes  # All nodes already have positions
    
    if layout == "grid":
        # Arrange in a grid (roughly square)
        cols = math.ceil(math.sqrt(len(unpositioned)))
        for i, node in enumerate(unpositioned):
            row = i // cols
            col = i % cols
            if "x" not in node:
                node["x"] = start_x + col * GRID_SPACING_X
            if "y" not in node:
                node["y"] = start_y + row * GRID_SPACING_Y
    
    elif layout == "vertical":
        # Arrange in a vertical column
        for i, node in enumerate(unpositioned):
            if "x" not in node:
                node["x"] = start_x
            if "y" not in node:
                node["y"] = start_y + i * LINEAR_SPACING
    
    elif layout == "horizontal":
        # Arrange in a horizontal row
        for i, node in enumerate(unpositioned):
            if "x" not in node:
                node["x"] = start_x + i * LINEAR_SPACING
            if "y" not in node:
                node["y"] = start_y
    
    return nodes


def create_from_data(data, output_path, layout="grid"):
    """
    Create a draw.io diagram from node and edge data.
    
    Args:
        data: Dictionary with 'nodes' and 'edges' arrays
        output_path: Path where the .drawio file will be saved
        layout: Auto-layout type - 'grid', 'vertical', 'horizontal'
    
    Returns:
        The path to the created file
    
    Raises:
        ImportError: If drawpyo is not installed
        ValueError: If data format is invalid
    """
    # Import drawpyo
    try:
        import drawpyo
    except ImportError:
        print("ERROR: drawpyo is not installed.")
        print("Run this script with: uv run scripts/from_data.py ...")
        print("Or install manually: pip install drawpyo --break-system-packages")
        raise
    
    # Validate input
    if not data:
        raise ValueError("Data cannot be empty")
    
    nodes_data = data.get("nodes", [])
    edges_data = data.get("edges", [])
    
    if not nodes_data:
        raise ValueError("No nodes provided")
    
    # Parse output path
    if "/" in output_path:
        file_path = "/".join(output_path.split("/")[:-1])
        file_name = output_path.split("/")[-1]
    else:
        file_path = "."
        file_name = output_path
    
    # Create file and page
    file = drawpyo.File()
    file.file_path = file_path
    file.file_name = file_name
    page = drawpyo.Page(file=file, name="Diagram")
    
    # Apply auto-layout to nodes without explicit positions
    nodes_data = apply_layout(nodes_data, layout=layout)
    
    # Dictionary to store created node objects by ID
    node_objects = {}
    
    # Create all nodes
    for node_data in nodes_data:
        # Validate required fields
        node_id = node_data.get("id")
        if not node_id:
            raise ValueError(f"Node missing 'id' field: {node_data}")
        
        label = node_data.get("label", node_id)
        shape = node_data.get("shape", "rectangle")
        width = node_data.get("width", DEFAULT_WIDTH)
        height = node_data.get("height", DEFAULT_HEIGHT)
        x = node_data.get("x", 0)
        y = node_data.get("y", 0)
        
        # Create the shape object
        if shape in SHAPE_MAPPING:
            library, obj_name = SHAPE_MAPPING[shape]
            obj = drawpyo.diagram.object_from_library(
                page=page,
                library=library,
                obj_name=obj_name,
                value=label,
                width=width,
                height=height
            )
        else:
            # Fall back to basic rectangle
            obj = drawpyo.diagram.Object(
                page=page,
                value=label,
                width=width,
                height=height
            )
        
        # Set position
        obj.position = (x, y)
        
        # Apply styling
        if "style" in node_data:
            # Use custom style if provided
            obj.apply_style_string(node_data["style"])
        else:
            # Apply default style based on shape
            fill_color, stroke_color = SHAPE_STYLES.get(
                shape, ("#dae8fc", "#6c8ebf")
            )
            style = (
                f"fillColor={fill_color};"
                f"strokeColor={stroke_color};"
                "rounded=1;"
                "whiteSpace=wrap;"
                "html=1;"
            )
            obj.apply_style_string(style)
        
        node_objects[node_id] = obj
    
    # Create all edges
    for edge_data in edges_data:
        # Validate required fields
        from_id = edge_data.get("from")
        to_id = edge_data.get("to")
        
        if not from_id or not to_id:
            raise ValueError(f"Edge missing 'from' or 'to' field: {edge_data}")
        
        if from_id not in node_objects:
            raise ValueError(f"Edge references unknown node: {from_id}")
        if to_id not in node_objects:
            raise ValueError(f"Edge references unknown node: {to_id}")
        
        source = node_objects[from_id]
        target = node_objects[to_id]
        
        # Create the edge
        label = edge_data.get("label", "")
        edge = drawpyo.diagram.Edge(
            page=page,
            source=source,
            target=target,
            label=label if label else None
        )
        
        # Apply styling
        if "style" in edge_data:
            edge.apply_style_string(edge_data["style"])
        else:
            # Default edge style
            edge.apply_style_string("endArrow=classic;html=1;rounded=1;")
    
    # Write to disk
    file.write()
    
    return output_path


def create_architecture_diagram(components, connections, output_path, layout="horizontal"):
    """
    Convenience function for creating architecture diagrams.
    
    Args:
        components: List of component dictionaries with 'id', 'label', and optional 'type'
        connections: List of connection tuples or dicts (source_id, target_id) or {"from": ..., "to": ...}
        output_path: Path where the .drawio file will be saved
        layout: Auto-layout type
    
    Returns:
        The path to the created file
    """
    # Convert components to nodes format
    nodes = []
    for comp in components:
        node = {
            "id": comp["id"],
            "label": comp.get("label", comp["id"]),
            "shape": comp.get("type", comp.get("shape", "rectangle"))
        }
        if "x" in comp:
            node["x"] = comp["x"]
        if "y" in comp:
            node["y"] = comp["y"]
        nodes.append(node)
    
    # Convert connections to edges format
    edges = []
    for conn in connections:
        if isinstance(conn, (tuple, list)):
            edges.append({"from": conn[0], "to": conn[1]})
        else:
            edges.append(conn)
    
    data = {"nodes": nodes, "edges": edges}
    return create_from_data(data, output_path, layout=layout)


def main():
    """Command-line interface for from_data."""
    if len(sys.argv) < 3:
        print("Usage: python from_data.py <input.json> <output.drawio> [options]")
        print("\nOptions:")
        print("  --layout grid|vertical|horizontal  (default: grid)")
        print("\nExample:")
        print("  python from_data.py architecture.json diagram.drawio --layout horizontal")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Parse optional arguments
    layout = "grid"
    
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--layout" and i + 1 < len(sys.argv):
            layout = sys.argv[i + 1]
            i += 2
        else:
            i += 1
    
    # Load the JSON input
    try:
        with open(input_file, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {input_file}: {e}")
        sys.exit(1)
    
    # Create the diagram
    try:
        result = create_from_data(data, output_file, layout=layout)
        print(f"Created diagram: {result}")
    except Exception as e:
        print(f"ERROR: Failed to create diagram: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

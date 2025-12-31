#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "drawpyo>=0.2.0",
# ]
# ///
"""
create_tree.py - Generate draw.io tree diagrams with automatic layout.

This script creates hierarchical tree diagrams from nested data structures.
It uses drawpyo's TreeDiagram class for automatic positioning and layout.

USAGE (CLI):
    python create_tree.py input.json output.drawio [--direction down|up|left|right]

USAGE (Module):
    from create_tree import create_tree, create_tree_from_list
    
    # From nested dictionary
    hierarchy = {
        "label": "Root",
        "children": [
            {"label": "Child 1"},
            {"label": "Child 2", "children": [{"label": "Grandchild"}]}
        ]
    }
    create_tree(hierarchy, "/mnt/user-data/outputs/tree.drawio")
    
    # From flat list with parent references
    items = [
        {"id": "root", "label": "Root", "parent": None},
        {"id": "child1", "label": "Child 1", "parent": "root"},
        {"id": "child2", "label": "Child 2", "parent": "root"},
    ]
    create_tree_from_list(items, "/mnt/user-data/outputs/tree.drawio")

INPUT FORMAT (Nested):
    Dictionary with these fields:
    - label (required): Text displayed in the node
    - children (optional): List of child node dictionaries
    - style (optional): Custom style string to apply

INPUT FORMAT (Flat List):
    List of dictionaries with:
    - id (required): Unique identifier
    - label (required): Text displayed in the node
    - parent (required): ID of parent node, or null/None for root

DIRECTIONS:
    - down: Root at top, children below (default, good for org charts)
    - up: Root at bottom, children above
    - left: Root at right, children to the left
    - right: Root at left, children to the right (good for decision trees)

LINK STYLES:
    - orthogonal: Right-angle connectors (default)
    - straight: Direct line connections
    - curved: Curved bezier connections
"""

import json
import sys

# Color palette for different tree levels
# Each tuple is (fill_color, stroke_color)
LEVEL_COLORS = [
    ("#dae8fc", "#6c8ebf"),  # Level 0 (root): Blue
    ("#d5e8d4", "#82b366"),  # Level 1: Green
    ("#fff2cc", "#d6b656"),  # Level 2: Yellow
    ("#e1d5e7", "#9673a6"),  # Level 3: Purple
    ("#f8cecc", "#b85450"),  # Level 4: Red
    ("#ffe6cc", "#d79b00"),  # Level 5: Orange
]

# Default node dimensions
DEFAULT_WIDTH = 120
DEFAULT_HEIGHT = 60


def create_tree(hierarchy, output_path, direction="down", link_style="orthogonal",
                level_spacing=80, item_spacing=30):
    """
    Create a draw.io tree diagram from a nested dictionary structure.
    
    Args:
        hierarchy: Nested dictionary with 'label' and optional 'children' keys
        output_path: Path where the .drawio file will be saved
        direction: Tree growth direction - 'down', 'up', 'left', 'right'
        link_style: Edge style - 'orthogonal', 'straight', 'curved'
        level_spacing: Vertical/horizontal space between tree levels
        item_spacing: Space between sibling nodes
    
    Returns:
        The path to the created file
    
    Raises:
        ImportError: If drawpyo is not installed
        ValueError: If hierarchy format is invalid
    """
    # Import drawpyo
    try:
        from drawpyo.diagram_types import TreeDiagram, NodeObject
    except ImportError:
        print("ERROR: drawpyo is not installed.")
        print("Run this script with: uv run scripts/create_tree.py ...")
        print("Or install manually: pip install drawpyo --break-system-packages")
        raise
    
    # Validate input
    if not hierarchy:
        raise ValueError("Hierarchy cannot be empty")
    if "label" not in hierarchy:
        raise ValueError("Root node must have a 'label' field")
    
    # Parse output path
    if "/" in output_path:
        file_path = "/".join(output_path.split("/")[:-1])
        file_name = output_path.split("/")[-1]
    else:
        file_path = "."
        file_name = output_path
    
    # Create the tree diagram
    tree = TreeDiagram(
        file_path=file_path,
        file_name=file_name,
        direction=direction,
        link_style=link_style,
        level_spacing=level_spacing,
        item_spacing=item_spacing
    )
    
    def add_node(data, parent=None, level=0):
        """Recursively add nodes to the tree."""
        # Get label text
        label = data.get("label", "Node")
        
        # Create the node
        node = NodeObject(
            tree=tree,
            value=label,
            parent=parent,
            width=DEFAULT_WIDTH,
            height=DEFAULT_HEIGHT
        )
        
        # Apply level-based coloring
        color_index = level % len(LEVEL_COLORS)
        fill_color, stroke_color = LEVEL_COLORS[color_index]
        
        # Build style string
        style = (
            f"fillColor={fill_color};"
            f"strokeColor={stroke_color};"
            "rounded=1;"
            "whiteSpace=wrap;"
            "html=1;"
        )
        
        # Apply custom style if provided (overrides defaults)
        if "style" in data:
            style = data["style"]
        
        node.apply_style_string(style)
        
        # Recursively add children
        for child_data in data.get("children", []):
            add_node(child_data, parent=node, level=level + 1)
        
        return node
    
    # Build the tree starting from root
    add_node(hierarchy, parent=None, level=0)
    
    # Apply automatic layout
    tree.auto_layout()
    
    # Write to disk
    tree.write()
    
    return output_path


def create_tree_from_list(items, output_path, direction="down", link_style="orthogonal",
                          level_spacing=80, item_spacing=30):
    """
    Create a draw.io tree diagram from a flat list with parent references.
    
    Args:
        items: List of dictionaries with 'id', 'label', and 'parent' fields
        output_path: Path where the .drawio file will be saved
        direction: Tree growth direction - 'down', 'up', 'left', 'right'
        link_style: Edge style - 'orthogonal', 'straight', 'curved'
        level_spacing: Vertical/horizontal space between tree levels
        item_spacing: Space between sibling nodes
    
    Returns:
        The path to the created file
    """
    # Import drawpyo
    try:
        from drawpyo.diagram_types import TreeDiagram, NodeObject
    except ImportError:
        print("ERROR: drawpyo is not installed.")
        print("Run this script with: uv run scripts/create_tree.py ...")
        print("Or install manually: pip install drawpyo --break-system-packages")
        raise
    
    # Validate input
    if not items:
        raise ValueError("Items list cannot be empty")
    
    # Build a lookup dictionary for items by ID
    items_by_id = {}
    for item in items:
        if "id" not in item:
            raise ValueError(f"Item missing 'id' field: {item}")
        items_by_id[item["id"]] = item
    
    # Find root nodes (items with no parent or parent=None)
    roots = [item for item in items if not item.get("parent")]
    if not roots:
        raise ValueError("No root node found (need at least one item with parent=None)")
    
    # Parse output path
    if "/" in output_path:
        file_path = "/".join(output_path.split("/")[:-1])
        file_name = output_path.split("/")[-1]
    else:
        file_path = "."
        file_name = output_path
    
    # Create the tree diagram
    tree = TreeDiagram(
        file_path=file_path,
        file_name=file_name,
        direction=direction,
        link_style=link_style,
        level_spacing=level_spacing,
        item_spacing=item_spacing
    )
    
    # Dictionary to store created nodes by their ID
    nodes_by_id = {}
    
    def get_level(item_id, depth=0):
        """Calculate the level of a node in the tree."""
        item = items_by_id.get(item_id)
        if not item or not item.get("parent"):
            return depth
        return get_level(item["parent"], depth + 1)
    
    def create_node(item, parent_node=None):
        """Create a node and recursively create its children."""
        item_id = item["id"]
        label = item.get("label", item_id)
        level = get_level(item_id)
        
        # Create the node
        node = NodeObject(
            tree=tree,
            value=label,
            parent=parent_node,
            width=DEFAULT_WIDTH,
            height=DEFAULT_HEIGHT
        )
        
        # Apply level-based coloring
        color_index = level % len(LEVEL_COLORS)
        fill_color, stroke_color = LEVEL_COLORS[color_index]
        
        style = (
            f"fillColor={fill_color};"
            f"strokeColor={stroke_color};"
            "rounded=1;"
            "whiteSpace=wrap;"
            "html=1;"
        )
        
        if "style" in item:
            style = item["style"]
        
        node.apply_style_string(style)
        nodes_by_id[item_id] = node
        
        # Find and create children
        children = [i for i in items if i.get("parent") == item_id]
        for child in children:
            create_node(child, parent_node=node)
        
        return node
    
    # Create all trees starting from root nodes
    for root in roots:
        create_node(root, parent_node=None)
    
    # Apply automatic layout
    tree.auto_layout()
    
    # Write to disk
    tree.write()
    
    return output_path


def main():
    """Command-line interface for create_tree."""
    # Parse arguments
    if len(sys.argv) < 3:
        print("Usage: python create_tree.py <input.json> <output.drawio> [options]")
        print("\nOptions:")
        print("  --direction down|up|left|right  (default: down)")
        print("  --link-style orthogonal|straight|curved  (default: orthogonal)")
        print("\nExample:")
        print("  python create_tree.py org.json org_chart.drawio --direction down")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Parse optional arguments
    direction = "down"
    link_style = "orthogonal"
    
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--direction" and i + 1 < len(sys.argv):
            direction = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--link-style" and i + 1 < len(sys.argv):
            link_style = sys.argv[i + 1]
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
    
    # Determine format and create tree
    try:
        if isinstance(data, list):
            # Flat list format with parent references
            result = create_tree_from_list(
                data, output_file, 
                direction=direction, 
                link_style=link_style
            )
        else:
            # Nested dictionary format
            result = create_tree(
                data, output_file,
                direction=direction,
                link_style=link_style
            )
        print(f"Created tree diagram: {result}")
    except Exception as e:
        print(f"ERROR: Failed to create tree: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

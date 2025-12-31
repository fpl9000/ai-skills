#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "drawpyo>=0.2.0",
# ]
# ///
"""
create_flowchart.py - Generate draw.io flowcharts from step definitions.

This script creates flowchart diagrams from a simple JSON/dict format.
It handles automatic positioning and default styling for common flowchart shapes.

USAGE (CLI):
    python create_flowchart.py input.json output.drawio

USAGE (Module):
    from create_flowchart import create_flowchart
    steps = [
        {"id": "start", "type": "terminator", "label": "Start", "next": "step1"},
        {"id": "step1", "type": "process", "label": "Do Thing", "next": "end"},
        {"id": "end", "type": "terminator", "label": "End"}
    ]
    create_flowchart(steps, "/mnt/user-data/outputs/flow.drawio")

INPUT FORMAT:
    List of step dictionaries with these fields:
    - id (required): Unique identifier for the step
    - type (required): Shape type - terminator, process, decision, data, document
    - label (required): Text displayed in the shape
    - next (optional): ID of the next step (for linear flow)
    - yes (optional): ID of the "yes" branch (for decisions)
    - no (optional): ID of the "no" branch (for decisions)

SUPPORTED TYPES:
    - terminator: Rounded rectangle (start/end points)
    - process: Rectangle (actions/operations)
    - decision: Diamond (yes/no branches)
    - data: Parallelogram (input/output)
    - document: Wavy bottom (documents)

EXAMPLE INPUT (JSON file):
    [
        {"id": "start", "type": "terminator", "label": "Start", "next": "input"},
        {"id": "input", "type": "data", "label": "Get Input", "next": "check"},
        {"id": "check", "type": "decision", "label": "Valid?", "yes": "process", "no": "error"},
        {"id": "error", "type": "process", "label": "Show Error", "next": "input"},
        {"id": "process", "type": "process", "label": "Process", "next": "end"},
        {"id": "end", "type": "terminator", "label": "End"}
    ]
"""

import json
import sys

# Default colors for each shape type (fill, stroke)
# These match draw.io's default color palette
DEFAULT_COLORS = {
    "terminator": ("#d5e8d4", "#82b366"),  # Green - start/end points
    "process": ("#dae8fc", "#6c8ebf"),     # Blue - standard process
    "decision": ("#fff2cc", "#d6b656"),    # Yellow - decision points
    "data": ("#e1d5e7", "#9673a6"),        # Purple - data input/output
    "document": ("#f8cecc", "#b85450"),    # Red - documents
}

# Default dimensions for shapes (width, height)
DEFAULT_SIZES = {
    "terminator": (120, 40),
    "process": (120, 60),
    "decision": (120, 80),
    "data": (120, 60),
    "document": (120, 60),
}

# Vertical spacing between shapes in the flowchart
VERTICAL_SPACING = 100

# Horizontal offset for branching paths (e.g., "no" branch of decisions)
HORIZONTAL_OFFSET = 200


def create_flowchart(steps, output_path, start_x=200, start_y=50):
    """
    Create a draw.io flowchart from a list of step definitions.
    
    Args:
        steps: List of step dictionaries (see module docstring for format)
        output_path: Path where the .drawio file will be saved
        start_x: X coordinate for the main flow (default: 200)
        start_y: Y coordinate for the first shape (default: 50)
    
    Returns:
        The path to the created file
    
    Raises:
        ImportError: If drawpyo is not installed
        ValueError: If step format is invalid
    """
    # Import drawpyo (will raise ImportError with helpful message if not installed)
    try:
        import drawpyo
    except ImportError:
        print("ERROR: drawpyo is not installed.")
        print("Run this script with: uv run scripts/create_flowchart.py ...")
        print("Or install manually: pip install drawpyo --break-system-packages")
        raise
    
    # Validate input
    if not steps:
        raise ValueError("Steps list cannot be empty")
    
    # Create the file and page
    file = drawpyo.File()
    
    # Parse output path into directory and filename
    if "/" in output_path:
        file.file_path = "/".join(output_path.split("/")[:-1])
        file.file_name = output_path.split("/")[-1]
    else:
        file.file_path = "."
        file.file_name = output_path
    
    page = drawpyo.Page(file=file, name="Flowchart")
    
    # Dictionary to store created objects by their ID
    # This allows us to create edges between them later
    objects = {}
    
    # Track positions for layout
    # Main flow goes down the center, branches go to the side
    main_y = start_y
    branch_positions = {}  # Track where branch nodes are placed
    
    # First pass: Create all shape objects
    for step in steps:
        # Validate required fields
        step_id = step.get("id")
        step_type = step.get("type", "process")
        label = step.get("label", step_id)
        
        if not step_id:
            raise ValueError(f"Step missing required 'id' field: {step}")
        
        # Get shape dimensions and colors
        width, height = DEFAULT_SIZES.get(step_type, (120, 60))
        fill_color, stroke_color = DEFAULT_COLORS.get(step_type, ("#dae8fc", "#6c8ebf"))
        
        # Create the shape from the flowchart library
        obj = drawpyo.diagram.object_from_library(
            page=page,
            library="flowchart",
            obj_name=step_type,
            value=label,
            width=width,
            height=height
        )
        
        # Apply styling
        style_string = (
            f"fillColor={fill_color};"
            f"strokeColor={stroke_color};"
            "whiteSpace=wrap;"
            "html=1;"
        )
        obj.apply_style_string(style_string)
        
        # Store the object for later edge creation
        objects[step_id] = {
            "obj": obj,
            "step": step,
            "positioned": False
        }
    
    # Second pass: Position objects
    # Start with objects that have no incoming edges (entry points)
    positioned_count = 0
    current_y = start_y
    
    # Find the starting node (first in list, or one with no incoming references)
    incoming = set()
    for step in steps:
        for field in ["next", "yes", "no"]:
            if field in step:
                incoming.add(step[field])
    
    # Position nodes in order, following the flow
    for step in steps:
        step_id = step["id"]
        obj_data = objects[step_id]
        
        if not obj_data["positioned"]:
            # Position on the main flow
            width, height = DEFAULT_SIZES.get(step.get("type", "process"), (120, 60))
            obj_data["obj"].position = (start_x - width/2, current_y)
            obj_data["positioned"] = True
            current_y += height + VERTICAL_SPACING - 40
    
    # Third pass: Create edges between connected shapes
    for step in steps:
        step_id = step["id"]
        source_obj = objects[step_id]["obj"]
        
        # Handle "next" connection (simple linear flow)
        if "next" in step:
            target_id = step["next"]
            if target_id in objects:
                target_obj = objects[target_id]["obj"]
                edge = drawpyo.diagram.Edge(
                    page=page,
                    source=source_obj,
                    target=target_obj
                )
                # Style the edge with an arrow
                edge.apply_style_string("endArrow=classic;html=1;")
        
        # Handle "yes" branch (for decisions)
        if "yes" in step:
            target_id = step["yes"]
            if target_id in objects:
                target_obj = objects[target_id]["obj"]
                edge = drawpyo.diagram.Edge(
                    page=page,
                    source=source_obj,
                    target=target_obj,
                    label="Yes"
                )
                edge.apply_style_string("endArrow=classic;html=1;")
        
        # Handle "no" branch (for decisions)
        if "no" in step:
            target_id = step["no"]
            if target_id in objects:
                target_obj = objects[target_id]["obj"]
                edge = drawpyo.diagram.Edge(
                    page=page,
                    source=source_obj,
                    target=target_obj,
                    label="No"
                )
                edge.apply_style_string("endArrow=classic;html=1;")
    
    # Write the file to disk
    file.write()
    
    return output_path


def main():
    """Command-line interface for create_flowchart."""
    # Check command line arguments
    if len(sys.argv) < 3:
        print("Usage: python create_flowchart.py <input.json> <output.drawio>")
        print("\nExample:")
        print("  python create_flowchart.py steps.json flowchart.drawio")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Load the JSON input
    try:
        with open(input_file, "r") as f:
            steps = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {input_file}: {e}")
        sys.exit(1)
    
    # Create the flowchart
    try:
        result = create_flowchart(steps, output_file)
        print(f"Created flowchart: {result}")
    except Exception as e:
        print(f"ERROR: Failed to create flowchart: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

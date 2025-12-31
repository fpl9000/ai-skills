# Draw.io Generation Reference

## Table of Contents
1. [File and Page Structure](#file-and-page-structure)
2. [Objects (Shapes)](#objects-shapes)
3. [Edges (Connections)](#edges-connections)
4. [Styling](#styling)
5. [Tree Diagrams](#tree-diagrams)
6. [Shape Libraries](#shape-libraries)
7. [Positioning and Layout](#positioning-and-layout)
8. [Common Patterns](#common-patterns)

---

## File and Page Structure

### Creating a File

For custom scripts, add inline dependency metadata and run with `uv run`:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["drawpyo>=0.2.0"]
# ///
import drawpyo

# Create file object
file = drawpyo.File()
file.file_path = "/mnt/user-data/outputs"  # Output directory
file.file_name = "my_diagram.drawio"       # Filename with extension

# Add one or more pages
page1 = drawpyo.Page(file=file, name="Overview")
page2 = drawpyo.Page(file=file, name="Details")

# ... add objects to pages ...

# Write to disk
file.write()
```

Run with: `uv run my_script.py`

### Page Properties
```python
page = drawpyo.Page(file=file)
page.name = "Page Title"           # Tab name in draw.io
page.width = 850                   # Page width (pixels)
page.height = 1100                 # Page height (pixels)
```

---

## Objects (Shapes)

### Basic Object Creation
```python
# Minimal object
obj = drawpyo.diagram.Object(page=page, value="Label Text")
obj.position = (100, 200)  # (x, y) from top-left

# With explicit dimensions
obj = drawpyo.diagram.Object(
    page=page,
    value="My Shape",
    width=150,
    height=80,
    position=(100, 100)
)
```

### Object Properties
```python
obj.value = "Label"          # Text inside shape
obj.position = (x, y)        # Tuple of coordinates
obj.width = 120              # Width in pixels
obj.height = 60              # Height in pixels

# Geometry (alternative to position)
obj.geometry.x = 100
obj.geometry.y = 200
```

### Creating from Shape Libraries
```python
# Use pre-defined shapes from draw.io libraries
obj = drawpyo.diagram.object_from_library(
    page=page,
    library="general",       # Library name
    obj_name="process",      # Shape name within library
    value="Process Step",    # Label text
    width=120,               # Optional: override default width
    height=60                # Optional: override default height
)
obj.position = (100, 100)
```

---

## Edges (Connections)

### Basic Edge
```python
edge = drawpyo.diagram.Edge(
    page=page,
    source=source_obj,       # Object to connect from
    target=target_obj        # Object to connect to
)
```

### Edge with Label
```python
edge = drawpyo.diagram.Edge(
    page=page,
    source=obj1,
    target=obj2,
    label="relationship"     # Text on the edge
)
```

### Edge Styles
```python
edge = drawpyo.diagram.Edge(page=page, source=obj1, target=obj2)

# Arrow styles
edge.endArrow = "classic"    # classic, block, open, oval, diamond, none
edge.startArrow = "none"     # Same options

# Line styles  
edge.strokeColor = "#000000"
edge.strokeWidth = 2
edge.dashed = True           # Dashed line

# Routing
edge.edgeStyle = "orthogonalEdgeStyle"  # Right-angle routing
# Other options: "elbowEdgeStyle", "entityRelationEdgeStyle"
```

### Connecting to Specific Points
```python
# Connect to specific sides of shapes
edge.exitX = 1       # Exit from right side (0=left, 0.5=center, 1=right)
edge.exitY = 0.5     # Exit from vertical center
edge.entryX = 0      # Enter on left side
edge.entryY = 0.5    # Enter at vertical center
```

---

## Styling

### Style Strings
Draw.io uses semicolon-separated style strings. Apply them directly:
```python
obj.apply_style_string(
    "rounded=1;"
    "whiteSpace=wrap;"
    "html=1;"
    "fillColor=#d5e8d4;"
    "strokeColor=#82b366;"
    "fontColor=#000000;"
    "fontSize=12;"
    "fontStyle=1;"  # 1=bold, 2=italic, 4=underline (additive)
)
```

### Common Style Properties

| Property | Values | Description |
|----------|--------|-------------|
| `fillColor` | `#RRGGBB` | Background color |
| `strokeColor` | `#RRGGBB` | Border color |
| `fontColor` | `#RRGGBB` | Text color |
| `strokeWidth` | `1`, `2`, ... | Border thickness |
| `fontSize` | `12`, `14`, ... | Font size in points |
| `fontStyle` | `0`, `1`, `2`, `4` | 0=normal, 1=bold, 2=italic, 4=underline |
| `rounded` | `0`, `1` | Rounded corners |
| `dashed` | `0`, `1` | Dashed border |
| `opacity` | `0`-`100` | Transparency |
| `shadow` | `0`, `1` | Drop shadow |
| `glass` | `0`, `1` | Glass/gradient effect |

### Color Presets (draw.io defaults)
```python
# Blues
LIGHT_BLUE = "#dae8fc"
BLUE_STROKE = "#6c8ebf"

# Greens  
LIGHT_GREEN = "#d5e8d4"
GREEN_STROKE = "#82b366"

# Yellows/Oranges
LIGHT_YELLOW = "#fff2cc"
YELLOW_STROKE = "#d6b656"
LIGHT_ORANGE = "#ffe6cc"
ORANGE_STROKE = "#d79b00"

# Reds
LIGHT_RED = "#f8cecc"
RED_STROKE = "#b85450"

# Purples
LIGHT_PURPLE = "#e1d5e7"
PURPLE_STROKE = "#9673a6"

# Grays
LIGHT_GRAY = "#f5f5f5"
GRAY_STROKE = "#666666"
```

---

## Tree Diagrams

Drawpyo provides automatic tree layout for hierarchical diagrams.

### Basic Tree
```python
from drawpyo.diagram_types import TreeDiagram, NodeObject

# Create tree diagram (automatically creates file and page)
tree = TreeDiagram(
    file_path="/mnt/user-data/outputs",
    file_name="org_chart.drawio",
    direction="down",        # down, up, left, right
    link_style="orthogonal"  # orthogonal, straight, curved
)

# Create nodes
ceo = NodeObject(tree=tree, value="CEO", base_style="rounded")
cto = NodeObject(tree=tree, value="CTO", parent=ceo)
cfo = NodeObject(tree=tree, value="CFO", parent=ceo)

eng1 = NodeObject(tree=tree, value="Engineer 1", parent=cto)
eng2 = NodeObject(tree=tree, value="Engineer 2", parent=cto)

# Auto-layout and save
tree.auto_layout()
tree.write()
```

### Tree Properties
```python
tree = TreeDiagram(
    file_path="./output",
    file_name="tree.drawio",
    direction="down",           # Growth direction
    link_style="orthogonal",    # Edge routing style
    level_spacing=60,           # Vertical space between levels
    item_spacing=20,            # Horizontal space between siblings
    padding=20                  # Padding around the diagram
)
```

### NodeObject Properties
```python
node = NodeObject(
    tree=tree,
    value="Node Label",
    parent=parent_node,     # None for root
    width=120,
    height=60
)

# Styling
node.base_style = "rounded"  # Base shape style
node.apply_style_string("fillColor=#dae8fc;")
```

---

## Shape Libraries

### General Library (`library="general"`)
```
rectangle, ellipse, square, circle, process, diamond, 
parallelogram, hexagon, triangle, cylinder, cloud, 
document, note, actor, cross, corner
```

### Flowchart Library (`library="flowchart"`)
```
terminator         # Rounded rectangle (start/end)
process            # Rectangle (action)
decision           # Diamond (if/then)
data               # Parallelogram (input/output)
document           # Wavy bottom (document)
predefined_process # Rectangle with lines (subroutine)
stored_data        # Curved side (database-ish)
internal_storage   # Rectangle with corners
manual_input       # Slanted top
manual_operation   # Trapezoid
preparation        # Hexagon
```

### Basic Library (`library="basic"`)
```
rectangle, ellipse, rhombus, triangle, pentagon, 
hexagon, heptagon, octagon, star, arrow
```

### UML Library (`library="uml"`)
```
class, interface, package, component, node, 
artifact, usecase, actor
```

---

## Positioning and Layout

### Coordinate System
- Origin (0, 0) is top-left of the page
- X increases to the right
- Y increases downward
- Units are pixels

### Manual Grid Layout
```python
def grid_layout(objects, columns=3, start_x=50, start_y=50, 
                spacing_x=150, spacing_y=100):
    """Arrange objects in a grid pattern."""
    for i, obj in enumerate(objects):
        row = i // columns
        col = i % columns
        obj.position = (
            start_x + col * spacing_x,
            start_y + row * spacing_y
        )
```

### Flowchart Layout (Top to Bottom)
```python
def vertical_flow(objects, start_x=200, start_y=50, spacing=100):
    """Arrange objects in a vertical flow."""
    for i, obj in enumerate(objects):
        obj.position = (start_x - obj.width/2, start_y + i * spacing)
```

---

## Common Patterns

### Flowchart with Decision
```python
import drawpyo

file = drawpyo.File()
file.file_path = "/mnt/user-data/outputs"
file.file_name = "flowchart.drawio"
page = drawpyo.Page(file=file)

# Create shapes
start = drawpyo.diagram.object_from_library(
    page=page, library="flowchart", obj_name="terminator", value="Start"
)
start.position = (200, 50)

process = drawpyo.diagram.object_from_library(
    page=page, library="flowchart", obj_name="process", value="Do Something"
)
process.position = (200, 150)

decision = drawpyo.diagram.object_from_library(
    page=page, library="flowchart", obj_name="decision", value="Success?"
)
decision.position = (200, 250)

end_yes = drawpyo.diagram.object_from_library(
    page=page, library="flowchart", obj_name="terminator", value="Done"
)
end_yes.position = (200, 380)

retry = drawpyo.diagram.object_from_library(
    page=page, library="flowchart", obj_name="process", value="Retry"
)
retry.position = (400, 250)

# Create edges
drawpyo.diagram.Edge(page=page, source=start, target=process)
drawpyo.diagram.Edge(page=page, source=process, target=decision)
drawpyo.diagram.Edge(page=page, source=decision, target=end_yes, label="Yes")
drawpyo.diagram.Edge(page=page, source=decision, target=retry, label="No")
drawpyo.diagram.Edge(page=page, source=retry, target=process)

file.write()
```

### Architecture Diagram
```python
import drawpyo

file = drawpyo.File()
file.file_path = "/mnt/user-data/outputs"  
file.file_name = "architecture.drawio"
page = drawpyo.Page(file=file)

# Style helpers
def styled_box(page, label, x, y, fill="#dae8fc", stroke="#6c8ebf"):
    obj = drawpyo.diagram.Object(page=page, value=label, width=100, height=60)
    obj.position = (x, y)
    obj.apply_style_string(
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
    )
    return obj

# Create components
client = styled_box(page, "Client", 50, 100, "#d5e8d4", "#82b366")
api = styled_box(page, "API Gateway", 200, 100)
service = styled_box(page, "Service", 350, 100)
db = styled_box(page, "Database", 500, 100, "#fff2cc", "#d6b656")

# Connect them
for source, target in [(client, api), (api, service), (service, db)]:
    edge = drawpyo.diagram.Edge(page=page, source=source, target=target)
    edge.apply_style_string("endArrow=classic;")

file.write()
```

---

## Troubleshooting

### Common Issues

**"Module not found: drawpyo"**
- If running helper scripts: use `uv run scripts/script_name.py` instead of `python`
- If writing custom code: add inline script metadata and use `uv run`
- Alternative (not recommended): `pip install drawpyo --break-system-packages`

**Objects overlapping**
- Increase spacing in your positioning logic
- Use explicit width/height values
- Consider using TreeDiagram for automatic layout

**Edges not connecting properly**
- Ensure source and target objects are added to the same page
- Check that objects have valid positions set

**Style not applying**
- Style strings must end with semicolon
- Property names are case-sensitive (camelCase)
- Check for typos in color codes (must include #)

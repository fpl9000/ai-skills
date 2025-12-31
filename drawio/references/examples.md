# Draw.io Diagram Examples

All examples below can be saved as `.py` files and run with `uv run`. Add the following header to make them self-contained:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["drawpyo>=0.2.0"]
# ///
```

Then run with: `uv run my_example.py`

---

## Example 1: Simple Flowchart

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["drawpyo>=0.2.0"]
# ///
import drawpyo

file = drawpyo.File()
file.file_path = "/mnt/user-data/outputs"
file.file_name = "simple_flow.drawio"
page = drawpyo.Page(file=file)

# Create terminator for start
start = drawpyo.diagram.object_from_library(
    page=page, library="flowchart", obj_name="terminator", value="Start"
)
start.position = (200, 50)
start.apply_style_string("fillColor=#d5e8d4;strokeColor=#82b366;")

# Process step
step1 = drawpyo.diagram.object_from_library(
    page=page, library="flowchart", obj_name="process", value="Process Data"
)
step1.position = (200, 150)

# End
end = drawpyo.diagram.object_from_library(
    page=page, library="flowchart", obj_name="terminator", value="End"
)
end.position = (200, 250)
end.apply_style_string("fillColor=#f8cecc;strokeColor=#b85450;")

# Connect with edges
drawpyo.diagram.Edge(page=page, source=start, target=step1)
drawpyo.diagram.Edge(page=page, source=step1, target=end)

file.write()
```

---

## Example 2: Organization Chart (Using TreeDiagram)

```python
from drawpyo.diagram_types import TreeDiagram, NodeObject

# Create tree with automatic layout
tree = TreeDiagram(
    file_path="/mnt/user-data/outputs",
    file_name="org_chart.drawio",
    direction="down",
    link_style="orthogonal",
    level_spacing=80,
    item_spacing=30
)

# Build hierarchy
ceo = NodeObject(tree=tree, value="CEO\nJane Smith")
ceo.apply_style_string("fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;")

cto = NodeObject(tree=tree, value="CTO\nBob Jones", parent=ceo)
cfo = NodeObject(tree=tree, value="CFO\nAlice Lee", parent=ceo)
coo = NodeObject(tree=tree, value="COO\nTom Chen", parent=ceo)

# Engineering team under CTO
eng1 = NodeObject(tree=tree, value="Lead Engineer", parent=cto)
eng2 = NodeObject(tree=tree, value="Senior Dev", parent=cto)
eng3 = NodeObject(tree=tree, value="Junior Dev", parent=cto)

# Finance team under CFO
fin1 = NodeObject(tree=tree, value="Controller", parent=cfo)
fin2 = NodeObject(tree=tree, value="Analyst", parent=cfo)

# Auto-position everything and save
tree.auto_layout()
tree.write()
```

---

## Example 3: System Architecture Diagram

```python
import drawpyo

file = drawpyo.File()
file.file_path = "/mnt/user-data/outputs"
file.file_name = "architecture.drawio"
page = drawpyo.Page(file=file)

# Color scheme
BLUE = ("fillColor=#dae8fc;strokeColor=#6c8ebf;rounded=1;whiteSpace=wrap;html=1;")
GREEN = ("fillColor=#d5e8d4;strokeColor=#82b366;rounded=1;whiteSpace=wrap;html=1;")
YELLOW = ("fillColor=#fff2cc;strokeColor=#d6b656;rounded=1;whiteSpace=wrap;html=1;")
PURPLE = ("fillColor=#e1d5e7;strokeColor=#9673a6;rounded=1;whiteSpace=wrap;html=1;")

def create_box(page, label, x, y, style, width=120, height=60):
    obj = drawpyo.diagram.Object(page=page, value=label, width=width, height=height)
    obj.position = (x, y)
    obj.apply_style_string(style)
    return obj

# Frontend tier
web = create_box(page, "Web App", 50, 50, GREEN)
mobile = create_box(page, "Mobile App", 50, 130, GREEN)

# API tier
api = create_box(page, "API Gateway", 220, 90, BLUE)

# Services tier
auth = create_box(page, "Auth Service", 390, 30, PURPLE)
users = create_box(page, "User Service", 390, 110, PURPLE)
orders = create_box(page, "Order Service", 390, 190, PURPLE)

# Data tier
db = create_box(page, "PostgreSQL", 560, 70, YELLOW)
cache = create_box(page, "Redis", 560, 150, YELLOW)

# Connections
for src in [web, mobile]:
    drawpyo.diagram.Edge(page=page, source=src, target=api)

for svc in [auth, users, orders]:
    drawpyo.diagram.Edge(page=page, source=api, target=svc)

for svc in [auth, users, orders]:
    drawpyo.diagram.Edge(page=page, source=svc, target=db)
    
drawpyo.diagram.Edge(page=page, source=users, target=cache)

file.write()
```

---

## Example 4: Decision Flowchart with Branches

```python
import drawpyo

file = drawpyo.File()
file.file_path = "/mnt/user-data/outputs"
file.file_name = "decision_flow.drawio"
page = drawpyo.Page(file=file)

# Helper to create styled flowchart shapes
def flow_shape(page, shape_type, label, x, y):
    obj = drawpyo.diagram.object_from_library(
        page=page, library="flowchart", obj_name=shape_type, value=label
    )
    obj.position = (x, y)
    return obj

# Create nodes
start = flow_shape(page, "terminator", "User Request", 200, 20)
validate = flow_shape(page, "process", "Validate Input", 200, 100)
valid_check = flow_shape(page, "decision", "Valid?", 200, 200)
process = flow_shape(page, "process", "Process Request", 200, 320)
error = flow_shape(page, "process", "Return Error", 400, 200)
success = flow_shape(page, "terminator", "Return Response", 200, 420)

# Style the decision diamond
valid_check.apply_style_string("fillColor=#fff2cc;strokeColor=#d6b656;")

# Connect nodes
drawpyo.diagram.Edge(page=page, source=start, target=validate)
drawpyo.diagram.Edge(page=page, source=validate, target=valid_check)

yes_edge = drawpyo.diagram.Edge(page=page, source=valid_check, target=process, label="Yes")
no_edge = drawpyo.diagram.Edge(page=page, source=valid_check, target=error, label="No")

drawpyo.diagram.Edge(page=page, source=process, target=success)

file.write()
```

---

## Example 5: Using the Helper Scripts

### Flowchart from JSON
```python
from scripts.create_flowchart import create_flowchart

steps = [
    {"id": "start", "type": "terminator", "label": "Begin", "next": "input"},
    {"id": "input", "type": "data", "label": "Get User Input", "next": "check"},
    {"id": "check", "type": "decision", "label": "Input Valid?", "yes": "process", "no": "error"},
    {"id": "error", "type": "process", "label": "Show Error", "next": "input"},
    {"id": "process", "type": "process", "label": "Process Data", "next": "end"},
    {"id": "end", "type": "terminator", "label": "Done"}
]

create_flowchart(steps, "/mnt/user-data/outputs/input_flow.drawio")
```

### Tree from Nested Dictionary
```python
from scripts.create_tree import create_tree

hierarchy = {
    "label": "Company",
    "children": [
        {
            "label": "Engineering",
            "children": [
                {"label": "Frontend"},
                {"label": "Backend"},
                {"label": "DevOps"}
            ]
        },
        {
            "label": "Product",
            "children": [
                {"label": "Design"},
                {"label": "Research"}
            ]
        }
    ]
}

create_tree(hierarchy, "/mnt/user-data/outputs/company_tree.drawio")
```

### Architecture from Data
```python
from scripts.from_data import create_from_data

data = {
    "nodes": [
        {"id": "lb", "label": "Load Balancer", "shape": "ellipse"},
        {"id": "web1", "label": "Web Server 1", "shape": "rectangle"},
        {"id": "web2", "label": "Web Server 2", "shape": "rectangle"},
        {"id": "db", "label": "Database", "shape": "cylinder"}
    ],
    "edges": [
        {"from": "lb", "to": "web1"},
        {"from": "lb", "to": "web2"},
        {"from": "web1", "to": "db"},
        {"from": "web2", "to": "db"}
    ]
}

create_from_data(data, "/mnt/user-data/outputs/infra.drawio", layout="horizontal")
```

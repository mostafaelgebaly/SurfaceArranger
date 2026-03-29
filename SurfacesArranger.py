# ═══════════════════════════════════════════════════════════════════════════════
# Dynamo Python Script — Grid Layout with Rotation + Frame + Label Points
# ───────────────────────────────────────────────────────────────────────────────
# IN[0] = surfaces     list of Surface / PolySurface geometry
# IN[1] = spacing      float  — gap between surfaces (also used as cell margin)
# IN[2] = columns      int    — number of columns in the grid
# IN[3] = label_band   float  — height of the label zone between double h-lines
# ───────────────────────────────────────────────────────────────────────────────
# OUT[0] = arranged + rotated surfaces
# OUT[1] = vertical lines
# OUT[2] = horizontal lines
# OUT[3] = label center points
# ═══════════════════════════════════════════════════════════════════════════════

import clr
import math
clr.AddReference('ProtoGeometry')
from Autodesk.DesignScript.Geometry import (
    BoundingBox, Vector, CoordinateSystem, Line, Point, Plane
)

# ── Helper: flatten nested lists ──────────────────────────────────────────────
def flatten(obj):
    if isinstance(obj, list):
        for item in obj:
            for sub in flatten(item):
                yield sub
    else:
        yield obj

# ── Helper: get all edges of a surface ────────────────────────────────────────
def get_edges(surface):
    try:
        return surface.Edges
    except:
        try:
            return surface.GetEdges()
        except:
            return []

# ── Helper: edge length ────────────────────────────────────────────────────────
def edge_length(edge):
    try:
        return edge.Length
    except:
        try:
            c = edge.CurveGeometry
            return c.Length
        except:
            return 0.0

# ── Helper: edge direction vector (start → end) ───────────────────────────────
def edge_vector(edge):
    try:
        c = edge.CurveGeometry
    except:
        c = edge
    sp = c.StartPoint
    ep = c.EndPoint
    dx = ep.X - sp.X
    dy = ep.Y - sp.Y
    length = math.sqrt(dx*dx + dy*dy)
    if length < 1e-9:
        return (1.0, 0.0)
    return (dx / length, dy / length)

# ── Helper: edge start point ───────────────────────────────────────────────────
def edge_start(edge):
    try:
        c = edge.CurveGeometry
    except:
        c = edge
    return c.StartPoint

# ── Rotate + orient surface so longest edge is on +X, surface in +XY plane ────
def orient_surface(surface):
    edges = get_edges(surface)
    if not edges:
        return surface

    # Find the longest edge
    longest = max(edges, key=lambda e: edge_length(e))
    ex, ey  = edge_vector(longest)

    # Angle from longest edge to +X axis
    angle_rad = math.atan2(ey, ex)       # angle of the edge in world XY
    angle_deg = math.degrees(angle_rad)

    # Rotate about the surface's bounding box center to align edge → +X
    bb     = BoundingBox.ByGeometry(surface)
    cx     = (bb.MinPoint.X + bb.MaxPoint.X) * 0.5
    cy     = (bb.MinPoint.Y + bb.MaxPoint.Y) * 0.5
    center = Point.ByCoordinates(cx, cy, 0.0)
    normal = Vector.ByCoordinates(0, 0, 1)

    rotated = surface.Rotate(center, normal, -angle_deg)

    # After rotation check: if the surface's centroid Y > start-point Y of
    # longest edge (i.e. surface is "above" the edge), it's resting correctly.
    # If not, rotate 180° to flip it so it always rests ON the longest edge.
    bb2  = BoundingBox.ByGeometry(rotated)
    cy2  = (bb2.MinPoint.Y + bb2.MaxPoint.Y) * 0.5

    # Re-find the longest edge start point after rotation to get its Y
    edges2   = get_edges(rotated)
    if edges2:
        longest2 = max(edges2, key=lambda e: edge_length(e))
        sp2      = edge_start(longest2)
        edge_y   = sp2.Y

        # If the body of the surface is below the edge, flip 180° around edge
        if cy2 < edge_y:
            cx2     = (bb2.MinPoint.X + bb2.MaxPoint.X) * 0.5
            cy2_val = (bb2.MinPoint.Y + bb2.MaxPoint.Y) * 0.5
            c2      = Point.ByCoordinates(cx2, cy2_val, 0.0)
            rotated = rotated.Rotate(c2, normal, 180.0)

    center.Dispose()
    normal.Dispose()
    return rotated

# ── Inputs ────────────────────────────────────────────────────────────────────
surfaces   = list(flatten(IN[0]))
spacing    = float(IN[1])
columns    = int(IN[2])
label_band = float(IN[3])

if not surfaces:
    OUT = [[], [], [], []]
    raise Exception("IN[0] is empty.")

# ── Step 1: Orient all surfaces (longest edge → +X, rest on that edge) ────────
oriented = [orient_surface(s) for s in surfaces]

# ── Step 2: Bounding boxes after rotation ─────────────────────────────────────
bboxes  = [BoundingBox.ByGeometry(s) for s in oriented]
widths  = [bb.MaxPoint.X - bb.MinPoint.X for bb in bboxes]
heights = [bb.MaxPoint.Y - bb.MinPoint.Y for bb in bboxes]

# ── Step 3: Grid dimensions ────────────────────────────────────────────────────
num_surfaces = len(oriented)
# Fix: actual number of rows needed — no empty trailing row
num_rows     = -(-num_surfaces // columns)

col_widths = []
for c in range(columns):
    idx_in_col = [r * columns + c for r in range(num_rows)
                  if (r * columns + c) < num_surfaces]
    col_widths.append(max(widths[i]  for i in idx_in_col) if idx_in_col else 0.0)

row_heights = []
for r in range(num_rows):
    idx_in_row = [r * columns + c for c in range(columns)
                  if (r * columns + c) < num_surfaces]
    row_heights.append(max(heights[i] for i in idx_in_row) if idx_in_row else 0.0)

# ── Step 4: Cumulative positions in logical space (Y downward) ────────────────
# Frame margin = spacing/2 on all sides — matches the half-gap between cells
# so the distance from any surface to the frame equals the distance between
# neighboring surfaces.
margin = spacing * 0.5

col_x = []
x_acc = margin
for w in col_widths:
    col_x.append(x_acc)
    x_acc += w + spacing

row_y_logical = []
y_acc = margin
for h in row_heights:
    row_y_logical.append(y_acc)
    y_acc += h + spacing + label_band

total_logical_height = y_acc - spacing - label_band + margin
#   last row consumed: h + spacing + label_band
#   we remove the trailing spacing+label_band, add back the bottom margin

# recalculate cleanly:
# bottom of last label band = row_y_logical[-1] + row_heights[-1] + spacing/2 + label_band
# bottom frame              = that + spacing/2  (= + margin)
last_row         = num_rows - 1
bottom_label_B   = (row_y_logical[last_row] + row_heights[last_row]
                    + margin + label_band)
total_logical_height = bottom_label_B + margin

frame_x0 = 0.0
frame_x1 = x_acc - spacing + margin      # right margin = margin (not full spacing)
z        = 0.0

# ── Flip: logical Y (down) → Revit Y (up) ─────────────────────────────────────
def flip(y):
    return total_logical_height - y

frame_y0 = 0.0                            # bottom of frame in Revit
frame_y1 = total_logical_height           # top of frame in Revit

# ── Step 5: Translate oriented surfaces into grid cells ───────────────────────
arranged = []
for idx, surface in enumerate(oriented):
    row = idx // columns
    col = idx %  columns

    mn = bboxes[idx].MinPoint

    target_x = col_x[col]
    # Bottom of this surface zone in Revit Y:
    target_y = flip(row_y_logical[row] + row_heights[row])

    dx = target_x - mn.X
    dy = target_y - mn.Y
    dz = -mn.Z

    vec       = Vector.ByCoordinates(dx, dy, dz)
    source_cs = CoordinateSystem.Identity()
    target_cs = source_cs.Translate(vec)
    moved     = surface.Transform(source_cs, target_cs)
    arranged.append(moved)

    vec.Dispose()
    target_cs.Dispose()

# ── Step 6: Vertical lines ────────────────────────────────────────────────────
v_lines = []

def make_v_line(x):
    p1 = Point.ByCoordinates(x, frame_y0, z)
    p2 = Point.ByCoordinates(x, frame_y1, z)
    ln = Line.ByStartPointEndPoint(p1, p2)
    p1.Dispose(); p2.Dispose()
    return ln

v_lines.append(make_v_line(frame_x0))
v_lines.append(make_v_line(frame_x1))

for c in range(columns - 1):
    x_sep = col_x[c] + col_widths[c] + spacing * 0.5
    v_lines.append(make_v_line(x_sep))

# ── Step 7: Horizontal lines ──────────────────────────────────────────────────
h_lines = []

def make_h_line(y):
    p1 = Point.ByCoordinates(frame_x0, y, z)
    p2 = Point.ByCoordinates(frame_x1, y, z)
    ln = Line.ByStartPointEndPoint(p1, p2)
    p1.Dispose(); p2.Dispose()
    return ln

h_lines.append(make_h_line(frame_y0))
h_lines.append(make_h_line(frame_y1))

label_center_y_per_row = []

for r in range(num_rows):
    logical_surf_bot = row_y_logical[r] + row_heights[r]
    logical_A        = logical_surf_bot + margin          # top divider (closer to surface)
    logical_B        = logical_A        + label_band      # bottom divider

    revit_A = flip(logical_A)
    revit_B = flip(logical_B)

    h_lines.append(make_h_line(revit_A))
    h_lines.append(make_h_line(revit_B))
    label_center_y_per_row.append((revit_A + revit_B) * 0.5)

# ── Step 8: Label center points ───────────────────────────────────────────────
label_points = []
for idx in range(num_surfaces):
    row = idx // columns
    col = idx %  columns
    pt  = Point.ByCoordinates(
              col_x[col] + col_widths[col] * 0.5,
              label_center_y_per_row[row],
              z)
    label_points.append(pt)

# ── Output ────────────────────────────────────────────────────────────────────
OUT = [arranged, v_lines, h_lines, label_points]

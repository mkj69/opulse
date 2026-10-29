"""Fast checks for the graph's browser-independent coordinate math."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_graph_scripts_parse():
    for name in ("opgraph.js", "scales-growth.js"):
        subprocess.run([NODE, "--check", str(ROOT / "docs/assets/js" / name)], check=True)


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_graph_transforms_and_hit_testing():
    script = r"""
const assert = require('node:assert/strict');
const g = require(process.argv[1]);
const v = {scale: 1.5, x: 21, y: -8};
const screen = g.worldToScreen(37, 49, v);
const world = g.screenToWorld(screen.x, screen.y, v);
assert.deepEqual(world, {x:37, y:49});
const zoomed = g.zoomAt(v, 3, screen.x, screen.y);
assert.deepEqual(g.screenToWorld(screen.x, screen.y, zoomed), world);
const nodes = [['+',-1,0,0],['◆',0,1,2]];
const point = g.worldToScreen(18+176+58,46+2*38+13.5,v);
assert.equal(g.hitTest(nodes,v,point.x,point.y),1);
assert.equal(g.hitTest(nodes,v,-200,-200),-1);
"""
    subprocess.run([NODE, "-e", script, str(ROOT / "docs/assets/js/opgraph.js")], check=True)

"""
CAD Engine Plugin — JARVIS designs 3D parts and assemblies autonomously.

Workflow:
  1. User describes a part in natural language.
  2. Plugin sends description to Ollama → Ollama writes CadQuery Python code.
  3. Plugin executes the code in a sandboxed namespace.
  4. Result is exported to STL / STEP / DXF and opened in the default viewer.

Also ships a library of parametric template shapes (box, cylinder, plate,
bracket, pipe, cone, hex) that work without any LLM call.

Requires:  pip install cadquery
Optional:  cadquery is already in requirements.txt after v2.1
"""

import logging
import os
import textwrap
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.cad")

CAD_OUTPUT_DIR = Path.home() / "NexusCAD"

# ── Prompt sent to Ollama when generating CadQuery code ──────────────────────
CADQUERY_CODEGEN_PROMPT = """You are a CadQuery CAD expert. Generate Python code that creates the described part.

STRICT RULES:
- Import: import cadquery as cq
- Store the final shape in a variable named exactly: result
- result must be a cq.Workplane object
- Output ONLY valid Python — no markdown, no triple backticks, no explanation, no comments
- Use millimetres unless the user specifies otherwise

COMMON PATTERNS:
Simple box:
import cadquery as cq
result = cq.Workplane("XY").box(100, 50, 20)

Plate with 4 corner holes:
import cadquery as cq
result = (
    cq.Workplane("XY")
    .box(100, 60, 5)
    .faces(">Z").workplane()
    .rect(80, 40, forConstruction=True)
    .vertices()
    .hole(5)
)

Cylinder with central bore:
import cadquery as cq
result = (
    cq.Workplane("XY")
    .cylinder(40, 20)
    .faces(">Z").workplane()
    .hole(8)
)

Hollow tube / pipe:
import cadquery as cq
result = (
    cq.Workplane("XY")
    .circle(15).circle(12)
    .extrude(80)
)

L-bracket:
import cadquery as cq
result = (
    cq.Workplane("XY")
    .hLine(60).vLine(5).hLine(-55).vLine(55).hLine(-5).close()
    .extrude(30)
)
"""

# Safe builtins for exec'd CadQuery code
_SAFE_BUILTINS = {
    "range": range, "len": len, "print": print,
    "list": list, "dict": dict, "tuple": tuple,
    "int": int, "float": float, "str": str,
    "bool": bool, "zip": zip, "enumerate": enumerate,
    "abs": abs, "min": min, "max": max, "round": round,
    "sum": sum, "map": map, "filter": filter,
    "__import__": __import__,   # needed so cadquery can import its own sub-modules
}


class CADPlugin(BasePlugin):
    name = "cad_engine"
    description = "AI-driven CAD — design any 3D part from a text description"
    icon = "⚙️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._cq = None
        self._parts: dict[str, dict] = {}   # name → metadata + code
        self._last_part: str | None = None
        self._ollama_host = config.get("ollama_host", "http://localhost:11434")
        self._model = config.get("model", "llama3.1:8b")
        CAD_OUTPUT_DIR.mkdir(exist_ok=True)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Import CadQuery in a thread with a timeout so startup never hangs."""
        import asyncio
        loop = asyncio.get_event_loop()

        def _try_import():
            import cadquery as cq  # noqa: F401 — heavy native import
            return cq

        try:
            cq = await asyncio.wait_for(
                loop.run_in_executor(None, _try_import),
                timeout=15.0,
            )
            self._cq = cq
            self._connected = True
            self._status_message = "CadQuery ready"
            logger.info("CAD Engine: CadQuery loaded successfully")
            return True
        except asyncio.TimeoutError:
            self._status_message = "CadQuery import timed out — check installation"
            logger.warning("CAD Engine: import timed out after 15s")
            return False
        except ImportError:
            self._status_message = "CadQuery not installed — run: pip install cadquery"
            logger.warning("CAD Engine: CadQuery not found")
            return False
        except Exception as e:
            self._status_message = f"Error: {str(e)[:60]}"
            logger.error(f"CAD Engine connect error: {e}")
            return False

    # ── Dispatch ─────────────────────────────────────────────────────────────

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "generate_part": self._generate_part,
            "create_shape":  self._create_shape,
            "run_code":      self._run_code,
            "export_stl":    self._export_stl,
            "export_step":   self._export_step,
            "export_dxf":    self._export_dxf,
            "list_parts":    self._list_parts,
            "open_part":     self._open_part,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown CAD action: '{action}'"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "generate_part",
                "description": "Generate a 3D CAD part from a natural language description using AI",
                "params": ["description", "name", "export"],
            },
            {
                "action": "create_shape",
                "description": "Create a parametric shape instantly: box, cylinder, sphere, plate, bracket, pipe, cone, hex",
                "params": ["shape", "name", "width", "height", "depth", "radius",
                           "thickness", "holes", "hole_diameter", "fillet",
                           "bore", "wall_thickness", "export"],
            },
            {
                "action": "run_code",
                "description": "Execute raw CadQuery Python code and export the result",
                "params": ["code", "name", "export"],
            },
            {
                "action": "export_stl",
                "description": "Export a named part to STL for 3D printing",
                "params": ["name"],
            },
            {
                "action": "export_step",
                "description": "Export a named part to STEP format for CAD interchange",
                "params": ["name"],
            },
            {
                "action": "export_dxf",
                "description": "Export the top face of a part to DXF for laser cutting / 2D machining",
                "params": ["name"],
            },
            {
                "action": "list_parts",
                "description": "List all generated CAD parts",
                "params": [],
            },
            {
                "action": "open_part",
                "description": "Open a generated part in the default 3D viewer",
                "params": ["name", "format"],
            },
        ]

    # ── AI-driven generation ─────────────────────────────────────────────────

    async def _generate_part(self, params: dict) -> str:
        description = params.get("description", "").strip()
        name = params.get("name") or f"part_{datetime.now().strftime('%H%M%S')}"
        raw_export = params.get("export", "stl")
        export_fmt = "stl" if not isinstance(raw_export, str) else raw_export.lower()

        if not description:
            return "❌ Please provide a description of the part, sir."
        if not self._cq:
            return "❌ CadQuery is not installed. Run: pip install cadquery"

        code = await self._codegen_via_ollama(description)
        if not code:
            return (
                "❌ Could not generate CAD code — Ollama may not be running.\n"
                "Try: 'create shape box' for a quick parametric shape, sir."
            )

        return await self._exec_and_export(code, name, description, export_fmt)

    async def _codegen_via_ollama(self, description: str) -> str | None:
        """Ask Ollama to write CadQuery code for the given description."""
        try:
            import ollama as ollama_lib

            client = ollama_lib.Client(host=self._ollama_host)
            response = client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": CADQUERY_CODEGEN_PROMPT},
                    {"role": "user",   "content": f"Design this part: {description}"},
                ],
                options={"temperature": 0.05},   # near-zero temp for deterministic code
                keep_alive="30m",
            )
            code = response["message"]["content"].strip()

            # Strip markdown fences if the model added them
            if "```" in code:
                lines = code.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                code = "\n".join(lines).strip()

            logger.debug(f"CAD codegen:\n{code}")
            return code

        except Exception as e:
            logger.error(f"CAD Ollama codegen error: {e}")
            return None

    # ── Raw code execution ───────────────────────────────────────────────────

    async def _run_code(self, params: dict) -> str:
        code = params.get("code", "").strip()
        name = params.get("name") or f"part_{datetime.now().strftime('%H%M%S')}"
        raw_export = params.get("export", "stl")
        export_fmt = "stl" if not isinstance(raw_export, str) else raw_export.lower()
        if not code:
            return "❌ No code provided."
        if not self._cq:
            return "❌ CadQuery is not installed. Run: pip install cadquery"
        return await self._exec_and_export(code, name, "Custom CadQuery code", export_fmt)

    # ── Core: execute code → export ──────────────────────────────────────────

    async def _exec_and_export(
        self, code: str, name: str, description: str, export_fmt: str
    ) -> str:
        import cadquery as cq

        namespace: dict = {
            "cadquery": cq,
            "cq": cq,
            "__builtins__": _SAFE_BUILTINS,
        }

        try:
            exec(textwrap.dedent(code), namespace)
        except Exception as e:
            return (
                f"❌ Code execution error: {e}\n\n"
                f"Generated code:\n```\n{code}\n```"
            )

        result = namespace.get("result")
        if result is None:
            return (
                f"❌ Code ran but produced no 'result' variable.\n\n"
                f"Code:\n```\n{code}\n```"
            )

        # Sanitise filename
        safe_name = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
        base_path = CAD_OUTPUT_DIR / safe_name

        exported: list[str] = []
        errors: list[str] = []

        def _export(res, path: Path, fmt: str):
            try:
                if fmt == "dxf":
                    # Export top face cross-section as DXF
                    cq.exporters.export(res.section(), str(path))
                else:
                    cq.exporters.export(res, str(path))
                exported.append(str(path))
            except Exception as exc:
                errors.append(f"{fmt.upper()}: {exc}")

        fmts = ["stl", "step", "dxf"] if export_fmt == "all" else [export_fmt]
        for fmt in fmts:
            ext_map = {"stl": ".stl", "step": ".step", "dxf": ".dxf"}
            ext = ext_map.get(fmt, f".{fmt}")
            _export(result, base_path.with_suffix(ext), fmt)

        # Persist metadata + code for later re-export / open
        self._parts[name] = {
            "description": description,
            "base_path":   str(base_path),
            "formats":     exported,
            "created":     datetime.now().strftime("%Y-%m-%d %H:%M"),
            "code":        code,
        }
        self._last_part = name

        file_list = "\n".join(f"  📄 {f}" for f in exported)
        err_note = ("\n⚠️  Some exports failed:\n" + "\n".join(f"  {e}" for e in errors)) if errors else ""

        return (
            f"✅ Part '{name}' designed and exported, sir.\n\n"
            f"📐 {description}\n"
            f"📁 Files:\n{file_list}{err_note}\n\n"
            f"💡 Say 'open {name}' to view it in your 3D viewer."
        )

    # ── Template shapes ──────────────────────────────────────────────────────

    async def _create_shape(self, params: dict) -> str:
        if not self._cq:
            return "❌ CadQuery is not installed. Run: pip install cadquery"

        shape = params.get("shape", "box").lower()
        name = params.get("name") or f"{shape}_{datetime.now().strftime('%H%M%S')}"
        raw_export = params.get("export", "stl")
        export_fmt = "stl" if not isinstance(raw_export, str) else raw_export.lower()

        builders = {
            "box":      self._tpl_box,
            "cylinder": self._tpl_cylinder,
            "sphere":   self._tpl_sphere,
            "plate":    self._tpl_plate,
            "bracket":  self._tpl_bracket,
            "pipe":     self._tpl_pipe,
            "cone":     self._tpl_cone,
            "hex":      self._tpl_hex,
        }

        builder = builders.get(shape)
        if not builder:
            shapes = ", ".join(builders.keys())
            return f"❌ Unknown shape '{shape}'. Available: {shapes}"

        code, desc = builder(params)
        return await self._exec_and_export(code, name, desc, export_fmt)

    # Templates return (code_str, description_str)

    def _tpl_box(self, p: dict) -> tuple[str, str]:
        w = float(p.get("width",  100))
        d = float(p.get("depth",   50))
        h = float(p.get("height",  20))
        f = float(p.get("fillet",   0))
        fillet = f".edges('|Z').fillet({f})" if f else ""
        return (
            f"import cadquery as cq\n"
            f"result = cq.Workplane('XY').box({w}, {d}, {h}){fillet}",
            f"Box {w}×{d}×{h}mm"
        )

    def _tpl_cylinder(self, p: dict) -> tuple[str, str]:
        r = float(p.get("radius", 25))
        h = float(p.get("height", 50))
        bore = float(p.get("bore", 0))
        bore_code = f"\n    .faces('>Z').workplane().hole({bore})" if bore else ""
        return (
            f"import cadquery as cq\n"
            f"result = (\n"
            f"    cq.Workplane('XY')\n"
            f"    .cylinder({h}, {r}){bore_code}\n"
            f")",
            f"Cylinder r={r}mm h={h}mm"
        )

    def _tpl_sphere(self, p: dict) -> tuple[str, str]:
        r = float(p.get("radius", 25))
        return (
            f"import cadquery as cq\n"
            f"result = cq.Workplane('XY').sphere({r})",
            f"Sphere r={r}mm"
        )

    def _tpl_plate(self, p: dict) -> tuple[str, str]:
        w      = float(p.get("width",          100))
        d      = float(p.get("depth",           60))
        t      = float(p.get("thickness",        5))
        holes  = int(  p.get("holes",            4))
        hole_d = float(p.get("hole_diameter",    5))
        margin = float(p.get("margin",          10))
        hole_code = ""
        if holes == 4:
            hole_code = (
                f"\n    .faces('>Z').workplane()\n"
                f"    .rect({w - margin*2}, {d - margin*2}, forConstruction=True)\n"
                f"    .vertices()\n"
                f"    .hole({hole_d})"
            )
        return (
            f"import cadquery as cq\n"
            f"result = (\n"
            f"    cq.Workplane('XY')\n"
            f"    .box({w}, {d}, {t}){hole_code}\n"
            f")",
            f"Plate {w}×{d}×{t}mm with {holes} corner holes (ø{hole_d}mm)"
        )

    def _tpl_bracket(self, p: dict) -> tuple[str, str]:
        w = float(p.get("width",     60))
        h = float(p.get("height",    60))
        t = float(p.get("thickness",  5))
        e = float(p.get("extrude",   30))   # depth / flange width
        return (
            f"import cadquery as cq\n"
            f"result = (\n"
            f"    cq.Workplane('XY')\n"
            f"    .hLine({w}).vLine({t}).hLine(-{w-t}).vLine({h-t}).hLine(-{t}).close()\n"
            f"    .extrude({e})\n"
            f")",
            f"L-bracket {w}×{h}mm t={t}mm depth={e}mm"
        )

    def _tpl_pipe(self, p: dict) -> tuple[str, str]:
        od   = float(p.get("outer_diameter",  30))
        wall = float(p.get("wall_thickness",   3))
        h    = float(p.get("height",         100))
        ir   = od / 2 - wall
        return (
            f"import cadquery as cq\n"
            f"result = (\n"
            f"    cq.Workplane('XY')\n"
            f"    .circle({od/2}).circle({ir})\n"
            f"    .extrude({h})\n"
            f")",
            f"Pipe OD={od}mm wall={wall}mm h={h}mm"
        )

    def _tpl_cone(self, p: dict) -> tuple[str, str]:
        r1 = float(p.get("base_radius", 30))
        r2 = float(p.get("top_radius",  10))
        h  = float(p.get("height",      50))
        return (
            f"import cadquery as cq\n"
            f"result = (\n"
            f"    cq.Workplane('XY').circle({r1})\n"
            f"    .workplane(offset={h}).circle({r2})\n"
            f"    .loft()\n"
            f")",
            f"Cone base_r={r1}mm top_r={r2}mm h={h}mm"
        )

    def _tpl_hex(self, p: dict) -> tuple[str, str]:
        size = float(p.get("size",   20))   # circumradius
        h    = float(p.get("height", 10))
        bore = float(p.get("bore",    0))
        bore_code = f"\n    .faces('>Z').workplane().hole({bore})" if bore else ""
        return (
            f"import cadquery as cq\n"
            f"result = (\n"
            f"    cq.Workplane('XY')\n"
            f"    .polygon(6, {size * 2})\n"
            f"    .extrude({h}){bore_code}\n"
            f")",
            f"Hex size={size}mm h={h}mm"
        )

    # ── Export helpers ───────────────────────────────────────────────────────

    async def _export_stl(self, params: dict) -> str:
        return await self._reexport(params, "stl")

    async def _export_step(self, params: dict) -> str:
        return await self._reexport(params, "step")

    async def _export_dxf(self, params: dict) -> str:
        return await self._reexport(params, "dxf")

    async def _reexport(self, params: dict, fmt: str) -> str:
        """Re-execute stored code and export to a new format."""
        import cadquery as cq

        name = params.get("name") or self._last_part
        if not name or name not in self._parts:
            return f"❌ No part named '{name}'. Say 'list parts' to see what's available."

        data = self._parts[name]
        namespace: dict = {"cq": cq, "cadquery": cq, "__builtins__": _SAFE_BUILTINS}
        try:
            exec(textwrap.dedent(data["code"]), namespace)
        except Exception as e:
            return f"❌ Error re-executing '{name}': {e}"

        result = namespace.get("result")
        if result is None:
            return "❌ Could not recover part geometry."

        out = Path(data["base_path"]).with_suffix(f".{fmt}")
        try:
            if fmt == "dxf":
                cq.exporters.export(result.section(), str(out))
            else:
                cq.exporters.export(result, str(out))
            if str(out) not in data["formats"]:
                data["formats"].append(str(out))
            return f"✅ Exported '{name}' → {fmt.upper()}\n  📄 {out}"
        except Exception as e:
            return f"❌ Export error: {e}"

    # ── List & Open ──────────────────────────────────────────────────────────

    async def _list_parts(self, params: dict) -> str:
        if not self._parts:
            return (
                "📐 No CAD parts generated yet, sir.\n\n"
                "Try:\n"
                "  • 'design a 100×50×10 mounting plate with 4 holes'\n"
                "  • 'create shape bracket'\n"
                "  • 'make a cylinder 30mm radius 50mm tall'"
            )
        lines = ["📐 Generated CAD Parts:\n"]
        for pname, data in self._parts.items():
            marker = "  ← last" if pname == self._last_part else ""
            lines.append(f"  ⚙️  {pname}{marker}")
            lines.append(f"      {data['description']}")
            lines.append(f"      Created: {data['created']}")
            for f in data.get("formats", []):
                lines.append(f"      📄 {f}")
            lines.append("")
        lines.append(f"📁 Output folder: {CAD_OUTPUT_DIR}")
        return "\n".join(lines)

    async def _open_part(self, params: dict) -> str:
        name = params.get("name") or self._last_part
        fmt  = params.get("format", "stl").lower()

        if not name or name not in self._parts:
            if self._last_part:
                name = self._last_part
            else:
                return "❌ No part to open. Generate a part first."

        data = self._parts[name]
        path = Path(data["base_path"]).with_suffix(f".{fmt}")

        if not path.exists():
            # Fall back to any existing format
            for ext in (".stl", ".step", ".dxf"):
                alt = Path(data["base_path"]).with_suffix(ext)
                if alt.exists():
                    path = alt
                    break
            else:
                return f"❌ No file found for '{name}'. Try exporting it first."

        try:
            os.startfile(str(path))
            return f"✅ Opening '{name}' ({path.suffix.upper()}) in your default viewer, sir."
        except Exception as e:
            return f"❌ Could not open file: {e}\n  Path: {path}"

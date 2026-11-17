"""
rulec.py  -  LAYER 4 library: typed rule schema  ->  rule DSL  ->  Lark AST  ->  SHACL shape.

Three deterministic stages after the (optional) model step:

  TypedRule (Pydantic)   the JSON schema a constrained-decoding LLM must emit  (step 1, model)
      |  to_dsl()
  Rule DSL (one line)    e.g.  OBLIGATION Policy attach_endorsement Endorsement:MM-CP-FL-01
                               WHEN Policy.inState = FL SOURCE MM-UW-CP-2025#SECTION-4/4.2
      |  parse()  (Lark LALR grammar -> typed AST; a parse failure means the rule is rejected)
  RuleAST (dict)
      |  compile_shape()  (rdflib)
  SHACL NodeShape        one shape per rule, stored under  https://example.org/pc/shape/<rule_id>

Design choice for the POC: unconditional rules compile to plain SHACL property shapes
(sh:hasValue / sh:not / sh:maxInclusive); conditional rules compile to sh:sparql constraints
(standard SHACL-SPARQL, supported by RDF4J ShaclSail in GraphDB with the documented
performance caveat). Both are standards-based; nothing GraphDB-specific is required.
"""
from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from lark import Lark, Transformer, v_args
from rdflib import Graph, Namespace, URIRef, Literal as RLiteral, BNode, RDF, RDFS, XSD
from rdflib.namespace import SH
from common import PC, PCD

PCN, PCDN = Namespace(PC), Namespace(PCD)
SHAPE = Namespace("https://example.org/pc/shape/")

# ------------------------------------------------------------------ 1. typed rule schema (constrained decoding contract)
Deontic = Literal["OBLIGATION", "PERMISSION", "PROHIBITION"]
Op = Literal["=", "!=", "IN", "NOT_IN", "<=", "<", ">", ">="]


class Condition(BaseModel):
    path: str = Field(description="Dotted path from the subject, e.g. Policy.inState or Claim.onPolicy.hasEndorsement. '^' marks an inverse step.")
    op: Op
    value: str | int | float | bool | List[str] = Field(description="An identifier (resolved to pcd:), literal, boolean or list; may also be another dotted path.")


class Deadline(BaseModel):
    value: int
    unit: Literal["hours", "days", "business_days"]


class TypedRule(BaseModel):
    rule_id: str
    deontic: Deontic
    subject: Literal["Policy", "Location", "Claim"] = Field(description="The operational record the rule is checked against (Layer 6).")
    action: str = Field(description="Canonical verb: attach_endorsement | schedule_location | report_loss | acknowledge_claim | pay_for_loss | bind | attach_form")
    object_type: Optional[str] = Field(default=None, description="Endorsement | Form | Peril | ClassCode | Coverage | None")
    object_ids: List[str] = Field(default_factory=list, description="e.g. ['MM-CP-E101'] or ['Flood','Water'] or ['ANY']")
    conditions: List[Condition] = Field(default_factory=list, description="WHEN - when does the rule apply")
    requirements: List[Condition] = Field(default_factory=list, description="REQUIRES - for permissions: what must hold to use the grant")
    exceptions: List[Condition] = Field(default_factory=list, description="UNLESS - carve-outs kept with the rule (each one exempts on its own)")
    deadline: Optional[Deadline] = None
    source_clause: str = Field(description="clause_id from Layer 1, e.g. MM-CP-0010#SECTION-E/E.3")
    message: str = Field(default="", description="Human message shown in the alert")


# ------------------------------------------------------------------ 2. DSL
def _fmt_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "(" + ", ".join(v) + ")"
    return str(v)


def to_dsl(r: TypedRule) -> str:
    parts = [r.deontic, r.subject, r.action]
    parts.append(f"{r.object_type}:{','.join(r.object_ids)}" if r.object_type else "NONE")
    for c in r.conditions:
        parts.append(f"WHEN {c.path} {c.op} {_fmt_value(c.value)}")
    for c in r.requirements:
        parts.append(f"REQUIRES {c.path} {c.op} {_fmt_value(c.value)}")
    for c in r.exceptions:
        parts.append(f"UNLESS {c.path} {c.op} {_fmt_value(c.value)}")
    if r.deadline:
        parts.append(f"WITHIN {r.deadline.value} {r.deadline.unit}")
    parts.append(f"SOURCE {r.source_clause}")
    return " ".join(parts)


GRAMMAR = r"""
start: deontic subject action object clause* source
deontic: "OBLIGATION" -> obligation | "PERMISSION" -> permission | "PROHIBITION" -> prohibition
subject: CLASS
action: NAME
object: "NONE" -> no_object | CLASS ":" idlist -> typed_object
idlist: ID ("," ID)*
clause: "WHEN" cond      -> when
      | "REQUIRES" cond  -> requires
      | "UNLESS" cond ("AND" cond)*  -> unless
      | "WITHIN" INT UNIT -> within
cond: PATH OP value
value: "(" ID ("," ID)* ")" -> list_value
     | PATH                 -> path_value
     | "true"               -> true_value
     | "false"              -> false_value
     | NUMBER               -> number_value
     | ID                   -> id_value
source: "SOURCE" SRC
PATH.2: /[A-Z][A-Za-z]+(\.\^?[A-Za-z][A-Za-z0-9]*)+/
CLASS: /[A-Z][A-Za-z]+/
NAME: /[a-z][a-z_]*/
ID: /[A-Z][A-Za-z0-9-]*[A-Za-z0-9]|[A-Z]/
UNIT: "hours" | "days" | "business_days"
OP: "!=" | "<=" | ">=" | "=" | "<" | ">" | "NOT_IN" | "IN"
SRC: /[A-Z][A-Z0-9-]+#[A-Za-z0-9.\-]+\/[A-Za-z0-9.\-\/]+/
NUMBER: /\d+(\.\d+)?/
INT: /\d+/
%import common.WS
%ignore WS
"""
_parser = Lark(GRAMMAR, parser="lalr")


@v_args(inline=True)
class _ToAST(Transformer):
    def obligation(self): return "OBLIGATION"
    def permission(self): return "PERMISSION"
    def prohibition(self): return "PROHIBITION"
    def subject(self, c): return str(c)
    def action(self, n): return str(n)
    def no_object(self): return None
    def idlist(self, *ids): return [str(i) for i in ids]
    def typed_object(self, cls, ids): return {"type": str(cls), "ids": ids}
    def list_value(self, *ids): return {"list": [str(i) for i in ids]}
    def path_value(self, p): return {"path": str(p).split(".")}
    def true_value(self): return {"bool": True}
    def false_value(self): return {"bool": False}
    def number_value(self, n): return {"number": float(n) if "." in str(n) else int(n)}
    def id_value(self, i): return {"id": str(i)}
    def cond(self, path, op, value): return {"path": str(path).split("."), "op": str(op), "value": value}
    def when(self, c): return ("when", c)
    def requires(self, c): return ("requires", c)
    def unless(self, *cs): return ("unless", list(cs))   # one UNLESS group = conjunction of conditions
    def within(self, n, unit): return ("within", {"value": int(n), "unit": str(unit)})
    def source(self, s): return str(s)

    def start(self, deontic, subject, action, obj, *rest):
        ast = {"deontic": deontic, "subject": subject, "action": action, "object": obj,
               "when": [], "requires": [], "unless": [], "within": None, "source": rest[-1]}
        for kind, payload in rest[:-1]:
            if kind == "within":
                ast["within"] = payload
            else:
                ast[kind].append(payload)
        return ast


def parse(dsl: str) -> dict:
    """Parse guarantee: either returns a typed AST or raises lark.exceptions.LarkError."""
    return _ToAST().transform(_parser.parse(dsl))


# ------------------------------------------------------------------ 3. AST -> SHACL
def _iri(v: str) -> str:
    return f"<{PCD}{v}>"


def _path_sparql(path, var):
    """['Claim','onPolicy','hasEndorsement'] -> '$this pc:onPolicy/pc:hasEndorsement ?var'"""
    steps = []
    for s in path[1:]:
        steps.append(("^pc:" + s[1:]) if s.startswith("^") else "pc:" + s)
    return f"$this {'/'.join(steps)} {var} ."


def _value_sparql(value, var_hint):
    """Return (extra_pattern, expression) for a value."""
    if "id" in value:
        return "", _iri(value["id"])
    if "number" in value:
        return "", str(value["number"])
    if "bool" in value:
        return "", "true" if value["bool"] else "false"
    if "list" in value:
        return "", "(" + ", ".join(_iri(i) for i in value["list"]) + ")"
    if "path" in value:  # path-vs-path comparison, e.g. TIV > authority max
        return _path_sparql(value["path"], var_hint), var_hint
    raise ValueError(value)


def _cond_sparql(c, idx):
    var = f"?c{idx}"
    pat = _path_sparql(c["path"], var)
    extra, expr = _value_sparql(c["value"], f"?v{idx}")
    op = c["op"]
    if op in ("IN", "NOT_IN"):
        filt = f"FILTER({var} {'IN' if op == 'IN' else 'NOT IN'} {expr})"
    else:
        filt = f"FILTER({var} {op} {expr})"
    return "\n    ".join(x for x in [pat, extra, filt] if x)


def _deadline_hours(within):
    v, u = within["value"], within["unit"]
    return v if u == "hours" else v * 24 if u == "days" else v * 24  # business days approximated for the POC


DEADLINE_PROPERTY = {"report_loss": ("noticeDelayHours", "hours"), "acknowledge_claim": ("acknowledgmentDelayDays", "days")}
OBJECT_PROPERTY = {"attach_endorsement": "hasEndorsement", "attach_form": "hasForm", "schedule_location": "scheduledUnder",
                   "pay_for_loss": "causeOfLoss", "bind": "hasClassCode"}


def compile_shape(rule_id: str, ast: dict, message: str = "", status: str = "active") -> Graph:
    g = Graph()
    g.bind("sh", SH); g.bind("pc", PCN); g.bind("pcd", PCDN); g.bind("shape", SHAPE)
    shape = SHAPE[rule_id]
    subj_cls = PCN[ast["subject"]]
    g.add((shape, RDF.type, SH.NodeShape))
    g.add((shape, SH.targetClass, subj_cls))
    # NOTE: sh:name / sh:description are property-shape characteristics; RDF4J ShaclSail (GraphDB) then types the
    # node shape as a PropertyShape too and rejects it ("Shape with multiple types"). Use rdfs:label / rdfs:comment.
    g.add((shape, RDFS.label, RLiteral(rule_id)))
    g.add((shape, RDFS.comment, RLiteral(f"{ast['deontic']} {ast['subject']} {ast['action']} | source {ast['source']} | status {status}")))
    g.add((shape, PCN.compiledFrom, URIRef(PCD + ast["source"].replace("#", "/").replace("/", "_"))))
    g.add((shape, PCN.ruleStatus, RLiteral(status)))
    msg = message or f"{rule_id}: {ast['deontic']} {ast['action']} violated (source {ast['source']})"

    simple = not ast["when"] and not ast["unless"] and not ast["requires"]
    obj = ast["object"]
    d = ast["deontic"]

    # ---- simple cases -> plain property shapes
    if simple and d == "OBLIGATION" and ast["within"] and ast["action"] in DEADLINE_PROPERTY:
        prop, unit = DEADLINE_PROPERTY[ast["action"]]
        limit = _deadline_hours(ast["within"]) if unit == "hours" else ast["within"]["value"]
        ps = BNode(); g.add((shape, SH.property, ps))
        g.add((ps, SH.path, PCN[prop])); g.add((ps, SH.maxInclusive, RLiteral(limit)))
        g.add((ps, SH.message, RLiteral(msg)))
        return g
    if simple and d == "OBLIGATION" and obj and ast["action"] in OBJECT_PROPERTY:
        ps = BNode(); g.add((shape, SH.property, ps))
        g.add((ps, SH.path, PCN[OBJECT_PROPERTY[ast["action"]]])); g.add((ps, SH.hasValue, PCDN[obj["ids"][0]]))
        g.add((ps, SH.message, RLiteral(msg)))
        return g
    if simple and d == "PROHIBITION" and obj and ast["action"] in OBJECT_PROPERTY and obj["ids"] != ["ANY"]:
        ps = BNode(); g.add((shape, SH.property, ps))
        g.add((ps, SH.path, PCN[OBJECT_PROPERTY[ast["action"]]]))
        if len(obj["ids"]) == 1:
            nb = BNode(); g.add((ps, SH["not"], nb)); g.add((nb, SH.hasValue, PCDN[obj["ids"][0]]))
        else:
            # none of the listed values may appear:  sh:not [ sh:in (...) ] is not legal on a value set,
            # so use a SPARQL constraint below instead
            simple = False
        if simple:
            g.add((ps, SH.message, RLiteral(msg)))
            return g

    # ---- general case -> SHACL-SPARQL constraint
    lines = [f"PREFIX pc: <{PC}>", f"PREFIX pcd: <{PCD}>", "SELECT $this ?value WHERE {"]
    for i, c in enumerate(ast["when"]):
        lines.append("    " + _cond_sparql(c, i))
    # the violation pattern
    if d == "PROHIBITION":
        if obj and obj["ids"] == ["ANY"] and ast["action"] == "attach_form":
            lines.append("    $this pc:hasForm ?value ; pc:inState ?st .")
        elif obj and ast["action"] in OBJECT_PROPERTY:
            lines.append(f"    $this pc:{OBJECT_PROPERTY[ast['action']]} ?value .")
            lines.append(f"    FILTER(?value IN ({', '.join(_iri(i) for i in obj['ids'])}))")
        else:
            lines.append("    BIND($this AS ?value)")
    elif d == "OBLIGATION":
        if ast["within"] and ast["action"] in DEADLINE_PROPERTY:
            prop, unit = DEADLINE_PROPERTY[ast["action"]]
            limit = _deadline_hours(ast["within"]) if unit == "hours" else ast["within"]["value"]
            lines.append(f"    $this pc:{prop} ?value . FILTER(?value > {limit})")
        elif obj and ast["action"] in OBJECT_PROPERTY:
            lines.append(f"    BIND({_iri(obj['ids'][0])} AS ?value)")
            lines.append(f"    FILTER NOT EXISTS {{ $this pc:{OBJECT_PROPERTY[ast['action']]} ?value }}")
        else:
            lines.append("    BIND($this AS ?value)")
    else:  # PERMISSION: a record that USES the grant must satisfy the grant's requirements
        lines.append("    BIND($this AS ?value)")
        reqs = [f"{{ {_cond_sparql(c, 100 + i)} }}" for i, c in enumerate(ast["requires"])]
        if reqs:
            lines.append("    FILTER NOT EXISTS { " + " ".join(reqs) + " }")
    for i, grp in enumerate(ast["unless"]):      # each UNLESS group: all of its conditions must hold to exempt
        inner = "\n      ".join(_cond_sparql(c, 200 + i * 10 + j) for j, c in enumerate(grp))
        lines.append("    FILTER NOT EXISTS {\n      " + inner + "\n    }")
    if d == "PROHIBITION" and obj and obj["ids"] == ["ANY"] and ast["action"] == "attach_form":
        lines.append("    FILTER NOT EXISTS { ?ap a pc:FormApproval ; pc:approvalOfForm ?value ; pc:approvalInState ?st ; pc:approvalStatus pcd:Approved }")
    lines.append("}")
    sp = BNode(); g.add((shape, SH.sparql, sp))
    g.add((sp, SH.message, RLiteral(msg)))
    g.add((sp, SH.select, RLiteral("\n".join(lines))))
    return g

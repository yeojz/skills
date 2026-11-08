// Explicit-state model checker and Mermaid statechart writer for small models.
// Pure TypeScript with node: built-ins only, so it runs on Node 22.18+, Bun or
// Deno without Java, TLC or a package install.
//
//   statechart MODEL.ts [--out DIR] [--max-states N] [--budget N]
//
// The model module exports init, actions and rules; see SKILL.md.

import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { inspect } from "node:util";

type S = Record<string, unknown>;
type Label = string | string[] | Record<string, string>;

type Model = {
  title?: string;
  init: S | S[] | (() => S | S[]);
  actions: Record<string, (s: S) => S | S[] | null | undefined | false>;
  invariants?: Record<string, (s: S) => boolean>;
  canReach?: Record<string, (s: S) => boolean>;
  final?: (s: S) => boolean;
  constraint?: (s: S) => boolean;
  state?: (s: S) => Label;
  step?: (action: string, from: S, to: S) => string | null;
  group?: (s: S) => string | null | undefined;
  colors?: Record<string, string>;
};

type Edge = { from: number; to: number; action: string };
type Node = { s: S; key: string; parent: number; via: string; depth: number; expanded: boolean };
type Bug = { rule: string; kind: "invariant" | "deadlock" | "canReach"; state: number };

const DEADLOCK = "No dead end: every state that is not an end state has a step out";

// ---------- arguments ----------

const argv = process.argv.slice(2);
const flag = (name: string, fallback: string) => {
  const i = argv.indexOf(name);
  if (i < 0) return fallback;
  const v = argv[i + 1];
  argv.splice(i, 2);
  if (v === undefined) fail(`${name} needs a value`);
  return v;
};
const outDir = path.resolve(flag("--out", "statechart-out"));
const count = (name: string, fallback: string) => {
  const v = flag(name, fallback);
  if (!/^[1-9]\d*$/.test(v)) fail(`${name} needs a positive whole number, got "${v}"`);
  return Number(v);
};
const maxStates = count("--max-states", "100000");
const budget = count("--budget", "500");
if (argv.length !== 1 || argv[0].startsWith("-")) {
  fail("usage: statechart MODEL.ts [--out DIR] [--max-states N] [--budget N]");
}
const modelFile = path.resolve(argv[0]);

function fail(message: string): never {
  process.stderr.write(`statechart: ${message}\n`);
  process.exit(2);
}

// Any error not caught below is a checker failure, never "a rule breaks".
process.on("uncaughtException", (e) => fail(`unexpected error: ${e instanceof Error ? (e.stack ?? e.message) : String(e)}`));
process.on("unhandledRejection", (e) => fail(`unexpected error: ${e instanceof Error ? (e.stack ?? e.message) : String(e)}`));

// ---------- values ----------

// Canonical key: object keys sorted, so two equal states always share a key.
// Only plain data is allowed; anything else (a Date, NaN, a bigint, a class
// instance) would make distinct states share a key and hide a broken rule.
function canon(v: unknown): string {
  if (v === null) return "null";
  if (v === undefined) return "undefined";
  if (typeof v === "string" || typeof v === "boolean") return JSON.stringify(v);
  if (typeof v === "number") {
    if (!Number.isFinite(v)) throw new Error(`${v} is not a finite number`);
    return JSON.stringify(v);
  }
  if (typeof v !== "object") throw new Error(`a ${typeof v} cannot be part of a state`);
  if (Array.isArray(v)) return `[${v.map(canon).join(",")}]`;
  if (v instanceof Set) return `Set${canon([...v].map(canon).sort())}`;
  if (v instanceof Map) return `Map${canon([...v].map(([k, x]) => `${canon(k)}=>${canon(x)}`).sort())}`;
  const proto = Object.getPrototypeOf(v);
  if (proto !== Object.prototype && proto !== null) {
    throw new Error(`a ${proto?.constructor?.name ?? "class"} object cannot be part of a state; use plain objects, arrays, Sets and Maps`);
  }
  const o = v as Record<string, unknown>;
  return `{${Object.keys(o)
    .filter((k) => o[k] !== undefined)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${canon(o[k])}`)
    .join(",")}}`;
}

// Runs a model hook; a throw stops the run with exit 2 and the state it threw on.
function guard<T>(what: string, s: unknown, run: () => T): T {
  try {
    return run();
  } catch (e) {
    let state: string;
    try {
      state = canon(s);
    } catch {
      state = inspect(s, { depth: 4, breakLength: Infinity });
    }
    fail(`${what} threw on ${state}: ${(e as Error).message}`);
  }
}

// Deep copy of plain data. structuredClone cannot copy the watching proxies below.
function copy<T>(v: T): T {
  if (v === null || typeof v !== "object") return v;
  if (Array.isArray(v)) return v.map(copy) as T;
  if (v instanceof Set) return new Set([...v].map(copy)) as T;
  if (v instanceof Map) return new Map([...v].map(([k, x]) => [copy(k), copy(x)])) as T;
  return Object.fromEntries(Object.entries(v as object).map(([k, x]) => [k, copy(x)])) as T;
}

// Field paths that exist in some reachable state, and reads of paths that do
// not. Node strips types without checking them, so a misspelt field in a rule
// would otherwise read undefined and quietly hold.
const known = new Set<string>();
const misses = new Map<string, Set<string>>();
const IGNORED_READS = new Set(["toJSON", "then"]);

function collect(v: unknown, at: string) {
  if (v === null || typeof v !== "object") return;
  if (Array.isArray(v) || v instanceof Set) {
    for (const x of v) collect(x, `${at}[]`);
    return;
  }
  if (v instanceof Map) {
    for (const x of v.values()) collect(x, `${at}[]`);
    return;
  }
  for (const [k, x] of Object.entries(v)) {
    if (x === undefined) continue;
    const path = at ? `${at}.${k}` : k;
    known.add(path);
    collect(x, path);
  }
}

function watch<T>(v: T, hook: string, at = ""): T {
  if (v === null || typeof v !== "object") return v;
  if (Array.isArray(v)) {
    return new Proxy(v, {
      get: (t, p, r) => {
        const x = Reflect.get(t, p, r);
        return typeof p === "string" && /^\d+$/.test(p) ? watch(x, hook, `${at}[]`) : x;
      },
    });
  }
  if (Object.getPrototypeOf(v) !== Object.prototype) return v;
  return new Proxy(v as object, {
    get: (t, p, r) => {
      if (typeof p !== "string" || IGNORED_READS.has(p)) return Reflect.get(t, p, r);
      const path = at ? `${at}.${p}` : p;
      if (!(p in t)) misses.set(path, (misses.get(path) ?? new Set()).add(hook));
      return watch(Reflect.get(t, p, r), hook, path);
    },
  }) as T;
}

// A fresh, watched copy for each hook call.
const view = (s: S, hook: string) => watch(copy(s), hook);

const show = (s: S) => canon(s);
const asList = <T>(x: T | T[] | null | undefined | false): T[] =>
  x === null || x === undefined || x === false ? [] : Array.isArray(x) ? x : [x];

// ---------- check ----------

async function load(): Promise<Model> {
  let m: Partial<Model> & { default?: Model };
  try {
    m = await import(pathToFileURL(modelFile).href);
  } catch (e) {
    fail(`cannot load ${modelFile}: ${(e as Error).message}`);
  }
  const model = (m.default ?? m) as Model;
  if (model.init === undefined) fail(`${modelFile} exports no init`);
  if (!model.actions || !Object.keys(model.actions).length) fail(`${modelFile} exports no actions`);
  const names = [...Object.keys(model.invariants ?? {}), DEADLOCK, ...Object.keys(model.canReach ?? {})];
  const dup = names.find((n, i) => names.indexOf(n) !== i);
  if (dup) fail(`two rules share the name "${dup}"; give each rule its own sentence`);
  return model;
}

function explore(model: Model) {
  const nodes: Node[] = [];
  const index = new Map<string, number>();
  const edges: Edge[] = [];
  const fired = new Map<string, number>();
  const bugs = new Map<string, Bug>();
  const breaks = new Map<number, string[]>();
  const invariants = Object.entries(model.invariants ?? {});
  let complete = true;
  let bounded = 0;

  const add = (s: S, parent: number, via: string, depth: number) => {
    const from = via ? `the state from action "${via}"` : "init";
    if (s === null || typeof s !== "object" || Array.isArray(s)) {
      const hint = via ? "" : " An array init lists the start states, so each item must be an object.";
      fail(`${from} gave ${inspect(s)}, which is not an object. A state must be a plain object; wrap a tuple as { pair: [a, b] }.${hint}`);
    }
    const key = guard(from, s, () => canon(s));
    const seen = index.get(key);
    if (seen !== undefined) return seen;
    const id = nodes.length;
    const stored = copy(s);
    nodes.push({ s: stored, key, parent, via, depth, expanded: false });
    index.set(key, id);
    collect(stored, "");
    for (const [rule, holds] of invariants) {
      if (!guard(`invariant "${rule}"`, stored, () => holds(view(stored, `invariant "${rule}"`)))) {
        if (!bugs.has(rule)) bugs.set(rule, { rule, kind: "invariant", state: id });
        breaks.set(id, [...(breaks.get(id) ?? []), rule]);
      }
    }
    return id;
  };

  const init = guard("init", undefined, () => (typeof model.init === "function" ? model.init() : model.init));
  for (const s of asList(init)) add(s, -1, "", 0);
  const starts = nodes.map((_, i) => i);

  for (let i = 0; i < nodes.length; i++) {
    if (nodes.length > maxStates) {
      complete = false;
      break;
    }
    const n = nodes[i];
    const constraint = model.constraint;
    if (constraint && !guard("constraint", n.s, () => constraint(view(n.s, "constraint")))) {
      bounded++;
      continue;
    }
    n.expanded = true;
    let out = 0;
    for (const [action, run] of Object.entries(model.actions)) {
      const next = guard(`action "${action}"`, n.s, () => asList(run(view(n.s, `action "${action}"`))));
      for (const t of next) {
        fired.set(action, (fired.get(action) ?? 0) + 1);
        const to = add(t, i, action, n.depth + 1);
        // A step back to the same state is stuttering, not a way out.
        if (to !== i) out++;
        edges.push({ from: i, to, action });
      }
    }
    if (!out && !guard("final", n.s, () => model.final?.(view(n.s, "final")) ?? false)) {
      if (!bugs.has(DEADLOCK)) bugs.set(DEADLOCK, { rule: DEADLOCK, kind: "deadlock", state: i });
      breaks.set(i, [...(breaks.get(i) ?? []), DEADLOCK]);
    }
  }

  // canReach: from every reachable state some goal state can still be reached.
  // A state past the constraint is unknown, not fine: what lies beyond it was
  // never searched. A state that misses the goal but can reach an unknown one
  // leaves the rule not checked; one that can reach neither breaks it.
  const unchecked = new Map<string, string>();
  const back = new Map<number, number[]>();
  for (const e of edges) {
    const list = back.get(e.to);
    if (list) list.push(e.from);
    else back.set(e.to, [e.from]);
  }
  const spread = (seeds: number[], into: Set<number>, skip: Set<number>) => {
    const queue = [...seeds];
    for (const i of seeds) into.add(i);
    while (queue.length) {
      for (const p of back.get(queue.pop() as number) ?? []) {
        if (!into.has(p) && !skip.has(p)) {
          into.add(p);
          queue.push(p);
        }
      }
    }
  };
  for (const [rule, goal] of Object.entries(model.canReach ?? {})) {
    if (!complete) {
      unchecked.set(rule, `the search stopped at --max-states ${maxStates}`);
      continue;
    }
    const ok = new Set<number>();
    const goals = nodes.flatMap((n, i) => (guard(`canReach "${rule}"`, n.s, () => goal(view(n.s, `canReach "${rule}"`))) ? [i] : []));
    spread(goals, ok, new Set());
    const unknown = new Set<number>();
    spread(
      nodes.flatMap((n, i) => (!n.expanded && !ok.has(i) ? [i] : [])),
      unknown,
      ok,
    );
    nodes.forEach((_, i) => {
      if (ok.has(i) || unknown.has(i)) return;
      if (!bugs.has(rule)) bugs.set(rule, { rule, kind: "canReach", state: i });
      breaks.set(i, [...(breaks.get(i) ?? []), rule]);
    });
    const blind = [...unknown].filter((i) => !ok.has(i)).length;
    if (blind && !bugs.has(rule)) {
      unchecked.set(rule, `${blind} states reach the goal, if at all, only through states past \`constraint\`, which were not searched`);
    }
  }

  return { nodes, edges, starts, fired, bugs, breaks, complete, unchecked, bounded };
}

type Result = ReturnType<typeof explore>;

function pathTo(r: Result, id: number) {
  const steps: { action: string; node: number }[] = [];
  for (let i = id; i >= 0; i = r.nodes[i].parent) steps.unshift({ action: r.nodes[i].via, node: i });
  return steps;
}

// ---------- labels ----------

function labeller(model: Model, r: Result) {
  const stateOf = model.state;
  const shape = (x: unknown) => {
    const word = (w: unknown) => typeof w === "string" && w.trim() !== "";
    if (word(x)) return "flat";
    if (Array.isArray(x) && x.length && x.every(word)) return "parents";
    if (x !== null && typeof x === "object" && !Array.isArray(x) && Object.keys(x).length && Object.values(x).every(word)) {
      return "regions";
    }
    return null;
  };
  const labels = r.nodes.map((n) => (stateOf ? guard("state", n.s, () => stateOf(view(n.s, "state"))) : show(n.s)));
  const kinds = new Set<string>();
  labels.forEach((x, i) => {
    const k = shape(x);
    if (!k) {
      fail(`state() returned ${inspect(x)} for ${show(r.nodes[i].s)}; return a non-empty string, an array of them, or an object of them`);
    }
    kinds.add(k);
  });
  if (kinds.size > 1) fail(`state() mixes ${[...kinds].join(" and ")} labels; return one shape for every state`);
  const kind = [...kinds][0] ?? "flat";
  const stepLabel = new Map<Edge, string | null>();
  for (const e of r.edges) {
    const from = r.nodes[e.from].s;
    const to = r.nodes[e.to].s;
    const stepOf = model.step;
    const hook = `step for "${e.action}"`;
    stepLabel.set(e, stepOf ? guard(hook, from, () => stepOf(e.action, view(from, hook), view(to, hook))) : e.action);
  }
  const groups = r.nodes.map((n) => guard("group", n.s, () => model.group?.(view(n.s, "group")) ?? null));
  return { labels, kind, stepLabel, groups };
}

// ---------- mermaid ----------

// One pass, so an inserted entity is never escaped again.
const ENTITY: Record<string, string> = { "#": "#35;", '"': "#quot;", ";": "#59;", "\n": " " };
const esc = (t: string) => t.replace(/[#";\n]/g, (c) => ENTITY[c]);

function mermaid(model: Model, r: Result, l: ReturnType<typeof labeller>, keep: Set<number>, keepEdges: Set<Edge>) {
  const lines = ["stateDiagram-v2"];
  // JSON strings are valid YAML, so a colon or # in the title cannot break the frontmatter.
  if (model.title) lines.unshift("---", `title: ${JSON.stringify(model.title.replace(/\n/g, " "))}`, "---");
  const ids = new Map<string, string>();
  const id = (k: string) => {
    if (!ids.has(k)) ids.set(k, `s${ids.size}`);
    return ids.get(k) as string;
  };
  const warnings: string[] = [];
  const classes = new Map<string, Set<string>>();
  const groupClass = new Map(Object.keys(model.colors ?? {}).map((g, i) => [g, `g${i}`]));
  const mark = (nodeIds: string, members: number[]) => {
    const broken = members.map((m) => r.breaks.has(m));
    const cls = broken.every(Boolean) ? "breaks" : broken.some(Boolean) ? "mayBreak" : null;
    const g = new Set(members.map((m) => l.groups[m]));
    const group = g.size === 1 ? [...g][0] : null;
    const c = cls ?? (group ? (groupClass.get(group) ?? null) : null);
    if (c) classes.set(c, (classes.get(c) ?? new Set()).add(nodeIds));
  };
  const drawn = [...keepEdges].filter((e) => l.stepLabel.get(e) !== null);
  let arrows = 0;

  // Region projection: one chart per key, an arrow per region whose label changes.
  if (l.kind === "regions") {
    const regions = [...new Set(l.labels.flatMap((x) => Object.keys(x as object)))];
    const at = (n: number, k: string) => String((l.labels[n] as Record<string, string>)[k] ?? "-");
    lines.push(`state "${esc(model.title ?? "System")}" as root {`);
    regions.forEach((k, ri) => {
      if (ri) lines.push("  --");
      const rid = `r${ri}`;
      lines.push(`  state "${esc(k)}" as ${rid} {`);
      const members = new Map<string, number[]>();
      for (const n of keep) members.set(at(n, k), [...(members.get(at(n, k)) ?? []), n]);
      for (const [v, ms] of members) {
        lines.push(`    state "${esc(v)}" as ${id(`${k}\u0000${v}`)}`);
        mark(id(`${k}\u0000${v}`), ms);
      }
      for (const v of new Set([...r.starts].filter((n) => keep.has(n)).map((n) => at(n, k)))) {
        lines.push(`    [*] --> ${id(`${k}\u0000${v}`)}`);
      }
      const arrowsHere = new Map<string, { a: string; b: string; text: string; others: Map<string, Set<string>> }>();
      for (const e of drawn) {
        const a = at(e.from, k);
        const b = at(e.to, k);
        if (a === b) continue;
        const text = l.stepLabel.get(e) as string;
        const key = `${a}\u0000${b}\u0000${text}`;
        const entry = arrowsHere.get(key) ?? { a, b, text, others: new Map() };
        for (const o of regions) if (o !== k) entry.others.set(o, (entry.others.get(o) ?? new Set()).add(at(e.from, o)));
        arrowsHere.set(key, entry);
      }
      for (const { a, b, text, others } of arrowsHere.values()) {
        let cond = "";
        if (!text.trim().endsWith("]")) {
          const parts: string[] = [];
          for (const [o, seen] of others) {
            const possible = new Set([...keep].filter((n) => at(n, k) === a).map((n) => at(n, o)));
            if (seen.size < possible.size) parts.push([...seen].join(" or "));
          }
          if (parts.length) cond = ` [when ${parts.join(", ")}]`;
        }
        lines.push(`    ${id(`${k}\u0000${a}`)} --> ${id(`${k}\u0000${b}`)} : ${esc(text + cond)}`);
        arrows++;
      }
      lines.push("  }");
    });
    lines.push("}");
  } else {
    const leaf = (n: number) => {
      const x = l.labels[n];
      return Array.isArray(x) ? x.map(String) : [String(x)];
    };
    const full = (n: number) => leaf(n).join("\u0000");
    const members = new Map<string, number[]>();
    for (const n of keep) members.set(full(n), [...(members.get(full(n)) ?? []), n]);
    // Build the parent tree from the label paths.
    type Tree = { kids: Map<string, Tree>; key: string };
    const root: Tree = { kids: new Map(), key: "" };
    for (const k of members.keys()) {
      let t = root;
      const parts = k.split("\u0000");
      parts.forEach((p, i) => {
        const key = parts.slice(0, i + 1).join("\u0000");
        if (!t.kids.has(p)) t.kids.set(p, { kids: new Map(), key });
        t = t.kids.get(p) as Tree;
      });
    }
    const emit = (t: Tree, depth: number) => {
      for (const [name, kid] of t.kids) {
        const pad = "  ".repeat(depth);
        lines.push(`${pad}state "${esc(name)}" as ${id(kid.key)}`);
        if (kid.kids.size) {
          if (members.has(kid.key)) warnings.push(`"${name}" is both a state and a parent; give it a child label`);
          lines.push(`${pad}state ${id(kid.key)} {`);
          emit(kid, depth + 1);
          lines.push(`${pad}}`);
        }
      }
    };
    emit(root, 0);
    for (const [k, ms] of members) mark(id(k), ms);
    for (const k of new Set(r.starts.filter((n) => keep.has(n)).map(full))) lines.push(`[*] --> ${id(k)}`);
    const seen = new Set<string>();
    for (const e of drawn) {
      const a = full(e.from);
      const b = full(e.to);
      if (a === b) continue;
      const line = `${id(a)} --> ${id(b)} : ${esc(l.stepLabel.get(e) as string)}`;
      if (seen.has(line)) continue;
      seen.add(line);
      lines.push(line);
      arrows++;
    }
    const ends = new Set<string>();
    for (const n of keep) if (guard("final", r.nodes[n].s, () => model.final?.(view(r.nodes[n].s, "final")))) ends.add(full(n));
    for (const k of ends) lines.push(`${id(k)} --> [*]`);

    // Hidden-step checks: each chart state reachable, and one arrow out where the model has a step out.
    const out = new Map<string, Set<string>>();
    for (const e of drawn) if (full(e.from) !== full(e.to)) out.set(full(e.from), (out.get(full(e.from)) ?? new Set()).add(full(e.to)));
    const reach = new Set(r.starts.filter((n) => keep.has(n)).map(full));
    const queue = [...reach];
    while (queue.length) for (const b of out.get(queue.pop() as string) ?? []) if (!reach.has(b)) reach.add(b), queue.push(b);
    const name = (k: string) => k.split("\u0000").join(" / ");
    for (const k of members.keys()) if (!reach.has(k)) warnings.push(`"${name(k)}" has no arrows leading to it from a start state`);
    const modelOut = new Set(
      [...keepEdges].filter((e) => full(e.from) !== full(e.to)).map((e) => full(e.from)),
    );
    for (const k of modelOut) if (!out.has(k)) warnings.push(`"${name(k)}" has steps out in the model but no arrow out in the chart`);
  }

  const style: Record<string, string> = {
    breaks: "fill:#f8d7da,stroke:#b02a37,stroke-width:2px,color:#000",
    mayBreak: "fill:#fff3cd,stroke:#b02a37,stroke-width:2px,stroke-dasharray:4 3,color:#000",
  };
  for (const [g, css] of Object.entries(model.colors ?? {})) style[groupClass.get(g) as string] = css;
  for (const [c, members] of classes) {
    lines.push(`classDef ${c} ${style[c]}`);
    lines.push(`class ${[...members].join(",")} ${c}`);
  }
  // A bug path step that stays inside one chart state is invisible to the reader.
  const same = (a: number, b: number) => canon(l.labels[a]) === canon(l.labels[b]);
  [...r.bugs.values()].forEach((bug) => {
    for (const p of pathTo(r, bug.state).slice(1)) {
      if (same(r.nodes[p.node].parent, p.node)) {
        warnings.push(`the path for "${bug.rule}" takes ${p.action} without leaving its chart state; split that label so the reader sees the step`);
      }
      const e = r.edges.find((x) => x.to === p.node && x.from === r.nodes[p.node].parent && x.action === p.action);
      if (e && l.stepLabel.get(e) === null) {
        warnings.push(`the path for "${bug.rule}" takes ${p.action}, which step() hides; keep bug path steps visible`);
      }
    }
  });
  if (arrows > 20) warnings.push(`${arrows} arrows; aim for about 20 by merging labels or hiding steps`);
  return { text: `${lines.join("\n")}\n`, arrows, warnings };
}

// ---------- report ----------

function report(
  model: Model,
  r: Result,
  l: ReturnType<typeof labeller>,
  chart: { arrows: number; warnings: string[] } | null,
  cut: { states: number } | null,
  suspect: string[],
) {
  const out: string[] = [`# ${model.title ?? "Statechart"}`, ""];
  out.push(
    `Distinct states: ${r.nodes.length}${r.complete ? "" : ` (stopped at --max-states ${maxStates}; the search is incomplete)`}. Steps: ${r.edges.length}.`,
  );
  if (r.bounded) {
    out.push(
      `${r.bounded} states fail \`constraint\` and were not explored: dead ends and canReach are not checked in them, and nothing past them is searched.`,
    );
  }
  if (cut) out.push(`${cut.states} chart states, over the --budget of ${budget}: the chart draws only the bug paths.`);
  if (!chart) out.push("No chart: over the budget and no rule breaks.");
  if (suspect.length) {
    out.push("", "## Model warnings", "", "The model itself looks wrong, so no result below can be trusted until these are fixed.", "");
    out.push(...suspect.map((w) => `- ${w}`));
  }
  out.push("", "## Rules", "");
  const rules = [...Object.keys(model.invariants ?? {}), DEADLOCK, ...Object.keys(model.canReach ?? {})];
  const sorted = [...r.bugs.values()].sort((a, b) => r.nodes[a.state].depth - r.nodes[b.state].depth);
  for (const rule of rules) {
    if (r.unchecked.has(rule)) out.push(`- NOT CHECKED (${r.unchecked.get(rule)}): ${rule}`);
    else if (r.bugs.has(rule)) out.push(`- BREAKS (path ${sorted.findIndex((b) => b.rule === rule) + 1}): ${rule}`);
    else out.push(`- ${r.complete ? "holds" : "holds in the states searched"}: ${rule}`);
  }
  const labelText = (n: number) => {
    const x = l.labels[n];
    return Array.isArray(x) ? x.join(" / ") : typeof x === "object" ? Object.entries(x).map(([k, v]) => `${k}: ${v}`).join(", ") : String(x);
  };
  sorted.forEach((bug, i) => {
    out.push("", `## Path ${i + 1}: ${bug.rule}`, "");
    if (bug.kind === "canReach") out.push("From the last state, no goal state can be reached any more.", "");
    if (bug.kind === "deadlock") out.push("The last state has no step out and `final` does not cover it.", "");
    pathTo(r, bug.state).forEach((p, j) => {
      const edge = r.edges.find((e) => e.to === p.node && e.from === r.nodes[p.node].parent && e.action === p.action);
      const how = j === 0 ? "start" : `${edge ? (l.stepLabel.get(edge) ?? `(hidden) ${p.action}`) : p.action} [action ${p.action}]`;
      out.push(`${j + 1}. ${how} -> **${labelText(p.node)}**`);
      out.push(`   \`${show(r.nodes[p.node].s)}\``);
    });
  });
  const hidden = [...new Set(r.edges.filter((e) => l.stepLabel.get(e) === null).map((e) => e.action))];
  if (hidden.length) out.push("", "## Steps hidden from the chart", "", ...hidden.map((a) => `- ${a}`));
  if (chart?.warnings.length) out.push("", "## Chart warnings", "", ...chart.warnings.map((w) => `- ${w}`));
  if (r.bugs.size) {
    out.push("", "## Legend", "", "- `breaks`: every model state behind this chart state breaks a rule.");
    out.push("- `mayBreak`: only some of them do.");
    const byLabel = new Map<string, Set<string>>();
    for (const [n, rs] of r.breaks) for (const rule of rs) byLabel.set(labelText(n), (byLabel.get(labelText(n)) ?? new Set()).add(rule));
    for (const [label, rs] of byLabel) out.push(`- **${label}** breaks: ${[...rs].join("; ")}`);
  }
  return `${out.join("\n")}\n`;
}

// ---------- main ----------

const model = await load();
// Clear the previous run's files first, so a failed or chartless run never
// leaves an old chart behind.
await rm(path.join(outDir, "report.md"), { force: true });
await rm(path.join(outDir, "chart.mmd"), { force: true });
const result = explore(model);
const labels = labeller(model, result);
const chartStates = new Set(labels.labels.map((x) => canon(x))).size;
const cut = chartStates > budget;
const suspect = [
  ...Object.keys(model.actions)
    .filter((a) => !result.fired.has(a))
    .map((a) => `action ${a} never fired; its guard is probably wrong`),
  ...[...misses]
    .filter(([p]) => !known.has(p))
    .map(([p, hooks]) => `${[...hooks].join(", ")} read \`${p}\`, which no reachable state has; check the spelling`),
];
let keep = new Set(result.nodes.map((_, i) => i));
let keepEdges = new Set(result.edges);
if (cut) {
  keep = new Set();
  keepEdges = new Set();
  for (const bug of result.bugs.values()) {
    for (const p of pathTo(result, bug.state)) {
      keep.add(p.node);
      const e = result.edges.find((x) => x.to === p.node && x.from === result.nodes[p.node].parent && x.action === p.action);
      if (e) keepEdges.add(e);
    }
  }
}
const chart = keep.size ? mermaid(model, result, labels, keep, keepEdges) : null;
const text = report(model, result, labels, chart, cut ? { states: chartStates } : null, suspect);
await mkdir(outDir, { recursive: true });
await writeFile(path.join(outDir, "report.md"), text);
if (chart) await writeFile(path.join(outDir, "chart.mmd"), chart.text);
process.stdout.write(text);
process.stdout.write(`\nWrote ${path.join(outDir, "report.md")}${chart ? ` and ${path.join(outDir, "chart.mmd")}` : ""}\n`);
// A model that looks wrong is inconclusive whatever it found. Otherwise a found
// violation is conclusive even when the search is not, so 1 wins over 2.
// exitCode, not exit(), so a piped stdout is flushed in full.
process.exitCode = suspect.length ? 2 : result.bugs.size ? 1 : !result.complete || result.unchecked.size ? 2 : 0;

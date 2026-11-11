"""The run's dashboard: one self-contained HTML file beside run.json.

The job script rewrites it after every command, so the file always shows the
state the script last recorded. It carries the run and every job as inline
data and draws them in the browser, with no server and no network. Every
value reaches the page as text, never as markup, since notes and questions
come from files the agents write.
"""

import json
import os
import time

import factorylib as lib

NAME = "dashboard.html"
# A page left open follows the run without a server to push to it.
REFRESH_SECONDS = 10

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="__REFRESH__">
<title>Factory run</title>
<style>
:root { --bg: #f4f6f9; --card: #ffffff; --fg: #16202b; --muted: #556474; --rule: #d3dbe4;
  --you: #9a5200; --on-you: #ffffff; --good: #1d6b3a; --bad: #a32020; }
@media (prefers-color-scheme: dark) { :root { --bg: #10161d; --card: #19222c; --fg: #e6ecf2;
  --muted: #9aa9b8; --rule: #2a3643; --you: #f1b24c; --on-you: #1b1305; --good: #6fcf97; --bad: #ff8a80; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--fg);
  font: 15px/1.5 system-ui, "Segoe UI", sans-serif; }
main { max-width: 1280px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
h1 { font-size: 1.5rem; margin: 0; }
h2 { font-size: 1.05rem; margin: 0 0 8px; }
.meta, .small { color: var(--muted); font-size: 0.85rem; }
.meta span { margin-right: 16px; white-space: nowrap; }
.board { display: grid; grid-template-columns: repeat(7, minmax(150px, 1fr)); gap: 10px; overflow-x: auto; }
.column { background: var(--card); border: 1px solid var(--rule); border-radius: 8px; padding: 10px; min-height: 90px; }
.column h3 { margin: 0 0 8px; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.job { border: 1px solid var(--rule); border-radius: 6px; padding: 8px; margin-bottom: 8px; background: var(--bg); }
.job strong { display: block; overflow-wrap: anywhere; }
.you { background: var(--you); color: var(--on-you); border-color: var(--you); }
.you .small { color: var(--on-you); }
.pass { color: var(--good); font-weight: 600; }
.fail { color: var(--bad); font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: 0.88rem; }
th, td { text-align: left; vertical-align: top; padding: 6px 12px 6px 0; border-bottom: 1px solid var(--rule); overflow-wrap: anywhere; }
.scroll { overflow-x: auto; }
details { background: var(--card); border: 1px solid var(--rule); border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; }
summary { cursor: pointer; font-weight: 600; }
</style>
</head>
<body>
<main>
  <header>
    <h1 id="title"></h1>
    <p class="meta" id="meta"></p>
  </header>
  <section id="waiting"></section>
  <section><h2>Where each job is</h2><div class="board" id="board"></div></section>
  <section id="left-out"></section>
  <section><h2>History</h2><div id="history"></div></section>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById("data").textContent);
  var run = data.run, jobs = data.jobs;
  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    if (cls) { node.className = cls; }
    return node;
  }
  function span(parent, text) { parent.appendChild(el("span", text)); }
  function minutes(from, to) {
    var gap = (Date.parse(to) - Date.parse(from)) / 60000;
    if (isNaN(gap)) { return ""; }
    return gap < 1 ? "under 1 min" : gap < 90 ? Math.round(gap) + " min" : (gap / 60).toFixed(1) + " h";
  }
  function verdicts(job) {
    var parts = [];
    if (job.gate) { parts.push("gate " + job.gate); }
    Object.keys(job.reviews || {}).sort().forEach(function (name) { parts.push(name + " " + job.reviews[name]); });
    return parts.join(", ");
  }

  document.title = "Factory: " + run.title;
  document.getElementById("title").textContent = run.title;
  var meta = document.getElementById("meta");
  span(meta, "Spec " + run.spec);
  span(meta, "Mode " + run.mode);
  if (run.integration_branch) { span(meta, "Integration branch " + run.integration_branch); }
  span(meta, "Base " + run.base.ref + " at " + String(run.base.sha).slice(0, 10));
  if (run.final && run.final.pr) { span(meta, "Final pull request " + run.final.pr + " (gate " + run.final.gate + ")"); }
  span(meta, "Updated " + data.generated);

  var waiting = jobs.filter(function (job) { return job.stage === "needs-owner" || job.stage === "blocked"; });
  var section = document.getElementById("waiting");
  if (waiting.length) {
    section.appendChild(el("h2", "Waiting on you"));
    waiting.forEach(function (job) {
      var card = el("div", null, "job you");
      card.appendChild(el("strong", job.id + " (" + job.stage + ")"));
      card.appendChild(el("div", job.note || job.question || "No question recorded."));
      if ((job.escalate || []).length) { card.appendChild(el("div", "Escalation: " + job.escalate.join("; "), "small")); }
      section.appendChild(card);
    });
  }

  var columns = [["planned", "Planned"], ["build", "Build"], ["gate", "Gate"], ["review", "Review"],
    ["approve", "Approve"], ["merging", "Merging"], ["done", "Merged or merge-ready"]];
  var board = document.getElementById("board");
  columns.forEach(function (column) {
    var box = el("div", null, "column");
    box.appendChild(el("h3", column[1]));
    jobs.forEach(function (job) {
      var where = (job.stage === "merged" || job.stage === "merge-ready") ? "done" : job.stage;
      if (where !== column[0]) { return; }
      var card = el("div", null, "job");
      card.appendChild(el("strong", job.id));
      card.appendChild(el("div", "Round " + job.round + " of " + job.round_limit + (job.pr ? ", pull request " + job.pr : ""), "small"));
      var read = verdicts(job);
      if (read) { card.appendChild(el("div", read, /FAIL|CHANGES/.test(read) ? "small fail" : "small pass")); }
      if (where === "done") { card.appendChild(el("div", job.stage, "small")); }
      card.appendChild(el("div", "Risk " + job.risk + "; reviewers " + (job.reviewers || []).join(", "), "small"));
      box.appendChild(card);
    });
    board.appendChild(box);
  });

  var out = document.getElementById("left-out");
  var rows = (run.ineligible || []).map(function (step) { return ["Step " + step.step, "ineligible", step.reason]; })
    .concat((run.skipped || []).map(function (step) { return ["Step " + step.step, "skipped", step.reason || "already done"]; }));
  if (rows.length) {
    out.appendChild(el("h2", "Steps the factory left out"));
    var table = el("table");
    rows.forEach(function (row) {
      var line = el("tr");
      row.forEach(function (cell) { line.appendChild(el("td", cell)); });
      table.appendChild(line);
    });
    out.appendChild(table);
  }

  var history = document.getElementById("history");
  jobs.forEach(function (job) {
    var block = el("details");
    block.appendChild(el("summary", job.id + ": " + job.title + " (" + job.stage + ")"));
    var wrap = el("div", null, "scroll");
    var table = el("table");
    var head = el("tr");
    ["When", "From", "To", "Round", "Time in the stage left", "Note"].forEach(function (name) { head.appendChild(el("th", name)); });
    table.appendChild(head);
    (job.history || []).forEach(function (move, index) {
      var line = el("tr");
      var before = index > 0 ? job.history[index - 1].at : null;
      [move.at, move.from, move.to, move.round, before ? minutes(before, move.at) : "", move.note || ""].forEach(function (cell) {
        line.appendChild(el("td", cell));
      });
      table.appendChild(line);
    });
    wrap.appendChild(table);
    block.appendChild(wrap);
    history.appendChild(block);
  });
})();
</script>
</body>
</html>
"""


def snapshot(run_state, jobs):
    """The run and its jobs as one value: what the dashboard and `status --json` show."""
    return {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "run": run_state, "jobs": jobs}


def render(run_state, jobs):
    data = json.dumps(snapshot(run_state, jobs))
    # Inline JSON must not be able to close its script element or open a comment.
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return PAGE.replace("__REFRESH__", str(REFRESH_SECONDS)).replace("__DATA__", data)


def write(directory, run_state, jobs):
    """Rewrite the dashboard in the run folder and return its path."""
    path = os.path.join(directory, NAME)
    lib.write_atomic(path, render(run_state, jobs))
    return path

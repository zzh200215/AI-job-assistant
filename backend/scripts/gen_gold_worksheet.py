#!/usr/bin/env python
"""Generate the P2 real-resume gold labeling worksheet (single-file HTML)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "tests" / "eval"
TEMPLATE_PATH = EVAL_DIR / "human_gold_TO_FILL.json"
OUTPUT_PATH = EVAL_DIR / "human_gold_worksheet.html"

HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>P2 真文本 Gold 标注工作表</title>
<style>
  :root {
    color-scheme: light;
    --bg: #f5f7fb;
    --card: #ffffff;
    --ink: #1f2430;
    --muted: #667085;
    --line: #d9dee8;
    --accent: #2f5bd3;
    --ok: #1f8a5b;
    --danger: #b42318;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }
  header { padding: 22px 24px 10px; }
  h1 { margin: 0 0 6px; font-size: 22px; letter-spacing: .01em; }
  h2 { margin: 0 0 10px; font-size: 15px; }
  .note { margin: 4px 0; color: var(--muted); font-size: 13px; line-height: 1.65; }
  .note code { color: var(--ink); background: #eef2ff; padding: 1px 5px; border-radius: 5px; }
  .progress { margin-top: 8px; font-weight: 650; color: var(--accent); }
  .tabs { display: flex; flex-wrap: wrap; gap: 8px; padding: 6px 24px 14px; }
  .tab {
    display: flex; align-items: center; gap: 8px;
    border: 1px solid var(--line); background: var(--card); color: var(--ink);
    border-radius: 999px; padding: 7px 12px; cursor: pointer; font: inherit;
  }
  .tab.active { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(47, 91, 211, .12); }
  .tab-id { font-weight: 650; }
  .tab-file { color: var(--muted); font-size: 12px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #cbd5e1; }
  .dot.done { background: var(--ok); }
  .workspace { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; padding: 0 24px; }
  .pane { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; min-height: 70vh; }
  #source-text {
    margin: 0; padding: 12px; max-height: 72vh; overflow: auto;
    white-space: pre-wrap; word-break: break-word;
    font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
    font-size: 13px; line-height: 1.65; background: #fafbfe;
    border: 1px solid var(--line); border-radius: 8px;
  }
  label { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; color: var(--muted); font-size: 13px; }
  input, textarea {
    width: 100%; font: inherit; color: var(--ink); background: #fff;
    border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px;
  }
  textarea { resize: vertical; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  fieldset { border: 1px solid var(--line); border-radius: 10px; margin: 14px 0; padding: 12px; }
  legend { padding: 0 6px; color: var(--ink); font-weight: 650; }
  .entry { border: 1px dashed var(--line); border-radius: 10px; padding: 12px; margin-bottom: 10px; background: #fcfdff; }
  .entry-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .entry-head strong { font-size: 13px; }
  button {
    font: inherit; border: 1px solid var(--line); background: var(--card); color: var(--ink);
    border-radius: 8px; padding: 8px 12px; cursor: pointer;
  }
  button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  button.danger { color: var(--danger); border-color: #fecdca; background: #fffbfa; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; padding: 16px 24px 24px; }
  .done-row { flex-direction: row; align-items: center; gap: 8px; margin: 14px 0 0; color: var(--ink); font-weight: 650; }
  .done-row input { width: auto; }
  pre.preview {
    margin: 0 24px 24px; padding: 14px; max-height: 40vh; overflow: auto;
    background: #0f172a; color: #e2e8f0; border-radius: 10px;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; line-height: 1.6;
  }
  @media (max-width: 980px) {
    .workspace { grid-template-columns: 1fr; }
    .grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<header>
  <h1>P2 真文本 Gold 标注工作表</h1>
  <p class="note">只填原文里确实有的内容；不确定就留空。技能名、公司名、项目名照原文写，描述摘要点即可，不必逐字抄。</p>
  <p class="note">本版已按助手代标（2026-10-20，zzh 指示）预填，供你复核与修正；技能/经历/项目都对着左侧原文改。</p>
  <p class="note">填完一份勾选“本份标完”。四份完成后点“导出 human_gold_TO_FILL.json”，用它替换 <code>backend/tests/eval/human_gold_TO_FILL.json</code>。</p>
  <p class="note">本页不调用任何接口，数据只留在本机浏览器；导出的 JSON 才是结果。</p>
  <div class="progress" id="progress" aria-live="polite"></div>
</header>

<nav class="tabs" id="tabs" aria-label="简历列表"></nav>

<main class="workspace">
  <aside class="pane">
    <h2>原文</h2>
    <p class="note" id="source-file"></p>
    <pre id="source-text"></pre>
  </aside>

  <section class="pane">
    <h2>Gold</h2>
    <form id="gold-form" autocomplete="off">
      <div class="grid">
        <label>工作年限（年）<input id="years_exp" inputmode="numeric" placeholder="例如 1"></label>
        <label>学历<input id="education" placeholder="例如 本科"></label>
        <label>专业<input id="major" placeholder="例如 计算机科学与技术"></label>
        <label>当前公司<input id="current_company"></label>
        <label>当前职位<input id="current_title"></label>
      </div>

      <label>技能（每行一个，或用逗号分隔）
        <textarea id="skills" rows="4" placeholder="例如：Python&#10;FastAPI"></textarea>
      </label>

      <fieldset>
        <legend>工作经历</legend>
        <div id="work-list"></div>
        <button type="button" id="add-work">添加工作经历</button>
      </fieldset>

      <fieldset>
        <legend>项目经历</legend>
        <div id="project-list"></div>
        <button type="button" id="add-project">添加项目经历</button>
      </fieldset>

      <label class="done-row"><input type="checkbox" id="done"> 本份标完</label>
    </form>
  </section>
</main>

<div class="actions">
  <button type="button" class="primary" id="preview-btn">预览 JSON</button>
  <button type="button" id="download-btn">导出 human_gold_TO_FILL.json</button>
  <button type="button" id="import-btn">导入已有 JSON</button>
  <input type="file" id="import-file" accept=".json,application/json" hidden>
  <button type="button" class="danger" id="reset-btn">清空本机进度</button>
</div>
<pre id="preview" class="preview" hidden></pre>

<template id="work-template">
  <div class="entry">
    <div class="entry-head"><strong>工作经历</strong><button type="button" class="remove danger">删除</button></div>
    <div class="grid">
      <label>公司<input data-k="company"></label>
      <label>职位<input data-k="title"></label>
      <label>开始<input data-k="start" placeholder="例如 2023.07"></label>
      <label>结束<input data-k="end" placeholder="例如 2024.06 / 至今"></label>
    </div>
    <label>描述<textarea data-k="desc" rows="2"></textarea></label>
  </div>
</template>

<template id="project-template">
  <div class="entry">
    <div class="entry-head"><strong>项目经历</strong><button type="button" class="remove danger">删除</button></div>
    <div class="grid">
      <label>项目名<input data-k="name"></label>
      <label>角色<input data-k="role"></label>
      <label>开始<input data-k="start" placeholder="例如 2024.03"></label>
      <label>结束<input data-k="end" placeholder="例如 2024.09"></label>
    </div>
    <label>技术栈（用逗号分隔）<input data-k="tech"></label>
    <label>描述<textarea data-k="desc" rows="2"></textarea></label>
  </div>
</template>

<script id="seed-data" type="application/json">__SEED_DATA__</script>
<script>
(function () {
  'use strict';

  var seed = JSON.parse(document.getElementById('seed-data').textContent);
  var TEMPLATE = seed.template;
  var TEXTS = seed.texts;
  var STORAGE_KEY = 'p2-gold-worksheet-v1';
  var SCALARS = ['years_exp', 'education', 'major', 'current_company', 'current_title'];

  var tabsEl = document.getElementById('tabs');
  var progressEl = document.getElementById('progress');
  var sourceFileEl = document.getElementById('source-file');
  var sourceTextEl = document.getElementById('source-text');
  var workListEl = document.getElementById('work-list');
  var projectListEl = document.getElementById('project-list');
  var workTemplate = document.getElementById('work-template');
  var projectTemplate = document.getElementById('project-template');
  var previewEl = document.getElementById('preview');
  var importFileEl = document.getElementById('import-file');

  function blankGold() {
    return {
      skillsText: '',
      work_experience: [],
      project_experience: [],
      years_exp: '',
      education: '',
      major: '',
      current_company: '',
      current_title: ''
    };
  }

  function normalizeGold(raw) {
    var gold = blankGold();
    if (!raw) return gold;
    gold.skillsText = Array.isArray(raw.skills) ? raw.skills.join('\n') : (raw.skills || '');
    gold.work_experience = Array.isArray(raw.work_experience) ? raw.work_experience.map(function (item) {
      return {
        company: item.company || '',
        title: item.title || '',
        start: item.start || '',
        end: item.end || '',
        desc: item.desc || ''
      };
    }) : [];
    gold.project_experience = Array.isArray(raw.project_experience) ? raw.project_experience.map(function (item) {
      return {
        name: item.name || '',
        role: item.role || '',
        start: item.start || '',
        end: item.end || '',
        techText: Array.isArray(item.tech) ? item.tech.join('、') : (item.tech || ''),
        desc: item.desc || ''
      };
    }) : [];
    SCALARS.forEach(function (key) { gold[key] = raw[key] == null ? '' : String(raw[key]); });
    return gold;
  }

  function initialRows() {
    return TEMPLATE.rows.map(function (row) {
      return { status: row._状态 === 'done' ? 'done' : 'todo', gold: normalizeGold(row) };
    });
  }

  function loadRows() {
    var fallback = initialRows();
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return fallback;
      var saved = JSON.parse(raw);
      if (!Array.isArray(saved) || saved.length !== TEMPLATE.rows.length) return fallback;
      return TEMPLATE.rows.map(function (row, index) {
        var item = saved[index] || {};
        return { status: item.status === 'done' ? 'done' : 'todo', gold: normalizeGold(item.gold) };
      });
    } catch (err) {
      return fallback;
    }
  }

  var rows = loadRows();
  var selected = 0;

  function save() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(rows)); } catch (err) { /* 本机存储不可用时仍可导出 */ }
  }

  function selectedRow() { return rows[selected]; }

  function renderTabs() {
    tabsEl.textContent = '';
    TEMPLATE.rows.forEach(function (base, index) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'tab' + (index === selected ? ' active' : '');
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', index === selected ? 'true' : 'false');

      var id = document.createElement('span');
      id.className = 'tab-id';
      id.textContent = base.id;
      var file = document.createElement('span');
      file.className = 'tab-file';
      file.textContent = base.source_file.split('/').pop();
      var dot = document.createElement('span');
      dot.className = 'dot' + (rows[index].status === 'done' ? ' done' : '');

      button.append(id, file, dot);
      button.addEventListener('click', function () {
        selected = index;
        renderTabs();
        renderSource();
        renderForm();
      });
      tabsEl.append(button);
    });
    var done = rows.filter(function (row) { return row.status === 'done'; }).length;
    progressEl.textContent = '已标完 ' + done + ' / ' + rows.length;
  }

  function renderSource() {
    var base = TEMPLATE.rows[selected];
    sourceFileEl.textContent = base.source_file;
    sourceTextEl.textContent = TEXTS[base.id] || '';
  }

  function bindEntryFields(node, item, kind) {
    node.querySelectorAll('[data-k]').forEach(function (input) {
      var key = input.dataset.k === 'tech' ? 'techText' : input.dataset.k;
      input.value = item[key] || '';
      input.addEventListener('input', function () {
        item[key] = input.value;
        save();
      });
    });
    node.querySelector('.remove').addEventListener('click', function () {
      var list = kind === 'work' ? selectedRow().gold.work_experience : selectedRow().gold.project_experience;
      var index = list.indexOf(item);
      if (index >= 0) list.splice(index, 1);
      save();
      renderForm();
    });
  }

  function renderEntries(kind, list, container, template) {
    container.textContent = '';
    list.forEach(function (item) {
      var node = template.content.firstElementChild.cloneNode(true);
      bindEntryFields(node, item, kind);
      container.append(node);
    });
  }

  function renderForm() {
    var row = selectedRow();
    SCALARS.forEach(function (key) {
      document.getElementById(key).value = row.gold[key] || '';
    });
    document.getElementById('skills').value = row.gold.skillsText || '';
    document.getElementById('done').checked = row.status === 'done';
    renderEntries('work', row.gold.work_experience, workListEl, workTemplate);
    renderEntries('project', row.gold.project_experience, projectListEl, projectTemplate);
  }

  function splitList(text) {
    return String(text || '').split(/[\n,，、;；]+/).map(function (item) {
      return item.trim();
    }).filter(Boolean);
  }

  function buildExport() {
    var out = JSON.parse(JSON.stringify(TEMPLATE));
    out.rows = out.rows.map(function (base, index) {
      var row = rows[index];
      var gold = row.gold;
      var work = gold.work_experience.map(function (item) {
        return {
          company: item.company.trim() || null,
          title: item.title.trim() || null,
          start: item.start.trim() || null,
          end: item.end.trim() || null,
          desc: item.desc.trim() || null
        };
      }).filter(function (item) {
        return Object.keys(item).some(function (key) { return item[key] !== null; });
      });
      var projects = gold.project_experience.map(function (item) {
        return {
          name: item.name.trim() || null,
          role: item.role.trim() || null,
          start: item.start.trim() || null,
          end: item.end.trim() || null,
          desc: item.desc.trim() || null,
          tech: splitList(item.techText)
        };
      }).filter(function (item) {
        return Object.keys(item).some(function (key) {
          return Array.isArray(item[key]) ? item[key].length > 0 : item[key] !== null;
        });
      });
      var yearsText = String(gold.years_exp == null ? '' : gold.years_exp).trim();
      var years = Number.parseInt(yearsText, 10);
      return Object.assign({}, base, {
        _状态: row.status === 'done' ? 'done' : 'todo',
        skills: splitList(gold.skillsText),
        work_experience: work,
        project_experience: projects,
        years_exp: Number.isFinite(years) ? years : null,
        education: gold.education.trim() || null,
        major: gold.major.trim() || null,
        current_company: gold.current_company.trim() || null,
        current_title: gold.current_title.trim() || null
      });
    });
    return out;
  }

  SCALARS.forEach(function (key) {
    document.getElementById(key).addEventListener('input', function (event) {
      selectedRow().gold[key] = event.target.value;
      save();
    });
  });

  document.getElementById('skills').addEventListener('input', function (event) {
    selectedRow().gold.skillsText = event.target.value;
    save();
  });

  document.getElementById('done').addEventListener('change', function (event) {
    selectedRow().status = event.target.checked ? 'done' : 'todo';
    save();
    renderTabs();
  });

  document.getElementById('add-work').addEventListener('click', function () {
    selectedRow().gold.work_experience.push({ company: '', title: '', start: '', end: '', desc: '' });
    save();
    renderForm();
  });

  document.getElementById('add-project').addEventListener('click', function () {
    selectedRow().gold.project_experience.push({ name: '', role: '', start: '', end: '', techText: '', desc: '' });
    save();
    renderForm();
  });

  document.getElementById('preview-btn').addEventListener('click', function () {
    previewEl.hidden = false;
    previewEl.textContent = JSON.stringify(buildExport(), null, 2);
  });

  document.getElementById('download-btn').addEventListener('click', function () {
    var blob = new Blob([JSON.stringify(buildExport(), null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'human_gold_TO_FILL.json';
    anchor.click();
    URL.revokeObjectURL(url);
  });

  document.getElementById('import-btn').addEventListener('click', function () {
    importFileEl.click();
  });

  importFileEl.addEventListener('change', function () {
    var file = importFileEl.files && importFileEl.files[0];
    if (!file) return;
    file.text().then(function (text) {
      var data = JSON.parse(text);
      if (!data || !Array.isArray(data.rows) || data.rows.length !== TEMPLATE.rows.length) {
        throw new Error('行数与当前模板不一致');
      }
      var byId = new Map(data.rows.map(function (row) { return [row.id, row]; }));
      TEMPLATE.rows.forEach(function (base, index) {
        var source = byId.get(base.id);
        if (!source) throw new Error('缺少 ' + base.id);
        rows[index] = { status: source._状态 === 'done' ? 'done' : 'todo', gold: normalizeGold(source) };
      });
      save();
      renderTabs();
      renderSource();
      renderForm();
    }).catch(function (err) {
      window.alert('导入失败：' + err.message);
    }).finally(function () {
      importFileEl.value = '';
    });
  });

  document.getElementById('reset-btn').addEventListener('click', function () {
    if (!window.confirm('清空本机进度？已经导出的 JSON 不受影响。')) return;
    rows = initialRows();
    selected = 0;
    save();
    renderTabs();
    renderSource();
    renderForm();
  });

  window.__goldWorksheet = {
    buildExport: buildExport,
    rows: function () { return JSON.parse(JSON.stringify(rows)); },
    select: function (index) {
      selected = Math.max(0, Math.min(rows.length - 1, Number(index) || 0));
      renderTabs();
      renderSource();
      renderForm();
    }
  };

  renderTabs();
  renderSource();
  renderForm();
})();
</script>
</body>
</html>
"""


def build_seed() -> dict:
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    rows = template.get("rows") or []
    if not rows:
        raise SystemExit(f"[ERROR] no rows in {TEMPLATE_PATH}")

    ids = set()
    texts: dict[str, str] = {}
    sources: dict[str, dict[str, str]] = {}
    for row in rows:
        row_id = str(row.get("id") or "")
        source_file = str(row.get("source_file") or "")
        if not row_id or not source_file:
            raise SystemExit(f"[ERROR] row missing id/source_file: {row}")
        if row_id in ids:
            raise SystemExit(f"[ERROR] duplicate row id: {row_id}")
        ids.add(row_id)
        path = EVAL_DIR / source_file
        if not path.exists():
            raise SystemExit(f"[ERROR] source file not found: {path}")
        text = path.read_text(encoding="utf-8")
        texts[row_id] = text
        sources[row_id] = {
            "file": source_file,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "chars": str(len(text)),
        }

    return {"template": template, "texts": texts, "sources": sources}


def render(seed: dict) -> str:
    payload = json.dumps(seed, ensure_ascii=False).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__SEED_DATA__", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check the P2 gold labeling worksheet")
    parser.add_argument("--check", action="store_true", help="Fail when the checked-in worksheet is stale")
    args = parser.parse_args(argv)

    seed = build_seed()
    html = render(seed)
    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"[STALE] missing {OUTPUT_PATH}")
            return 2
        current = OUTPUT_PATH.read_text(encoding="utf-8")
        if current != html:
            print("[STALE] worksheet differs from template/source files; run without --check")
            return 2
        print(f"[OK] {OUTPUT_PATH.name}: {len(seed['template']['rows'])} rows, {len(html)} chars")
        return 0

    OUTPUT_PATH.write_text(html, encoding="utf-8", newline="\n")
    print(f"[OK] wrote {OUTPUT_PATH} ({len(html)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: bash export_trace.sh 'YYYY-MM-DD HH:MM:SS' 'YYYY-MM-DD HH:MM:SS' /absolute/output.json" >&2
  exit 2
fi

START_LOCAL=$1
END_LOCAL=$2
OUTPUT_JSON=$3
TRACE_URL=${TRACE_URL:-"https://www.workbuddy.cn/admin/observability/trace"}
TIME_PATTERN='^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$'

if [[ ! "$START_LOCAL" =~ $TIME_PATTERN ]] || [[ ! "$END_LOCAL" =~ $TIME_PATTERN ]]; then
  echo "Dates must use 'YYYY-MM-DD HH:MM:SS' in China Standard Time (UTC+8)." >&2
  exit 2
fi
if ! command -v playwright-cli >/dev/null 2>&1; then
  echo "playwright-cli is required. Install it with: npm install -g @playwright/cli@latest" >&2
  exit 2
fi

START_TS=$(date -d "$START_LOCAL +0800" +%s)
END_TS=$(date -d "$END_LOCAL +0800" +%s)
if (( END_TS < START_TS )); then
  echo "End time must be greater than or equal to start time." >&2
  exit 2
fi

mkdir -p "$(dirname "$OUTPUT_JSON")"
export PLAYWRIGHT_MCP_EXTENSION=1

playwright-cli open "$TRACE_URL" >/dev/null
playwright-cli --raw run-code "async page => {
  await page.waitForTimeout(5000);
  const organizationInput = page.getByPlaceholder('全部组织（可多选，仅统计所选部门直属成员）');
  await organizationInput.waitFor({ state: 'visible', timeout: 30000 });
  await organizationInput.click({ force: true });
  await page.waitForTimeout(800);

  const options = page.locator('.t-tree-select-popup label.t-checkbox');
  const selected = [];
  const excluded = [];
  const optionCount = await options.count();
  if (!optionCount) throw new Error('No organization options found. Confirm the organization tree selector and login state.');
  for (let i = 0; i < optionCount; i++) {
    const option = options.nth(i);
    const name = (await option.innerText()).trim();
    const input = option.locator('input[type=checkbox]');
    const checked = await input.isChecked();
    if (name === '不导出') {
      excluded.push(name);
      if (checked) {
        await option.evaluate(el => el.click());
        await page.waitForTimeout(80);
      }
    } else {
      selected.push(name);
      if (!checked) {
        await option.evaluate(el => el.click());
        await page.waitForTimeout(80);
      }
    }
  }
  if (!selected.length) throw new Error('No organization nodes were selected.');
  const optionStates = await options.evaluateAll(els => els.map(e => ({
    name: e.innerText.trim(),
    checked: e.querySelector('input').checked
  })));
  if (optionStates.some(s => s.name === '不导出' ? s.checked : !s.checked)) {
    throw new Error('Organization checkbox verification failed: ' + JSON.stringify(optionStates));
  }
  await page.keyboard.press('Escape');

  let headers = null;
  let firstUrl = null;
  page.on('request', r => {
    if (r.url().includes('/observability/traces?')) {
      headers = r.headers();
      firstUrl = r.url();
    }
  });
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  await page.waitForTimeout(2500);
  if (!headers || !firstUrl) throw new Error('No trace request captured after applying organization filters.');

  const captured = new URL(firstUrl);
  const start = Number('$START_TS');
  const end = Number('$END_TS');
  const segments = [];

  async function query(s, e, p) {
    const u = new URL(captured.toString());
    u.searchParams.set('page', String(p));
    u.searchParams.set('pageSize', '100');
    u.searchParams.set('range.start', String(s));
    u.searchParams.set('range.end', String(e));
    const r = await page.request.get(u.toString(), { headers });
    const j = await r.json();
    if (r.status() !== 200) throw new Error(j.msg || ('HTTP ' + r.status()));
    return j.data;
  }

  async function fetchRange(s, e, depth = 0) {
    if (e - s + 1 > 7 * 24 * 60 * 60 && depth < 16) {
      const mid = Math.floor((s + e) / 2);
      const left = await fetchRange(s, mid, depth + 1);
      const right = await fetchRange(mid + 1, e, depth + 1);
      return left.concat(right);
    }
    const first = await query(s, e, 1);
    const total = first.total || 0;
    if (total >= 1000 && e > s && depth < 16) {
      const mid = Math.floor((s + e) / 2);
      const left = await fetchRange(s, mid, depth + 1);
      const right = await fetchRange(mid + 1, e, depth + 1);
      return left.concat(right);
    }
    if (total >= 1000) throw new Error('A one-second segment still contains at least 1000 records; manual investigation is required.');
    const records = [...(first.records || [])];
    const pages = Math.ceil(total / 100);
    for (let p = 2; p <= pages; p++) {
      const data = await query(s, e, p);
      records.push(...(data.records || []));
    }
    segments.push({ start: s, end: e, total, downloaded: records.length });
    return records;
  }

  const raw = await fetchRange(start, end);
  const unique = new Map();
  for (const record of raw) unique.set(record.traceId, record);
  const records = [...unique.values()].sort((a, b) => (b.startTimeMs || 0) - (a.startTimeMs || 0));

  const statsSegments = [];
  const statsErrors = [];
  let conversations = 0;
  let credits = 0;
  let errors = 0;
  for (const segment of segments) {
    const u = new URL(captured.toString());
    u.pathname = u.pathname.replace(/\/traces$/, '/trace-stats');
    u.searchParams.delete('page');
    u.searchParams.delete('pageSize');
    u.searchParams.set('range.start', String(segment.start));
    u.searchParams.set('range.end', String(segment.end));
    const r = await page.request.get(u.toString(), { headers });
    const j = await r.json();
    if (r.status() === 200 && j.data) {
      conversations += j.data.conversations?.value || 0;
      credits += j.data.credits?.value || 0;
      errors += j.data.errors?.value || 0;
      statsSegments.push({ start: segment.start, end: segment.end, ...j.data });
    } else {
      statsErrors.push(j.msg || ('HTTP ' + r.status()));
    }
  }

  return {
    source: '$TRACE_URL',
    range: {
      start,
      end,
      startLocal: '$START_LOCAL +08:00',
      endLocal: '$END_LOCAL +08:00'
    },
    exportedAt: new Date().toISOString(),
    organizationScope: { selected, excluded, optionStates },
    count: records.length,
    fields: records[0] ? Object.keys(records[0]) : [],
    pageStats: {
      conversations: { value: conversations },
      credits: { value: credits },
      errors: { value: errors },
      segments: statsSegments
    },
    pageStatsError: statsErrors.length ? statsErrors.join('; ') : null,
    segments,
    records
  };
}" > "$OUTPUT_JSON"

python -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p,encoding="utf-8")); print(json.dumps({"output":p,"records":d["count"],"segments":len(d["segments"]),"allSegmentsComplete":all(s["downloaded"]==s["total"] for s in d["segments"]),"uniqueTraceIds":len({r.get("traceId") for r in d["records"]}),"pageConversations":d["pageStats"]["conversations"]["value"],"pageCredits":d["pageStats"]["credits"]["value"],"statsError":d["pageStatsError"],"organizationSelected":len(d["organizationScope"]["selected"]),"organizationExcluded":d["organizationScope"]["excluded"]},ensure_ascii=False))' "$OUTPUT_JSON"

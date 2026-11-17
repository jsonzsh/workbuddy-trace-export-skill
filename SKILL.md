---
name: workbuddy-trace-export
description: This skill should be used when the user asks to export, download, or analyze WorkBuddy 企业控制台「可观测中心 / 会话追踪 / Trace」logs for a relative or absolute time range, including 近7天、指定起止日期、跨周日志、会话追踪明细、JSON 导出和 Excel 汇总分析. It handles Chrome extension authentication, the 7-day query-span limit, the 1,000-record query cap, 100-record pagination, traceId deduplication, and page-versus-detail metric differences.
agent_created: true
---

# WorkBuddy Trace Export

## Overview

Export WorkBuddy Trace list records to JSON and generate an Excel workbook with summary KPIs, daily trends, user statistics, row-level details, and field notes. Preserve the requested time boundaries while automatically splitting restricted queries.

Use this workflow for **列表明细导出**, not for claiming a Trace 全文导出. The UI full-text export is a separate asynchronous operation and may be limited to selected rows.

## Prerequisites

- Use Chrome with the **Playwright Extension** installed and an authenticated WorkBuddy enterprise-console session.
- Install `@playwright/cli@latest` when `playwright-cli` is unavailable. Load the `playwright-cli` skill for connection troubleshooting.
- Obtain `PLAYWRIGHT_MCP_EXTENSION_TOKEN` from the extension UI for the active Chrome profile when connection approval is required.
- Inject the token only into the current process environment. Never write it into SKILL.md, scripts, project files, logs, screenshots, or the final response.
- Use Bash with GNU `date -d` for the bundled export script; Windows Git Bash is supported.
- Load `workbuddy-sheetagent`, then enter `workbuddy-sheet-generation`, before generating an Excel deliverable. Follow that skill's design, recalculation, and AIGC-label requirements.

## Workflow

### 1. Normalize the request

- Parse absolute ranges as China Standard Time (UTC+8) unless the user specifies another timezone.
- Resolve relative ranges such as「近 7 天」from the current time; do not silently replace them with calendar weeks.
- Preserve inclusive end times such as `23:59:59`.
- Name outputs with absolute paths, for example:
  - `trace-YYYYMMDD-YYYYMMDD.json`
  - `YYYY-MM-DD至YYYY-MM-DD会话追踪日志与分析.xlsx`
- Avoid overwriting an earlier export unless the user explicitly requests replacement.

### 2. Connect to the existing Chrome session

- Open `https://www.workbuddy.cn/admin/observability/trace` through the extension connection.
- Confirm that the enterprise console is accessible without asking for credentials again.
- Capture request headers in memory from the page's own `observability/traces` request. Do not print authorization headers or cookies.

### 3. Export the complete list records

Run:

```bash
export PLAYWRIGHT_MCP_EXTENSION_TOKEN='<current-profile-token>'
bash "$HOME/.workbuddy/skills/workbuddy-trace-export/scripts/export_trace.sh" \
  "2026-11-03 00:00:00" \
  "2026-11-10 23:59:59" \
  "/absolute/path/trace-20261103-20261110.json"
```

The export script must:

- Split any range longer than 7 days before querying.
- Split any query returning `total >= 1000` recursively by time.
- Fetch up to 100 records per page and all pages in each leaf range.
- Deduplicate merged records by `traceId` and sort by `startTimeMs` descending.
- Query `trace-stats` only within each leaf range; aggregate conversations, credits, and errors across ranges.
- Leave overall latency percentiles unmerged across ranges. Let the workbook calculate percentiles from detail records when no overall statistic exists.
- Validate that the output is JSON and print record, segment, page-conversation, and credit totals.

### 4. Verify the export

Check all of the following before delivery:

- `range.startLocal` and `range.endLocal` match the requested boundaries.
- Every leaf segment has `downloaded == total`.
- `count` equals the number of unique `traceId` values in `records`.
- `pageStatsError` is either empty or explicitly reported.
- A zero-record result is reported as no matching logs; do not build an empty analysis workbook.

### 5. Generate the Excel analysis workbook

Run:

```bash
python "$HOME/.workbuddy/skills/workbuddy-trace-export/scripts/build_trace_workbook.py" \
  "/absolute/path/trace-20261103-20261110.json" \
  "/absolute/path/2026-11-03至2026-11-10会话追踪日志与分析.xlsx" \
  "2026-11-03至2026-11-10会话追踪日志与分析"
```

Produce these five worksheets:

1. `汇总`
2. `每日趋势`
3. `用户统计`
4. `明细`
5. `字段说明`

Run `recalc.py` from the loaded `workbuddy-sheet-generation` resources and require `status=success` with `total_errors=0`. Then run `aigc_label.py` with `--platform WORKBUDDY`. Do not deliver the workbook when either validation fails.

### 6. Report results

- Present the XLSX first and the raw JSON second.
- State the exact range, unique detail count, session count, user count, and validation result.
- Keep page-summary and detail-record counts separate when they differ.
- Disclose missing or zero-valued detail metrics instead of interpreting them as genuine zero usage.
- Warn that inputs and outputs can contain confidential business data.

## Data Rules

- Treat `traceId` as the row-level deduplication key and `sessionId` as the task-session key.
- Treat `status=success` as a response status, not proof of good latency or successful task completion.
- Identify title-generation rows by `output` containing `isNewTopic`; keep them separate in performance analysis.
- Treat `input` and `output` as list-record content or previews. Do not describe them as complete trace payloads.
- Do not sum or average page-level P50/P90/P99 values across time segments.
- Do not infer that `credits`, `llmCallCount`, `toolCallCount`, or `toolErrorCount` are truly zero when the list API returns zero for every row.
- Read `references/api_reference.md` when changing endpoints, diagnosing errors, or interpreting fields.

## Failure Handling

- **`No clients are currently connected`**: reconnect through the Playwright Extension and verify the token belongs to the active Chrome profile.
- **401**: reload the authenticated trace page and recapture request headers in memory.
- **`range exceeds query span limit of 7 days`**: split the range before both `traces` and `trace-stats` requests.
- **`pageSize exceeds limit 100`**: reduce `pageSize` to 100.
- **Missing records after merge**: inspect each leaf segment's `total` and `downloaded`, then check duplicate `traceId` values before retrying.
- **Workbook formula errors**: correct the workbook script, regenerate, recalculate, and reapply the AIGC label.

## Examples

- 「导出 2026-11-03 00:00:00 到 2026-11-10 23:59:59 的会话追踪」
- 「分析近 7 天 Trace 日志并下载成 Excel」
- 「把上个月每周的会话追踪明细分别导出来」
- 「统计指定日期范围内每天对话数、用户活跃度和耗时，并保留原始 JSON」

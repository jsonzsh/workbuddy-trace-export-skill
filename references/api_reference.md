# WorkBuddy Trace API Reference

## Scope

Use the authenticated enterprise-console requests captured from the current Chrome session. The enterprise ID is part of the request path; discover it from the page request instead of hardcoding it.

Base page:

```text
https://www.workbuddy.cn/admin/observability/trace
```

## List records

```http
GET /console/enterprises/{enterpriseId}/observability/traces
```

Required query parameters:

- `page`: 1-based page number.
- `pageSize`: maximum 100.
- `range.start`: inclusive Unix timestamp in seconds.
- `range.end`: inclusive Unix timestamp in seconds.

Observed response shape:

```json
{
  "code": 0,
  "msg": "OK",
  "data": {
    "total": 100,
    "hasMore": false,
    "totalIsEstimated": false,
    "records": []
  }
}
```

Important limits:

- A single time span cannot exceed 7 days.
- A query can expose at most 1,000 list records. Split the time range when `total >= 1000`.
- Fetch every page using `pageSize=100`.
- Deduplicate split or overlapping results by `traceId`.

## Page summary statistics

```http
GET /console/enterprises/{enterpriseId}/observability/trace-stats
```

Query parameters:

- `range.start`
- `range.end`
- Preserve the captured organization-scope parameters from the list request; remove only `page` and `pageSize` before requesting statistics.

The same 7-day span restriction applies. Observed fields:

- `conversations.value`
- `errors.value`
- `credits.value`
- `p50LatencyMs.value`
- `p90LatencyMs.value`
- `p99LatencyMs.value`
- `ttftP50Ms.value`
- `ttftP90Ms.value`
- `ttftP99Ms.value`

Aggregate only additive values such as conversations, errors, and credits across segments. Do not combine percentiles arithmetically.

## Record fields

| Field | Meaning |
|---|---|
| `traceId` | Unique single-turn conversation/trace ID; use for deduplication |
| `sessionId` | Task-session ID |
| `name` | Trace name when supplied |
| `input`, `output` | List-record content or previews; not guaranteed full payloads |
| `startTimeMs`, `endTimeMs` | Start/end timestamps in milliseconds |
| `durationMs` | Single-turn duration in milliseconds |
| `ttftMs` | Time to first token in milliseconds |
| `status` | Response status, such as `success` |
| `userId`, `userName` | User identifiers; nicknames can be blank |
| `agentScene`, `productScene`, `taskScene` | Scene classifications |
| `eventCount` | Event count |
| `credits` | Detail credit field; may be zero even when page credits are nonzero |
| `llmCallCount` | Detail model-call field; may be unavailable through zero values |
| `toolCallCount` | Detail tool-call field; may be unavailable through zero values |
| `toolErrorCount` | Detail tool-error field; may be unavailable through zero values |
| `inputIo`, `outputIo` | IO metadata and content |
| `modelName` | Model name when supplied |

## Common errors

| Message | Resolution |
|---|---|
| `10001:range exceeds query span limit of 7 days` | Split both list and stats requests into ranges of at most 7 days |
| `10001:pageSize exceeds limit 100` | Set `pageSize=100` |
| HTTP 401 | Restore the authenticated page session and recapture headers |
| Empty captured headers | Click the page's search button after attaching the extension, then listen for `/observability/traces?` |

## Security

- Keep authorization headers, cookies, and extension tokens in memory or process-local environment variables only.
- Do not include organization IDs, tokens, or user credentials in reusable skill resources.
- Treat exported input/output text as confidential enterprise data.

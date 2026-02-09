# Architecture

> Technical architecture, design decisions, and system internals

## System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Slack User                           │
└──────────────────────────┬──────────────────────────────────┘
                           │ Question
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Slack Bot (Socket Mode)                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  handlers.py - Extract question + thread context     │   │
│  └──────────────────┬───────────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                       RAG Engine                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  engine.py - Orchestrate pipeline                    │   │
│  └──────────────────┬───────────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
┌──────────────────┐    ┌──────────────────────────┐
│ Get MCP Tools    │    │  generator.py            │
│ (alation_client) │    │  Invoke Claude + Tools   │
└──────────────────┘    └──────────┬───────────────┘
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │   AWS Bedrock       │
                        │   Claude 3 Sonnet   │
                        └──────────┬──────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │                              │
              Tool Request                    Final Answer
                    │                              │
                    ▼                              ▼
      ┌──────────────────────────┐         ┌────────────┐
      │  Alation MCP Server      │         │   Return   │
      │  (alation_server.py)     │         │  to User   │
      └──────────┬───────────────┘         └────────────┘
                 │
                 ▼
      ┌──────────────────────────┐
      │  Alation API Adapter     │
      │  (alation_adapter.py)    │
      │  - Caching (5-min TTL)   │
      │  - Retry Logic           │
      │  - Error Handling        │
      └──────────┬───────────────┘
                 │ HTTPS + API Token
                 ▼
      ┌──────────────────────────┐
      │   Alation REST API       │
      │   Enterprise Catalog     │
      └──────────────────────────┘
```

## Process Lifecycle

1. **Startup**: MCP server starts on port 8000 → Slack Socket Mode connects
2. **Message Processing**: User message → Handler extracts question → RAG Engine invoked
3. **Tool Execution Loop**: Claude requests tool → MCP client calls server → Alation API queried → Result returned to Claude → Repeat until final answer
4. **Response Delivery**: Answer posted to Slack thread with governance warnings
5. **Shutdown**: MCP subprocess terminated → Connections closed

---

## Design Decisions

### Why Alation as Single Source of Truth?
- Enterprise-grade metadata catalog with governance
- Rich metadata: ownership, lineage, certification, classifications
- Access control enforced at the source
- No data duplication or drift

### Why No Vector Database?
- Queries live Alation metadata directly (always fresh)
- Simpler architecture with fewer dependencies
- Alation catalog is structured, not unstructured documents
- Governance metadata (PII tags, ownership) can't be meaningfully embedded

### Why MCP (Model Context Protocol)?
- Standardized protocol for tool execution
- Dynamic tool discovery
- Clean separation between bot and data layer
- Easy to add new tools without modifying core logic

### Why Socket Mode?
- No public endpoint required
- Works behind firewalls
- Real-time bidirectional communication
- Suitable for enterprise environments

### Why Explicit "Unknown" Values?
- No hallucination of metadata
- Transparency about data quality
- Encourages users to improve Alation catalog
- Compliance and audit trail integrity

---

## Error Handling (4 Layers)

| Layer | Component | Strategy |
|-------|-----------|----------|
| **1** | Alation Adapter | HTTP retries with exponential backoff. 404/403 → return None. 5xx → retry 3 times |
| **2** | MCP Server | None from adapter → "Error: Not found". Exception → "Error: {message}" |
| **3** | Generator | Tool errors passed to Claude in context. Claude explains naturally |
| **4** | Slack Handler | Unhandled exceptions → friendly error message. Full error logged |

---

## Security

| Aspect | Implementation |
|--------|----------------|
| **API Token** | Stored in `.env` (never committed), rotation recommended quarterly |
| **Permissions** | Token inherits user permissions (least privilege) |
| **Operations** | All Alation API calls are read-only GET requests |
| **Access Control** | Enforced by Alation - bot only sees what user can access |
| **Audit Trail** | All API calls and tool executions logged |

---

## Performance

### Caching
- **TTL**: 5 minutes (configurable in `alation_adapter.py`)
- **Scope**: Process-level (not shared across instances)
- **Impact**: Reduces API load by ~80% for repeated queries
- **Response times**: Warm cache <100ms, cold cache 500-2000ms

### Scalability
- Stateless design allows horizontal scaling
- MCP server can be externalized for multi-bot setup
- Consider Redis for shared cache across instances

---

## Monitoring Recommendations

### Key Metrics
- Tool execution success/failure rate
- Alation API response times
- Cache hit/miss rates
- Slack message handling latency

### Alerting
- MCP server crashes
- Alation API failure rate > 10%
- Slack connection drops
- Token expiration warnings

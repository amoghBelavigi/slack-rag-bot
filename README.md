# MCP-based Metadata Assistant for Slack

A Slack bot that provides real-time access to your Alation enterprise metadata catalog using the Model Context Protocol (MCP) and AWS Bedrock.

##  Overview

This bot integrates with Slack via Socket Mode and uses a specialized MCP server to fetch live metadata from Alation. It provides comprehensive data governance information including table descriptions, ownership, lineage, and data classifications.

### Key Features
- **Live Alation Queries**: Fetch real-time metadata directly from your Alation enterprise catalog
- **Governance-Aware**: Access ownership, stewardship, certification, and trust status
- **Data Classification**: Identify PII, PHI, and FINANCIAL data automatically
- **Lineage Tracking**: Understand upstream sources and downstream dependencies
- **MCP Architecture**: Uses Model Context Protocol to bridge the LLM with Alation
- **LLM Integration**: Uses AWS Bedrock (Claude 3) for natural language reasoning and tool use
- **Slack Socket Mode**: Secure connection without needing public endpoints or webhooks
- **Production-Ready**: No local database or vector store required - Alation is the single source of truth

##  Prerequisites

- Python 3.10+
- Alation instance with API access
- AWS Account with Bedrock access
- Slack App with Socket Mode enabled

##  Setup & Configuration

### 1. Environment Variables
Create a `.env` file in the root directory:

```env
# Alation Configuration
ALATION_BASE_URL=https://your-company.alation.com
ALATION_API_TOKEN=your_api_token_here
ALATION_USER_ID=your_user_id  # Optional

# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_SIGNING_SECRET=...

# AWS (for Bedrock only)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-west-2
```

### 2. Get Alation API Token

1. Log into your Alation instance
2. Navigate to **User Settings** → **API Access Tokens**
3. Click **Create Token**
4. Copy the token and add to `.env` as `ALATION_API_TOKEN`

### 3. Installation
```bash
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# Unix/macOS
source venv/bin/activate

pip install -r requirements.txt
```

##  Running the Bot

For detailed setup and usage, see [docs/DOCUMENTATION.md](./docs/DOCUMENTATION.md).

```bash
python -m app.socket_mode
```

This command starts both the Slack bot and the embedded Alation MCP server automatically.

## 💬 Usage Examples

Ask your bot questions like:

### Metadata Discovery
- "What data sources are available?"
- "Show me schemas in the production Snowflake database"
- "List all tables in the analytics schema"

### Table Information
- "Tell me about the customers table"
- "What columns are in the orders table?"
- "Who owns the customer_360 table?"

### Governance & Compliance
- "Which tables contain PII?"
- "Is the customers table certified?"
- "Show me all FINANCIAL data classifications"

### Data Lineage
- "Where does the customer data come from?"
- "What tables use the orders table?"
- "Show me the lineage for customer_summary"

##  Project Structure

```
slack-rag-bot/
├── app/
│   ├── __init__.py                # Package initialization
│   ├── main.py                    # FastAPI app (HTTP mode)
│   ├── socket_mode.py             # Main entry point (Socket Mode)
│   ├── core/
│   │   └── config.py              # Configuration and initialization
│   ├── models/
│   │   └── schemas.py             # Pydantic data models
│   ├── services/rag/
│   │   ├── alation_adapter.py     # Alation REST API adapter
│   │   ├── alation_server.py      # MCP server with 6 tools
│   │   ├── alation_client.py      # SSE client for MCP
│   │   ├── engine.py              # RAG orchestration
│   │   ├── generator.py           # LLM generation with tool use
│   │   └── prompts.py             # Governance-aware prompts
│   └── slack/
│       ├── handlers.py            # Slack event handlers
│       └── events.py              # HTTP webhook routes
├── docs/
│   └── DOCUMENTATION.md           # Complete setup, usage & development guide
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment template
├── README.md                      # This file
└── ARCHITECTURE.md                # Technical architecture
```

##  Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/), [Slack Bolt for Python](https://slack.dev/bolt-python/)
- **LLM**: [AWS Bedrock (Claude 3)](https://aws.amazon.com/bedrock/)
- **Metadata Catalog**: [Alation](https://www.alation.com/)
- **Protocol**: [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- **HTTP Client**: [Requests](https://requests.readthedocs.io/) for Alation API

##  MCP Tools

The Alation MCP server exposes 6 tools to the LLM:

1. **list_data_sources** - List all accessible data sources
2. **list_schemas** - List schemas in a data source
3. **list_tables** - List tables with row counts and popularity
4. **get_table_metadata** - Get ownership, certification, description
5. **get_column_metadata** - Get column types and classifications
6. **get_lineage** - Get upstream/downstream dependencies

##  Documentation

- **[docs/DOCUMENTATION.md](./docs/DOCUMENTATION.md)** - Complete setup, usage, and development guide
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - Technical architecture overview

##  Security & Governance

- **Read-Only**: All operations are read-only, no data modifications
- **User Context**: Respects Alation's access control policies
- **No Hallucination**: Returns "unknown" for missing data instead of guessing
- **Audit Trail**: All API calls logged for compliance
- **Data Classification**: Automatically identifies sensitive data (PII, PHI, FINANCIAL)

##  Troubleshooting

See [docs/DOCUMENTATION.md](./docs/DOCUMENTATION.md#troubleshooting) for common issues and solutions.

### Quick Checks
- Verify Alation API token is valid
- Check MCP server is running on port 8000
- Ensure Slack tokens are configured correctly
- Verify AWS Bedrock access in your region

Internal use only. Proprietary.

---

**Note**: This bot uses Alation as the single source of truth for all metadata. No secondary catalogs or data dumps are used.

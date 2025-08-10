# Model Context Protocol (MCP) Integration with Supsrc

## Model Context Protocol (MCP) Technical Details

MCP is an open protocol that standardizes how AI assistants connect with external data sources and tools. Here's a technical breakdown:

### Core Architecture

1. **Protocol Structure**:
   - JSON-RPC 2.0 based communication
   - Transport-agnostic (stdio, HTTP, WebSocket)
   - Request/response + server-initiated notifications
   - Bidirectional communication channel

2. **Key Components**:
   - **MCP Host**: The AI application (like Claude)
   - **MCP Server**: External tool/data provider
   - **Resources**: Read-only data sources (files, APIs, databases)
   - **Tools**: Executable functions with inputs/outputs
   - **Prompts**: Reusable prompt templates

3. **Message Types**:
   ```json
   // Tool definition
   {
     "name": "search_code",
     "description": "Search for code patterns",
     "inputSchema": {
       "type": "object",
       "properties": {
         "pattern": {"type": "string"},
         "path": {"type": "string"}
       }
     }
   }
   ```

## How MCP Could Work with Supsrc

Here's how you could integrate MCP with supsrc to create a powerful development assistant:

### 1. Supsrc as an MCP Server

Create `supsrc-mcp` that exposes supsrc functionality to AI assistants:

```python
# supsrc/mcp/server.py
class SupsrcMCPServer:
    """MCP server exposing supsrc capabilities"""
    
    async def handle_initialize(self, params):
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {"subscribe": True},
                "prompts": {}
            },
            "serverInfo": {
                "name": "supsrc-mcp",
                "version": "0.1.0"
            }
        }
    
    # Exposed Tools
    tools = [
        {
            "name": "supsrc_status",
            "description": "Get status of monitored repositories",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string", "description": "Optional repo ID"}
                }
            }
        },
        {
            "name": "supsrc_commit",
            "description": "Trigger commit for a repository",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string"},
                    "message": {"type": "string"}
                },
                "required": ["repo_id"]
            }
        },
        {
            "name": "supsrc_pause",
            "description": "Pause/resume monitoring",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["pause", "resume"]}
                }
            }
        }
    ]
    
    # Exposed Resources
    resources = [
        {
            "uri": "supsrc://logs",
            "name": "Supsrc Logs",
            "description": "Real-time monitoring logs",
            "mimeType": "application/json"
        },
        {
            "uri": "supsrc://config",
            "name": "Supsrc Configuration",
            "description": "Current supsrc configuration",
            "mimeType": "text/toml"
        },
        {
            "uri": "supsrc://repos/{repo_id}/history",
            "name": "Repository History",
            "description": "Commit history for a repository"
        }
    ]
```

### 2. Integration Architecture

```python
# supsrc/mcp/integration.py
class SupsrcMCPIntegration:
    def __init__(self, orchestrator: WatchOrchestrator):
        self.orchestrator = orchestrator
        self.mcp_server = SupsrcMCPServer(self)
        
    async def execute_tool(self, tool_name: str, args: dict):
        """Execute MCP tool requests"""
        if tool_name == "supsrc_status":
            return await self.get_status(args.get("repo_id"))
        elif tool_name == "supsrc_commit":
            return await self.trigger_commit(args["repo_id"], args.get("message"))
        elif tool_name == "supsrc_pause":
            return await self.control_monitoring(args["action"])
    
    async def get_resource(self, uri: str):
        """Fetch MCP resource data"""
        if uri == "supsrc://logs":
            return self.get_recent_logs()
        elif uri == "supsrc://config":
            return self.get_config_toml()
        elif uri.startswith("supsrc://repos/"):
            repo_id = uri.split("/")[3]
            return self.get_repo_history(repo_id)
```

### 3. Stdio Transport Implementation

```python
# supsrc/mcp/stdio_transport.py
import sys
import json
import asyncio

class StdioMCPTransport:
    """Handle MCP over stdio for Claude Desktop integration"""
    
    async def run(self):
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: protocol, sys.stdin
        )
        
        while True:
            line = await reader.readline()
            if not line:
                break
                
            try:
                message = json.loads(line.decode())
                response = await self.handle_message(message)
                
                # Write response
                sys.stdout.write(json.dumps(response) + '\n')
                sys.stdout.flush()
            except Exception as e:
                self.send_error(e)
```

### 4. MCP Configuration for Claude Desktop

```json
{
  "mcpServers": {
    "supsrc": {
      "command": "supsrc",
      "args": ["mcp", "serve"],
      "env": {
        "SUPSRC_CONFIG": "~/.config/supsrc/config.toml"
      }
    }
  }
}
```

### 5. Advanced Features

**A. Real-time Notifications**:
```python
async def send_notification(self, event: MonitoredEvent):
    """Send real-time notifications to AI"""
    await self.mcp_transport.send_notification({
        "method": "notifications/resources/updated",
        "params": {
            "uri": f"supsrc://repos/{event.repo_id}/status"
        }
    })
```

**B. Commit Cook Integration**:
```python
{
    "name": "generate_commit_message",
    "description": "Generate AI commit message from diff",
    "inputSchema": {
        "type": "object",
        "properties": {
            "repo_id": {"type": "string"},
            "diff": {"type": "string"},
            "context": {"type": "object"}
        }
    }
}
```

**C. Prompts for Common Tasks**:
```python
prompts = [
    {
        "name": "analyze_changes",
        "description": "Analyze uncommitted changes",
        "arguments": [
            {
                "name": "repo_id",
                "description": "Repository to analyze",
                "required": true
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": "Analyze changes in {{repo_id}} and suggest: 1) Commit message 2) Any issues 3) Missing files"
            }
        ]
    }
]
```

## Benefits of MCP + Supsrc

1. **AI-Assisted Development**: Claude can monitor your repos, suggest commits, and handle routine tasks
2. **Smart Automation**: AI can decide when to commit based on code analysis
3. **Enhanced Commit Messages**: AI generates meaningful commit messages from diffs
4. **Proactive Assistance**: AI can warn about potential issues before commits
5. **Natural Language Control**: "Hey Claude, pause monitoring while I refactor"

## Implementation Roadmap

### Phase 1: Basic MCP server with status/control tools
### Phase 2: Resource streaming for real-time monitoring
### Phase 3: Commit Cook integration for AI-powered commits
### Phase 4: Advanced prompts and workflow automation
### Phase 5: Advanced Integration Features

**A. Contextual Code Understanding**:
```python
class SupsrcMCPContext:
    """Provide rich context to AI about repository state"""
    
    async def get_context_for_repo(self, repo_id: str):
        return {
            "recent_commits": await self.get_commit_history(repo_id, limit=10),
            "current_diff": await self.get_uncommitted_changes(repo_id),
            "file_tree": await self.get_file_structure(repo_id),
            "dependencies": await self.analyze_dependencies(repo_id),
            "test_status": await self.get_test_results(repo_id),
            "lint_issues": await self.get_lint_warnings(repo_id)
        }
```

**B. Intelligent Monitoring Rules**:
```python
{
    "name": "create_monitoring_rule",
    "description": "Create AI-suggested monitoring rule",
    "inputSchema": {
        "type": "object",
        "properties": {
            "repo_id": {"type": "string"},
            "rule_type": {"type": "string"},
            "ai_suggestions": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "threshold": {"type": "number"},
                    "actions": {"type": "array"}
                }
            }
        }
    }
}
```

## Real-World Usage Scenarios

### 1. AI-Driven Development Workflow
```bash
# Start supsrc with MCP server
supsrc mcp serve --config ~/.supsrc/config.toml

# In Claude Desktop:
"Monitor my Python project and automatically commit when:
- All tests pass
- Type hints are complete
- No linting errors
Use semantic commit messages based on the changes"
```

### 2. Intelligent Commit Grouping
The AI can analyze changes and suggest logical commit groupings:

```python
async def suggest_commit_groups(self, repo_id: str):
    """AI analyzes changes and suggests how to group them"""
    changes = await self.get_unstaged_changes(repo_id)
    
    # AI receives context about:
    # - File relationships
    # - Change types (refactor, feature, fix)
    # - Dependencies between changes
    
    return {
        "suggestions": [
            {
                "files": ["src/api/auth.py", "tests/test_auth.py"],
                "message": "feat: add OAuth2 authentication support",
                "reasoning": "Auth implementation and tests should be committed together"
            },
            {
                "files": ["README.md", "docs/setup.md"],
                "message": "docs: update installation instructions",
                "reasoning": "Documentation changes are independent"
            }
        ]
    }
```

### 3. Proactive Code Quality Monitoring
```python
class QualityMonitor:
    """MCP resource that streams code quality metrics"""
    
    async def stream_metrics(self, repo_id: str):
        while True:
            metrics = {
                "complexity": await self.calculate_complexity(repo_id),
                "coverage": await self.get_test_coverage(repo_id),
                "tech_debt": await self.estimate_tech_debt(repo_id),
                "security_issues": await self.scan_security(repo_id)
            }
            
            # AI can suggest refactoring when metrics degrade
            if metrics["complexity"] > threshold:
                await self.notify_ai({
                    "alert": "complexity_increase",
                    "files": metrics["complex_files"],
                    "suggestion": "Consider refactoring these methods"
                })
            
            yield metrics
            await asyncio.sleep(30)
```

## Security and Privacy Considerations

```python
class SupsrcMCPSecurity:
    """Security layer for MCP integration"""
    
    def __init__(self):
        self.allowed_operations = set()
        self.sensitive_paths = set()
        
    async def validate_request(self, tool: str, args: dict):
        """Validate MCP requests before execution"""
        # Check permissions
        if tool == "supsrc_commit":
            # Require explicit user confirmation for commits
            if not await self.get_user_confirmation(f"Commit to {args['repo_id']}?"):
                raise PermissionError("User declined commit")
        
        # Filter sensitive data
        if "credentials" in args:
            args["credentials"] = "[REDACTED]"
            
        return True
    
    def filter_response(self, data: dict):
        """Remove sensitive data from responses"""
        # Remove API keys, tokens, etc.
        return self.redact_sensitive_data(data)
```

## Integration with Existing Supsrc Features

### 1. Enhanced TUI with AI Suggestions
```python
class AIEnhancedTUI(SupsrcTuiApp):
    """TUI with integrated AI suggestions"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ai_suggestions = []
        
    def compose(self):
        yield Header()
        with Container():
            yield DataTable(id="repo-table")
            yield Panel(id="ai-suggestions", title="AI Insights")
            
    async def update_ai_suggestions(self):
        """Fetch and display AI suggestions"""
        for repo_id, state in self.repo_states.items():
            if state.has_changes:
                suggestion = await self.mcp_client.get_suggestion(repo_id)
                self.ai_suggestions.append(suggestion)
```

### 2. MCP-Powered CLI Commands
```python
@cli.command()
@click.option('--ai-assist', is_flag=True, help='Enable AI assistance')
def watch(config_file: Path, ai_assist: bool):
    """Run supsrc with optional AI assistance"""
    if ai_assist:
        # Start MCP server in subprocess
        mcp_process = start_mcp_server(config_file)
        
        # Connect Claude or other AI
        click.echo("AI assistance enabled. Connect your AI client to:")
        click.echo(f"  MCP endpoint: localhost:7777")
```

## Configuration Example

```toml
# ~/.supsrc/mcp-config.toml
[mcp]
enabled = true
transport = "stdio"  # or "tcp", "websocket"
port = 7777  # for network transports

[mcp.security]
require_confirmation = ["commit", "push", "config_change"]
allowed_repos = ["*"]  # or specific repo list
max_file_size = "10MB"

[mcp.ai_features]
commit_cook = true
auto_suggest = true
quality_monitoring = true
smart_grouping = true

[mcp.resources]
expose_logs = true
expose_config = false  # security consideration
expose_history = true
realtime_updates = true
```

## Future Possibilities

1. **Multi-AI Collaboration**: Multiple AI agents monitoring different aspects
2. **Learning Mode**: AI learns your commit patterns and coding style
3. **Cross-Repository Intelligence**: AI understands relationships between repos
4. **Predictive Monitoring**: AI predicts when you'll need to commit based on patterns
5. **Integration with CI/CD**: AI can trigger builds and analyze results

This MCP integration would essentially give you an AI pair programmer that:
- Understands your codebase
- Monitors changes in real-time
- Suggests improvements
- Handles routine tasks
- Learns from your patterns

The key is that MCP provides the protocol for this deep integration, while supsrc provides the monitoring and action capabilities.
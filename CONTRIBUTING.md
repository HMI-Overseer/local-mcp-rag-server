# Contributing to Local MCP RAG Server

Thank you for your interest in contributing to this project! This guide will help you get started with development and testing.

## Prerequisites

- **Python 3.12+** (developed and tested with Python 3.12)
- **LM Studio** installed and running locally
- **Git** for version control
- An **embedding model** loaded in LM Studio (recommended: `nomic-embed-text-v1.5`)

## First-Time Setup

### 1. Clone the Repository

```bash
git clone https://github.com/HMI-Overseer/local-mcp-rag-server.git
cd local-mcp-rag-server
```

### 2. Create Virtual Environment

**Windows:**
```bash
py -3.12 -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3.12 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy the example configuration file and customize it:

```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```

Edit `.env` to match your local setup. Key settings to verify:

```ini
# Ensure this matches your LM Studio server
LM_STUDIO_BASE_URL=http://localhost:1234/v1

# Set to the embedding model loaded in LM Studio
EMBEDDING_MODEL=nomic-embed-text-v1.5

# Path to your documents (can be relative or absolute)
DOCUMENTS_DIR=documents
```

### 5. Verify LM Studio Connection

1. Start LM Studio
2. Enable the local server (⚙️ → Local Server → Start Server)
3. Load an embedding model (recommended: `nomic-embed-text-v1.5`)
4. Test the connection:

```bash
python -c "from rag.embedder import get_embedder; e = get_embedder(); print('Connection successful:', e.embed('test')[:5])"
```

If successful, you'll see the first 5 dimensions of the test embedding.

### 6. Index Sample Documents

The repository includes example documents in the `documents/` directory:

```bash
python ingest.py
```

You should see output indicating successful indexing:
```
OK: Your knowledge base is ready.
```

### 7. Test the MCP Server

**Option A: Test with MCP client (LM Studio)**

Configure LM Studio to use the MCP server by editing your MCP settings file:

**Windows:** `%APPDATA%\LM Studio\mcp_settings.json`
**macOS:** `~/Library/Application Support/LM Studio/mcp_settings.json`
**Linux:** `~/.config/LM Studio/mcp_settings.json`

Add this configuration (adjust paths to your installation):

```json
{
  "mcpServers": {
    "local-context": {
      "command": "/absolute/path/to/local-mcp-rag-server/venv/bin/python",
      "args": ["/absolute/path/to/local-mcp-rag-server/mcp_server.py"]
    }
  }
}
```

**Option B: Test manually**

```bash
python mcp_server.py
```

The server should start without errors and wait for MCP protocol messages.

## Development Workflow

### Running Tests

Run the full test suite:

```bash
python -m unittest discover tests
```

Run specific test files:

```bash
python -m unittest tests.test_chunking
python -m unittest tests.test_ingestor
python -m unittest tests.test_search_utils
python -m unittest tests.test_vectorstore_filters
```

### Code Style

This project follows standard Python conventions:

- **PEP 8** for code style
- **Type hints** for function signatures
- **Docstrings** for public functions and classes
- **LF line endings** for all Python files

### Project Structure

```
local-mcp-rag-server/
├── mcp_server.py          # MCP server entry point
├── ingest.py              # Document ingestion CLI
├── requirements.txt       # Python dependencies
├── .env                   # Local configuration (not in git)
├── .env.example          # Configuration template
├── documents/            # Example documents
├── rag/                  # Core RAG implementation
│   ├── config.py         # Configuration management
│   ├── embedder.py       # LM Studio embeddings client
│   ├── vectorstore.py    # ChromaDB interface
│   ├── ingestor.py       # Document processing
│   ├── markdown_chunker.py  # Markdown-aware chunking
│   ├── indexing.py       # Index state management
│   └── search_utils.py   # Search utilities
└── tests/                # Test suite
```

### Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, well-documented code
   - Add tests for new functionality
   - Update documentation as needed

3. **Test your changes**
   ```bash
   # Run tests
   python -m unittest discover tests
   
   # Test ingestion
   python ingest.py --reset
   
   # Test MCP server (manually or with LM Studio)
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "Description of changes"
   ```

5. **Push and create a pull request**
   ```bash
   git push origin feature/your-feature-name
   ```

## Common Tasks

### Reset the Vector Database

To completely rebuild the index:

**Windows:**
```bash
ingest_reset.bat
```

**macOS/Linux:**
```bash
./ingest_reset.sh
```

Or manually:
```bash
python ingest.py --reset
```

### Update Dependencies

```bash
pip install --upgrade -r requirements.txt
```

### Add New Dependencies

If you need to add a new package:

1. Install it: `pip install package-name`
2. Update `requirements.txt`: `pip freeze > requirements.txt`
3. Test that the project still works
4. Commit both code changes and updated `requirements.txt`

### Debug Logging

Enable verbose logging by setting in `.env`:

```ini
LOG_LEVEL=DEBUG
```

This will show detailed information about:
- Document processing
- Embedding operations
- Search queries
- Chunk metadata

## Troubleshooting

### "Cannot connect to LM Studio"

- Verify LM Studio is running
- Check that the local server is enabled
- Ensure an embedding model is loaded
- Verify `LM_STUDIO_BASE_URL` in `.env` matches LM Studio settings

### "No module named 'mcp'"

```bash
pip install -r requirements.txt
```

### Virtual environment activation issues

**Windows PowerShell:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
venv\Scripts\Activate.ps1
```

**Windows CMD:**
```cmd
venv\Scripts\activate.bat
```

### Tests fail after changing chunking settings

After modifying `CHUNK_TARGET_SIZE`, `CHUNK_MIN_SIZE`, or `CHUNKING_STRATEGY`, reset the index:

```bash
python ingest.py --reset
```

## Release Process

This project uses semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes to the API or data format
- **MINOR**: New features, backward-compatible
- **PATCH**: Bug fixes, documentation updates

Version is tracked in `mcp_server.py` at `server_version`.

## Questions or Issues?

- Check existing [GitHub Issues](https://github.com/HMI-Overseer/local-mcp-rag-server/issues)
- Create a new issue with detailed information about your problem
- Include error messages, log output, and steps to reproduce

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
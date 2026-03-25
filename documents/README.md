# Document Templates

These templates are optional examples for how to organize Markdown documents when you want better metadata and filterable search.

Nothing in this folder is required. Plain Markdown files still work without frontmatter.

## Supported Optional Frontmatter

You can place a YAML frontmatter block at the top of a Markdown file:

```md
---
title: Example Title
category: guides
tags:
  - metadata
  - filters
source_type: file
status: draft
owner: user
---
```

Recognized fields:

- `title`
- `category`
- `tags`
- `source_type`

Other fields are also kept as metadata and stored with a `meta_` prefix, for example `status` becomes `meta_status`.

## Search Filters

The `search_documents` MCP tool supports optional filters:

- `category`
- `source_type`
- `filepath_contains`
- `title_contains`
- `tags`

Example idea:

```json
{
  "query": "how does the indexing pipeline work?",
  "category": "guides",
  "tags": ["metadata", "filters"]
}
```

## Files in This Folder

- `plain_markdown_example.md`
- `metadata_frontmatter_example.md`
- `research_note_example.md`

---
name: terminal-output-md
description: Convert Python terminal output, stdout, stderr, tracebacks, and command sessions into clean Markdown notes or documentation. Use when asked to save, summarize, or rewrite terminal results from Python into a .md file.
---

# Terminal Output to Markdown

Turn raw terminal output into a markdown document that is easy to read and save.

## Workflow

1. Preserve the original command exactly when it is present.
2. Separate `stdout`, `stderr`, and tracebacks into distinct sections when possible.
3. Keep exact error text and stack traces in fenced code blocks.
4. Add a short summary only when it helps the reader understand the result.
5. If the output is long, group repeated lines and highlight the important result near the top.
6. Do not invent conclusions that are not supported by the terminal output.

## Suggested Structure

Use this order when it fits the content:

- `# Run Summary`
- `## Command`
- `## Output`
- `## Errors`
- `## Notes`
- `## Next Steps`

## Formatting Rules

- Put terminal text in fenced code blocks.
- Use bullets for observations and short takeaways.
- Keep file-ready Markdown clean and pasteable.
- If the user provides multiple runs, label them clearly and keep them in chronological order.

## Output Goal

Produce Markdown that can be saved directly as a `.md` file without extra cleanup.

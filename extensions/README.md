# ClawHub Extension Bridge

Glove can call multiple extension adapters in parallel through provider `clawhub`.

Set:

- `GLOVE_NOTIFIER_PROVIDER=clawhub` or include `clawhub` in `GLOVE_NOTIFIER_PROVIDERS`
- `GLOVE_CLAWHUB_EXTENSIONS_DIR=./extensions`
- `GLOVE_CLAWHUB_EXTENSIONS=ext1,ext2`

Each extension must live in:

- `<extensions_dir>/<extension_id>/glove-extension.json`

Manifest format:

```json
{
  "name": "my-extension",
  "notify": {
    "command": "python",
    "args": ["notify.py"]
  }
}
```

Glove sends this JSON envelope to the extension stdin:

```json
{
  "event": "notify",
  "subject": "Glove PIN Required",
  "message": "text...",
  "payload": { "request_id": "..." }
}
```

Extension should exit `0` on success and non-zero on failure.

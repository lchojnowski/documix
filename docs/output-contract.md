# DocuMix Rust implementation: output contract (default conversion path)

Scope: byte-identical output file vs. Python for the default chain (`anydoc` → `liteparse`), excluding the `- Compilation Date:` line, the version string and the `- Processing time:` line. Everything below quotes the exact Python literals; "console" means stdout/stderr text that does not enter the output file.

Source of truth (Python fallback, now under `python/`): `documix/cli.py`, `compiler.py`, `output.py`, `email_processor.py`, `textutils.py`, `config.py`, `converters/{__init__,anydoc,liteparse,archive,text}.py`, `errors.py`, `version.py`, `local_ocr.py:has_content`.

---

## 1. CLI contract

### 1.1 Invocation order in `main()` (cli.py:115-205)

1. If `argv[1] == 'benchmark'` → benchmark subcommand (before anything else, no logo). **Prototype: reject** (see 1.6).
2. `print_logo()` — the literal block (trailing spaces on lines 3-4 and a line of 57 spaces, then `    ` + newline; `print(logo)` adds a final `\n`).
3. `parser.parse_args()` — any argparse failure: usage block on **stderr** + `{prog}: error: {message}`, **exit 2**. `-h/--help`: help to stdout, exit 0. argparse `allow_abbrev=True`: unique long-option prefixes are accepted; a second positional → `error: unrecognized arguments: extra`.
4. `--version` → prints `DocuMix v{version}`, empty line, converter table (1.4), **returns (exit 0)**, even if a folder was given.
5. No `folder` → `parser.print_help()` to stdout, **exit 0**.
6. `🔍 Analyzing folder: {args.folder}` (raw argument, not absolutized).
7. `-e`: `include_extensions = [f".{ext.strip().lower()}" for ext in args.extensions.split(',')]`; prints `📋 Included extensions: {', '.join(include_extensions)}`. Quirks: `-e .txt` → `..txt` (never matches); `-e ""` is falsy → defaults; `-e "txt, MD"` → `.txt`, `.md`.
8. `-x`: `[pattern.strip() for pattern in args.exclude.split(',')]`; prints `🚫 Exclusion patterns: {', '.join(exclude_patterns)}`.
9. `--standard-format` → `force_format='standard'`; prints `📄 Forcing standard output format`.
10. `-j` given and `< 1` → `parser.error('--jobs must be at least 1')` → stderr usage + `documix: error: --jobs must be at least 1`, **exit 2** (after steps 6-9 already printed). `-j abc` → argparse error exit 2 during parse.
11. For each `fmt` in order `pdf, docx, doc, rtf, epub, office`: if `--{fmt}-converters` is non-empty: `names = [n.strip() for n in value.split(',')]`; first `name not in CONVERTER_CHOICES[fmt]` → **stdout** `Error: unknown {FMT} converter '{name}'. Valid choices: {', '.join(valid)}` then `sys.exit(1)`; otherwise prints `🔧 {FMT} converters: {', '.join(names)}`.
12. OCR: if any `--ocr-*` is given and `'tesseract'` not in the pdf list → `parser.error('OCR settings require --pdf-converters including tesseract')` exit 2. Else `validate_config` bounds → `parser.error('Invalid OCR settings; see --help for bounded values')` exit 2.
13. `anydoc_engine.require()` → on failure `_fail(error)` (1.5).
14. `print_converter_info(converter_config)` (1.4).
15. `DocumentCompiler(...)`, `compile()`; `EngineError` → `_fail(error, args.output)`.

### 1.3 Exit codes summary

| Situation | Stream / message | Exit |
|---|---|---|
| argparse error | stderr usage + `documix: error: ...` | 2 |
| `--jobs < 1`, OCR flags without tesseract, OCR out of bounds | stderr `documix: error: ...` | 2 |
| unknown converter name | stdout `Error: unknown {FMT} converter '{name}'. Valid choices: ...` | 1 |
| anydoc missing / engine crash | stdout, see 1.5; partial output removed | 1 |
| `--version`, `-h`, no folder | stdout | 0 |
| no files found | stdout `❌ No files found to process.`; **no output file is created** | 0 |
| non-recursive scan of a nonexistent/unreadable folder | Python traceback (`FileNotFoundError`) | 1 |
| recursive scan of a nonexistent folder | `os.walk` ignores errors → `❌ No files found to process.` | 0 |
| output path not writable | Python traceback | 1 |

### 1.4 `--version` and `print_converter_info`

Format: `f"  {fmt.upper():>6}: {', '.join(active) if active else '(none available)'}"`, then if any configured converter is unavailable: `f"          missing: {', '.join(missing)}"` (10 spaces). Console only.

### 1.5 Engine failure (`_fail`)

`\n❌ ERROR: anydoc engine failure: {message}` + `DocuMix requires a working anydoc installation; nothing was written.`, then `os.remove(output_file)` (errors ignored), `sys.exit(1)`.

### 1.6 Features that only the Python fallback has

| Input | Rust binary behaviour |
|---|---|
| `documix benchmark ...` | stderr `documix: error: the benchmark subcommand is not available in this build; use the Python implementation: documix-py benchmark`, **exit 3** |
| any `--{fmt}-converters` list containing a name outside `{anydoc, liteparse}` | after the `🔧 ...` line, stderr `documix: error: converter '{name}' is not available in this build (supported: anydoc, liteparse); use the Python implementation: documix-py`, **exit 3** |
| `--ocr-*` without tesseract | identical to Python: exit 2 with the same message |

Exit code 3 is unused by Python, which makes "rejected by prototype" distinguishable from "parity failure".

---

## 2. File discovery (`DocumentCompiler._scan`)

`source_path = os.path.abspath(arg)` (lexical, no symlink resolution). `is_single_file = os.path.isfile(source_path)` (follows symlinks). `include_extensions = [e.lower() for e in (cli list or DEFAULT_EXTENSIONS)]`. Exclusion patterns compiled with `re.compile`; invalid → console `WARNING: Invalid exclusion pattern: {pattern}`.

`_matches(filename)`: `ext = os.path.splitext(filename.lower())[1]`; `ext in include_extensions` and `not any(p.search(filename))` on the **basename** (original case).

`os.path.splitext`: extension from the last `.` provided a non-dot char precedes it in the basename (`.bashrc` → `''`, `.hidden.md` → `.md`, `archive.tar.gz` → `.gz`, `trailing.` → `.`, `a..b` → `.b`).

Algorithm: single file → `[source_path]` if it matches; recursive → `os.walk` top-down with `dirs.sort()`, `rel_root = relpath(root, source_dir)`, hidden = any component of rel_root starts with `.`; non-hidden non-root dirs emit `f"{rel_root}/"`; files `sorted(names)` filtered by `_matches`; files appended (unless single-file) and `f"  {relpath(path, source_dir)}"` when not hidden. Non-recursive → `sorted(os.listdir)`, `isfile` + `_matches`, structure `f"  {name}"`. Return `sorted(files), structure`.

- Hidden rule applies to directory components only; dotfiles with a matching extension are included.
- `os.walk` classifies with `is_dir()` (follows symlinks); symlinked dirs appear in `dirs` but are not descended. Recursive mode does not check `isfile` (broken symlinks are processed → read failure placeholder).
- Single-file source: structure built from the parent directory.
- `sorted(files)` by code point == UTF-8 byte order. `.` < `/`.

`process_file`: `fmt = FORMAT_OF_EXTENSION.get(ext)` → chain; `.zip` → `extract_zip`; `.eml` → `process_email`; else text read (UTF-8 `errors='replace'`, universal newlines, BOM retained) → `(text, "direct_read")`; failure → `("[Failed to read file: {basename}]", "failed")`.

---

## 3. Output file format, standard mode — see `documix/output.py` (literals copied into `src/output.rs`).

- Header: `## File: {rel_path} (converted with {method})\n`; `fenced = (method == 'direct_read')`.
- Not fenced: content, `\n` if missing, `\n`. Fenced: ```` ````lang\n```` or ```` ````\n````, content, `\n````\n\n`.

---

## 4. Single-email mode

### 4.1 Mode detection
`single_email` iff `len(files) == 1 and files[0].lower().endswith('.eml')` (including a directory containing exactly one `.eml`), unless `--standard-format`.

### 4.2 `EmailProcessor`
- Attachments dir auto-detect: first existing dir among `attachments`, `Attachments`, `attachment`, `Attachment` next to the eml.
- Header semantics (policy.default): all `\r`/`\n` removed (continuation whitespace kept); RFC 2047 decoded; structured headers **re-rendered**: address headers → `display_name <addr>` / `addr` / `Group: a, b;` (display names quoted when they contain specials `()<>@,:;.\"[]`), comments dropped; `Date` → `email.utils.format_datetime(parsedate_to_datetime(value))` (`Wed, 01 Jan 2025 12:00:00 +0000`, weekday recomputed, `-0000` for naive; unparseable → raw unfolded); `Message-ID` → `<id>`. Missing header → `''`.
- `_check_attachments_folder`: `os.listdir` (**raw readdir order**, includes dotfiles), regular files only.
- `process_attachments`: folder → `'Local folder'`; else extract → `'Extracted from email'`.
- `extract_attachments_from_email`: walk pre-order; `'attachment' in Content-Disposition` (case-sensitive substring on the rendered value incl. parameters); `filename = get_filename()` (CD filename, else CT name; RFC 2231/2047 decoded); dir = attachments_dir or `join(dirname(eml), 'attachments')`; bytes written binary, str (text parts) written as UTF-8; size = getsize. Side effect persists on disk.
- `get_email_body`: skip attachment parts; `text/plain` → last wins; `text/html` → `h2t.handle(...)` last wins; exceptions per part → fallback; return html if truthy else plain. Body line endings preserved (CRLF stays).

### 4.3 `compile_output()` → lines joined by `\n`:
`# Email Document: {subject or 'No Subject'}`, `Generated by DocuMix on {now}`, ``, `## Email Metadata`, optional `- **From**: `, `- **To**: `, `- **CC**: `, `- **Date**: `, `- **Subject**: `, `- **Message-ID**: `, `- **Attachments Source**: {src} ({n} files found)`, ``, `## Email Content`, ``, `{body or "[No email body content found]"}`, ``, then `## Attachments ({n} files)`, ``, `Total size: {format_size(sum)}`, `` — or `## Attachments`, ``, `No attachments found.`, ``.

### 4.4 `process_email` → `(content, method, email_info)`
`email_info` built **before** `process_attachments()` so `email_info['attachments_source']` is always `''` (the `- Attachments source:` line is never written). If attachments: `content += "\n"`; per attachment `### {i}. {name} ({size})\n\n`; `ext in include_extensions and ext != '.eml'` → `process_file`; not fenced → `{c}\n\n`; fenced → three-backtick fence with language; else `[Attachment type '{ext}' not supported for extraction]\n\n`. Then `\n---\n## Statistics\n`, `- Total attachments: {n}\n`, optional `- Total size: {size}\n`, `- Processing time: {elapsed:.2f}s\n`. Method `email+local_folder` / `email+extracted_from_email`.

### 4.5 `write_single_email` — literals copied into `src/output.rs`; defaults `No Subject`/`Unknown` only when email_info is empty (parse failure).

### 4.6 helpers
`estimate_tokens`, `format_size` (`{:.1f}` round-half-even on exact value), `{:,}`.

---

## 5. ZIP handling
`tempfile.mkdtemp()`; `extractall`; `file_list` = all files under the temp dir (relative, sorted); text: `# ZIP Archive Contents: {name}\n\n`, `## Files in archive:\n\n`, `- {rel}\n`…, `\n## Extracted file contents:\n\n`, per includable member `### File: {rel}\n\n` + raw `{content}\n\n` or three-backtick fence. `conversion_method = "zip_extract+" + "+".join(set(methods))` — **set order is hash-randomised in Python**; the port sorts; the harness canonicalises. Errors: `[Error: {name} is not a valid ZIP file]` / `failed-bad_zip`; other → `[Error processing ZIP file: {e}]` / `failed-exception`.

---

## 6. Engines
Chain: first text accepted; exhausted → `[Failed to convert {label} file: {basename}]`, labels `PDF`, `DOCX`, `DOC`, `RTF`, `EPUB`, office → upper-cased extension. `has_content`: not Python-whitespace and category not Cc/Cf. anydoc: `ConvertError`/`OSError` decline; panic → EngineError; empty → decline. `--office-require-text-only`: for OFFICE_EXTENSIONS, `to_document` assets or `has_embedded_media` (`.rels` `Type="…/image"`, `Pictures/`, `/media/`) → `[Failed to convert {LABEL} file: unassessed_media]` terminal; else `to_markdown_bytes(data, format_from_path)`.

---

## 7. Concurrency
Results written strictly in sorted order; `.eml` inline on the main thread; EngineError removes the partial output and exits 1.

---

## 8. Parity test plan
Normalise `^- Compilation Date: .*$`, `^Generated by DocuMix v.* on …$`, `^Generated by DocuMix on …$`, `^- Processing time: …$`, sort the `+`-parts of `zip_extract+…`. Copy fixtures to fresh temp dirs per run (attachment extraction mutates the tree); always write `-o` outside the source dir. Edge cases: lexical paths, code-point sort, lossy UTF-8 + universal newlines, code-point lengths, Python whitespace set, Unicode version for Cc/Cf, `-x` regex dialect, html2text, header re-rendering, `'attachment'` substring quirk, raw readdir order of `attachments/`, persistent extraction, ZIP cp437 names / symlink members / set order, nonexistent folder exit codes, `Total characters` vs processing-time length, local time.

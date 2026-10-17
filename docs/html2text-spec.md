# html2text rendering spec for the Rust port

This covers html2text 2025.4.15 running on Python 3.13.12, with `body_width=0`, plus the `protect_links=True` variant. The four package files were read in full, and also the stdlib `html/parser.py` from 3.13.12, which decides how input is split into pieces before html2text sees it. About 200 inputs were run through the installed library. Every exact output string below, including those in section 10, was produced by the library.

**Files**
- Package: `.venv/lib/python3.13/site-packages/html2text/` — `__init__.py` (1028 lines), `config.py`, `utils.py`, `elements.py`
- Tokenizer: CPython 3.13 `html/parser.py`
- Callers: `documix/email_processor.py` (lines 23-26 and 155) and `documix/textutils.py` (lines 97-102, which also applies `.strip()` to the result)

**Things a port is most likely to get wrong**
1. **Python errors that the caller turns into a fallback.**
   - A numeric character reference directly followed by a letter a–f (e.g. `&#39abc`, `&#160Every`) raises `ValueError`. So does `<ol start>` with no value (`AssertionError`).
   - `get_email_body` catches the exception, prints a warning and uses the plain-text part instead.
2. **The email converter reuses one instance across `handle()` calls.** Most state carries over into the next HTML part. Details are in section 9.
3. **Text is handled in pieces, not as one string.** Python's parser splits text at every tag, comment, `&` and lone `<`. Whitespace collapsing, Markdown escaping, emphasis stripping and auto-link matching all work on each piece separately. Merging the pieces first gives different output.
4. **Output is not normalised.** Trailing spaces, extra blank lines and leading spaces are all kept, because wrapping is skipped when `body_width` is 0.

---

## 1. Settings in effect

The constructor is at `__init__.py:54-91`; defaults are in `config.py:4-169`.

| Setting | Value | Effect here |
|---|---|---|
| `body_width` | 0 | `optwrap` returns the text unchanged (`:961-962`). `wrap_links`, `wrap_list_items` and `wrap_tables` (True/False/False) are never read. |
| `unicode_snob` | False | Some entities become ASCII (section 4); `&nbsp;` becomes `" "` (`:170-174`). |
| `escape_snob` | False | Only the limited escaping in section 5 applies. |
| `inline_links` | True | Links are written `[text](url)`. Reference links are never produced, so `links_each_paragraph=False` has no effect. |
| `skip_internal_links` | True | `href` starting with `#` is not a link. |
| `protect_links` | False (True in the table path) | When True, the URL is written as `<url>`. |
| `use_automatic_links` | True | Link text equal to an absolute `href` is written `<url>`. |
| `ignore_links`, `ignore_images`, `ignore_mailto_links` | False | |
| `ignore_emphasis` | False | |
| `ul_item_mark`, `emphasis_mark`, `strong_mark` | `"*"`, `"_"`, `"**"` | Hard-coded at `:75-77`. |
| `open_quote`, `close_quote` | `"` and `"` | |
| `images_to_alt`, `images_as_html`, `images_with_size` | False | `default_image_alt` is `""`. |
| `ignore_tables`, `bypass_tables`, `pad_tables` | False | |
| `single_line_break` | False | A paragraph break is 2 newlines. |
| `mark_code`, `backquote_code_style` | False | `<pre>` content is indented 4 spaces. |
| `google_doc` | False | All style, class and CSS logic is inactive. |
| `hide_strikethrough` | False | Only used in google_doc mode. |
| `include_sup_sub` | False | `<sup>` and `<sub>` are ignored. |
| `tag_callback` | None | |
| `baseurl` | `""` | `urljoin("", x)` returns `x` unchanged, so URLs are never normalised. |
| `decode_errors` | — | Not used by the class (CLI only). |

---

## 2. Output engine

### State (`:54-139`)
- **Flags and counters:** `quiet`, `p_p` (pending newlines: 0, 1 or 2), `start`, `space`, `br_toggle`, `lastWasNL`, `lastWasList`, `blockquote`, `pre`, `startpre`, `code`, `quote`
- **Links:** `astack`, `maybe_automatic_link`, `empty_link`
- **Lists:** `list` (stack of `{name, num}`), `list_code_indent`, `pre_indent`
- **Emphasis:** `stressed`, `preceding_stressed`, `preceding_data`, `current_tag`, `inheader`
- **Tables:** `table_start`, `split_next_td`, `td_count`
- **Abbreviations:** `abbr_title`, `abbr_data`, `abbr_list` (keeps insertion order)
- **Output:** `outtextlist`, a list of strings in the order they were written

### `out(s)` (`outtextf`, `:157-160`)
Appends `s`. If `s` is non-empty, sets `lastWasNL = s ends with "\n"`.

### Line-break helpers (`:740-752`)
- `pbr()`: if `p_p == 0`, set `p_p = 1`.
- `p()`: `p_p = 2`.
- `soft_br()`: `pbr()`, then `br_toggle = "  "`.

### `o(data, puredata=false, force=None|True|"end")` (`:754-870`)
Every write goes through this function. Steps, in order:
```
1  if abbr_data != None: abbr_data += data          // raw input, recorded even when quiet
2  if quiet != 0: return                              // a NEGATIVE quiet also hides everything
3  if puredata && !pre:
       data = replace each run of Unicode whitespace with " "   // `\s+`; set listed below
       if data starts with " ": space = true; data = data[1..]
4  if data == "" && force is None: return
5  if startpre && !data.starts_with("\n") && !data.starts_with("\r\n"): data = "\n" + data
6  bq = ">" * blockquote
   if blockquote > 0 && !(force && data != "" && data[0] == '>'): bq += " "
7  if pre:
       if list non-empty: bq += list_code_indent
       bq += "    "
       data = data.replace("\n", "\n" + bq); pre_indent = bq
8  if startpre: startpre = false
       if list non-empty: data = data.trim_start_matches(any char in ("\n" + pre_indent))   // character SET
9  if start: space = false; p_p = 0; start = false
10 if force == "end": p_p = 0; out("\n"); space = false
11 if p_p > 0: out((br_toggle + "\n" + bq) repeated p_p times); space = false; br_toggle = ""
12 if space: if !lastWasNL: out(" "); space = false
13 (reference-link footer at :837-862 — never triggers because inline_links is on)
14 if force == "end": for (abbr, title) in abbr_list: out("  *[" + abbr + "]: " + title + "\n")
15 p_p = 0; out(data)
```

**Unicode whitespace** for step 3, for `str.strip()`, and for regex `\s`:
U+0009–000D, U+001C–001F, U+0020, U+0085, U+00A0, U+1680, U+2000–200A, U+2028, U+2029, U+202F, U+205F, U+3000. U+200B (zero-width space) is not whitespace.

**What follows from this**
- Newlines are only written when the next real output arrives (step 11). Pending newlines at the very end are thrown away (step 10).
- The `start` flag (step 9) cancels pending newlines and spaces before the first real output. It is set again by `<blockquote>` and `<li>`.
- Each piece's trailing whitespace (collapsed to one space) is written immediately. Its leading whitespace becomes a deferred space. So `"foo <span> bar</span>"` gives `"foo  bar"` with **two** spaces, and `"a <br> b"` gives `"a   \nb"`.
- Because `br_toggle` is repeated on every newline in step 11, a paragraph break after a table row comes out as `"  \n  \n"`.
- Inside `<pre>`, pending newlines carry the indent: `"para\n    \n    \n    line1"`.

### `handle_data(data, entity_char=false)` (`:872-913`)
Called for each text piece, and for each decoded entity with `entity_char=true`.
```
if data == "": return
if stressed: data = py_strip(data)   (Unicode whitespace, both ends); stressed = false; preceding_stressed = true
elif preceding_stressed:
    if data[0] NOT in {] [ ( ) { } . ! ?} ∪ UnicodeWS  &&  hn(current_tag) == 0  &&  current_tag ∉ {a, code, pre}:
        data = " " + data
    preceding_stressed = false
if maybe_automatic_link is Some(href):
    if data == href && href matches ^[a-zA-Z+]+:// : o("<" + data + ">"); empty_link = false; return   // maybe_automatic_link is NOT cleared
    else: o("["); maybe_automatic_link = None; empty_link = false
if !code && !pre && !entity_char: data = escape_md_section(data)
preceding_data = data
o(data, puredata = true)
```
- `current_tag` is the last start or end tag seen. After `</b>` it is `"b"`, so `<b>bold</b>, x` gives `**bold** , x`.
- Only a text piece consumes `stressed`. `<i></i>x` gives `__x`.

### `handle()` and `finish()` (`:143-180`, `:953`)
```
start = true
feed(html.replace("</' + 'script>", "</ignore>"))   // literal 15-char string including quotes and +
feed(""); close()                                    // flush the tokenizer
pbr(); o("", force = "end")
text = join(outtextlist).replace("&nbsp_place_holder;", " "); outtextlist = []
return text                                          // optwrap returns early; pad_tables is false
```
- The output ends with exactly one `"\n"` after the last content, plus any newlines the content already ended with (`</ul>`, `<br>`, pre).
- An empty document gives `"\n"`.
- If `quiet` is not 0 at the end (unclosed `<head>`, stray `</head>` or `</script>`), the output is `""`.

---

## 3. How Python's parser splits the input (3.13.12)

The parser is created with `convert_charrefs=False` (`:51`).

**Splitting text**
- Text is cut at every `<` and `&`. Each stretch between them is one `handle_data` call.
- These split text into separate pieces:
  - every tag, comment and declaration
  - every entity
  - a lone `<` (followed by a space, a digit, etc.) becomes its own `"<"` piece
  - a lone `&` becomes its own `"&"` piece
- Example: `"a & b"` gives the pieces `"a "`, `"&"`, `" b"`.

**Tags**
- A start tag is `<` + an ASCII letter. Tag names are lowercased and may contain `:` (so `o:p` stays `o:p`).
- Attribute names are lowercased. Quotes are removed from values, and character references in values are decoded using HTML5 attribute rules (`parser.py:93-106`).
- An attribute with no value gives `None`.
- With duplicate attributes, the **last** one wins (`dict(attrs)`).
- An unquoted value swallows a trailing `/`: `src=a.png/>` gives `"a.png/"`.
- `<x .../>` calls the start handler and then the end handler, for any tag. So `<b/>` gives `****` and `<a href=u/>` is an empty link.
- `</br>` is only an end tag, so it produces nothing.
- No tree is built. There is no implicit closing and no case-sensitivity issue.

**Comments and declarations (all dropped)**
- Comments end at `-->` or `--!>`. `<!-->` and `<!--->` are empty comments. An unterminated comment runs to end of input.
- `<![CDATA[...]]>` is dropped, including its content.
- `<!doctype ...>`, `<?...>`, any other `<!...>` (including Outlook's `<![if !mso]>`), and `</` followed by a non-letter (up to `>`) are all dropped. `</>` is ignored.

**Incomplete markup at end of input**
- An unterminated start tag (`x<y z`, `<div`) is silently dropped, and everything after it is lost.
- A bare `</` at the very end is output as text.

**Raw-text elements** (`parser.py:134-135`)
- `script`, `style`, `xmp`, `iframe`, `noembed`, `noframes`: everything up to `</name` followed by whitespace, `/` or `>` (case-insensitive) is a single piece. Tags and entities inside are not processed.
- `title` and `textarea`: the same, except entities are decoded.
- `plaintext`: the rest of the document is raw text.
- `noscript`: parsed normally.
- Only `head`, `style` and `script` are hidden by html2text. Content of `iframe`, `noframes`, `xmp`, `textarea`, and a `title` outside `<head>`, is printed literally: `<iframe>if <b>x</b></iframe>` gives `if <b>x</b>`.
- An unclosed raw-text element turns the rest of the input into one piece.

**Line endings**
- `\r\n` is not normalised. Outside `<pre>`, `\r` collapses as whitespace. Inside `<pre>`, it stays: `"\n    a\r\n    b"`.

---

## 4. Entities and character references

### Named entity `&name` (`:185-195`, `:930-937`)
- Matched by the regex `&([a-zA-Z][-.a-zA-Z0-9]*)[^a-zA-Z0-9]`. The terminator character is consumed only if it is `;`.
- At end of input, an unterminated `&name` takes the rest of the buffer as the name.
- Decoding:
  1. If the name is a key in `UNIFIABLE`, use that value.
  2. Otherwise look up `html5[name + ";"]` (case-sensitive, full WHATWG table; some entries are two code points).
  3. Otherwise output `"&" + name + ";"`. A `;` is added even if the source had none.

| Input | Output |
|---|---|
| `AT&T rocks` | `AT&T; rocks` |
| `AT&T` (at end) | `AT&T;` |
| `a&b=c` | `a&b;=c` |
| `?a=1&c=2` | `?a=1&c;=2` |
| `&amp b` | `& b` |
| `&unknown;` | `&unknown;` |
| `a & b` | `a & b` (`&` is its own piece) |

**`UNIFIABLE`** (`config.py:112-151`):

| Entities | Output |
|---|---|
| `rsquo`, `lsquo` | `'` |
| `rdquo`, `ldquo` | `"` |
| `copy` | `(C)` |
| `mdash` | `--` |
| `ndash` | `-` |
| `rarr` | `->` |
| `larr` | `<-` |
| `middot` | `*` |
| `oelig` | `oe` |
| `aelig` | `ae` |
| `agrave`, `aacute`, `acirc`, `atilde`, `auml`, `aring` | `a` |
| `egrave`, `eacute`, `ecirc`, `euml` | `e` |
| `igrave`, `iacute`, `icirc`, `iuml` | `i` |
| `ograve`, `oacute`, `ocirc`, `otilde`, `ouml` | `o` |
| `ugrave`, `uacute`, `ucirc`, `uuml` | `u` |
| `lrm`, `rlm` | empty (nothing output) |
| `nbsp` | `"&nbsp_place_holder;"` (set at `:141`), becomes `" "` at the end |

- Keys are lowercase only: `&Eacute;` gives `É`, but `&eacute;` gives `e`.
- Literal Unicode characters in the text are **never** changed: `’“é` passes through as-is.

### Numeric reference `&#N` / `&#xH` (`:182-183`, `:915-928`)
- Matched by `&#(?:[0-9]+|[xX][0-9a-fA-F]+)[^0-9a-fA-F]`.
- Decoding:
  1. Values outside 1..0x10FFFF, and surrogates, become U+FFFD.
  2. 0x80–0x9F are mapped to their Windows-1252 characters (`utils.py:13-41`; 0x81, 0x8D, 0x8F, 0x90, 0x9D are left as-is).
  3. If the code point belongs to a `UNIFIABLE` entity (excluding nbsp), use the ASCII value. So `&#8217;` and `&#x92;` give `'`, and `&#233;` gives `e`.
  4. Otherwise output the character.
- **Crash:** decimal digits followed directly by a–f/A–F (`&#39abc`) never match. The parser waits for more input, then at `close()` calls `int()` on the rest of the document, which raises `ValueError`.
- `&#;` gives the literal text `&#;`.

### Decoded entities skip escaping but take part in the piece logic
Decoded entities and references are never Markdown-escaped (`&#42;` gives `*`; `&lt;b&gt;` gives `<b>`). They still count as pieces for stripping, the leading-space rule, auto-link matching and `preceding_data`.

### Non-breaking spaces
- `&nbsp;` gives a **non-collapsing** `" "`: `a&nbsp;&nbsp;b` gives `a  b`, and `<p>&nbsp;</p>` gives `" \n"`.
- `&#160;`, `&#xA0;` and a literal U+00A0 are **collapsible whitespace**: `a&#160;&#160;b` gives `a b`.

---

## 5. Markdown escaping (`utils.py:230-251`)

### `escape_md_section`
Applied to each raw text piece before whitespace collapsing, except inside code or pre and except for decoded entities. Four steps, in order:
1. Double a backslash when it is followed by any of these characters: `` \ ` * _ { } [ ] ( ) # + - . ! ``.
2. `^(\s*\d+)(\.)(?=\s)` becomes `\1\.` — `1. x` gives `1\. x`.
3. `^(\s*)(\+)(?=\s)` becomes `\1\+`.
4. `^(\s*)(-)(?=\s|-)` becomes `\1\-` — `--- hr` gives `\--- hr`; `-x` is unchanged.

All three anchored patterns use MULTILINE, so `^` means "start of the piece or after a `\n` in it". `\d` means Unicode digits (`١. x` gives `١\. x`).

Consequences:
- `"a\n1. item"` gives `a 1\. item`: the line start in the source counts even though the output joins the lines.
- `<b>x</b>1. y` gives `**x** 1\. y`.
- Nothing else is escaped: `*`, `_`, `` ` ``, `#`, `[`, `]` and `!` all pass through.

### `escape_md`
Used for URLs, link titles and image alt text. Puts a backslash before each of `\ [ ] ( )`.

---

## 6. Rules for each tag

These run in `handle_tag` (`:304-737`), in this order, for every start and end tag.

### Step 0 (`:315-323`)
On a start tag, if `maybe_automatic_link` is set and the tag is not one of `p, div, style, dl, dt, img`: `o("[")`, clear `maybe_automatic_link`, set `empty_link = false`.

### Headings h1–h9 (`:343-365`)
- The test is `tag[0] == 'h'`, length 2, and second character `1`–`9`, so `<h7>` gives `####### `.
- **Not inside an `<a>`:** call `p()` on both start and end. On start, `o("#"*n + " ")`. On end, return immediately.
- Text is not trimmed: `<h1> Title </h1>` gives `#  Title ` (two spaces, trailing space).
- **Inside an `<a>`** (`astack` non-empty, even when the anchor has no href):
  - On start: if the last written string is exactly `"["`, remove it and write `"# "` then `"["`.
  - On end: `p_p = 0`, then return. There is no paragraph break.
  - `<a href=u><h2>H</h2></a>` gives `## [H](u)`.
  - `<a name=x><h2>Head</h2></a>more` gives `Headmore`: no `#` and no break.

### Paragraph and line elements
- **`p`, `div`** (`:367-378`): on start and end, call `p()`, unless inside an `<a>` or `split_next_td` is set (inside a table row).
  - **These are the only block elements.** `section`, `article`, `header`, `footer`, `center`, `font`, `span`, `o:p`, `tbody` and the rest produce nothing: `<section>a</section><section>b</section>` gives `ab`.
- **`br`** (start only): `o("  \n")`, or `o("  \n> ")` inside a blockquote. That is a single `>` whatever the nesting depth.
- **`hr`** (start only): `p(); o("* * *"); p()`.

### Hidden content and body
- **`head`, `style`, `script`:** `quiet += 1` on start, `-= 1` on end. A stray end tag makes `quiet` −1, which hides **everything**.
- **`body`** (start or end): `quiet = 0`.
- `<title>` inside `<head>` is hidden; outside it, its text is printed.

### Blockquote (`:406-414`)
- **Start:** `p(); o("> ", force=true); start = true; blockquote += 1`.
- **End:** `blockquote -= 1; p()`.
- Paragraph breaks inside use the `bq` prefix: `"> a\n> \n> b"`.
- Nested: `"> a\n>\n>> b\n> \n> c"`.
- The newline written by `</ul>` has no prefix, so text after a list leaves the quote.

### Emphasis
- **`em`, `i`, `u`:** on both start and end, write `"_"`.
  - On start, write `" _"` instead (and append `" "` to `preceding_data`) if `preceding_data` is non-empty and its last character is not ASCII whitespace or ASCII punctuation.
  - Start also sets `stressed`.
  - `preceding_data` is never reset between blocks: `<p>foo</p><p><i>bar</i></p>` gives `"foo\n\n _bar_"` with a leading space. With a newline between the paragraphs in the source, there is no leading space.
- **`strong`, `b`:** `"**"`. The `" **"` form is used only when the last character of `preceding_data` is `*`. `<strong>a</strong><strong>b</strong>` gives `**a****b**`.
- **`del`, `strike`, `s`:** `"~~"`, with `" ~~"` after `~`. Not affected by `ignore_emphasis`.
- Empty elements are not removed: `<b></b>` gives `****`, `<em> </em>after` gives `__ after`.
- An unclosed `<b>` leaves the `**` unbalanced.

### Code
- **`kbd`, `code`, `tt`** when not inside pre: on start **and** end, write a backtick and toggle `code`.
- Text inside is not escaped but is still whitespace-collapsed: `<code>a\nb</code>` gives `` `a b` ``.

### `abbr`
- **Start:** `abbr_data = ""`; `abbr_title` = the `title` attribute.
- While `abbr_data` is active, every string passed to `o()` is appended to it.
- **End:** if there is a title, `abbr_list[abbr_data] = title`.
- At the very end of the document: `"  *[HTML]: HyperText\n"`.

### Other inline tags
- **`q`:** writes `"` and toggles.
- **`sup`, `sub`:** ignored.

### Definition lists
- `<dl>` start: `p()`.
- `</dt>`: `pbr()`.
- `<dd>` start: `o("    ")`.
- `</dd>`: `pbr()`.

### `ol`, `ul` (`:615-633`)
```
if list is empty && !lastWasList: p()
start: push {name: tag, num: start_attr - 1, or 0 if invalid}
end:   if list non-empty: pop; if list is now empty: o("\n")
lastWasList = true      // every other tag (except the early heading returns) sets it false; text does not
```
- The `start` attribute is parsed with Python `int()`, which accepts surrounding spaces, `+`/`-`, `1_0` and Unicode digits.
- `<ol start>` with no value raises `AssertionError`.
- `<li value>` is ignored.

### `li` (`:635-663`)
```
list_code_indent = ""; pbr()
start: li = top of list, or a temporary {ul, 0} if there is no list
       indent = for each list on the stack: "   " if the previous entry was ol, else "  "
       o(indent)
       ul: o("* "), indent += "  "
       ol: num += 1; o(num + ". "), indent += "   "
       start = true
```
- Top-level items get a two-space indent: `"  * a"`, `"  1. a"`.
- Nested indents: ul in ul gives `"    * "`; ul in ol gives `"     * "`; ol in ul gives `"    1. "`; ol in ol gives `"     1. "`.
- A `<li>` outside any list gives `"* x"` with no indent.
- Continuation lines are **not** indented: `<li><p>a</p><p>b</p></li>` gives `"  * a\n\nb"`.
- After a list: `"  * b\n\n\n\nc"` before a `<p>`, or `"\n\nc"` before plain text.
- Consecutive lists are separated by `"\n\n\n"`.

### `pre` (`:720-731`)
- **Start:** `startpre = pre = true; pre_indent = ""`, then `p()`.
- **End:** `pre = false`, then `p()`.
- Content is not escaped or collapsed. A leading `\n` is added if missing, and every `\n` becomes `"\n" + bq + list indent + "    "`.
- `<b>`, `<a>` and `<br>` inside still produce output (`**`, links, `"  \n    "`). `<code>` inside does nothing.
- An empty `<pre></pre>` leaves `startpre` set, so the next text gets an extra leading `\n`.

### Tags with no handling
Any other tag only does three things: sets `current_tag`, triggers step 0 inside a pending link, and resets `lastWasList`.

---

## 7. Links and images

### `<a>` start (`:505-521`)
- A real link needs an `href` attribute that has a value and does not start with `#`. The check uses the raw value, so leading spaces defeat it.
- For a real link:
  - push the attributes onto `astack`
  - `maybe_automatic_link = href`, `empty_link = true`
  - when `protect_links` is set, the stored href becomes `"<" + href + ">"` (after `maybe_automatic_link` was taken)
- Anything else (no href, `<a href>` with no value, `#...`, `name=`) pushes `None`. Its text is printed plain.

### Opening bracket
The `[` is written lazily: by step 0, by the first text piece (in `handle_data`), or by an `<img>`.

### `<a>` end (`:522-546`)
```
pop a
if maybe_automatic_link is truthy && !empty_link: maybe_automatic_link = None   // auto-link already written
elif a:
    if empty_link: o("["); empty_link = false; maybe_automatic_link = None
    p_p = 0
    t = escape_md(title or "")
    o("](" + escape_md(href) + (if strip(t) != "": " \"" + t + "\"" else "") + ")")
```

### Verified link outputs
| Input | Output |
|---|---|
| `<a href="u">text</a>` | `[text](u)` |
| same, `protect_links` on | `[text](<u>)` |
| `<a href="http://x.com/a">http://x.com/a</a>` | `<http://x.com/a>` (both modes) |
| `<a href="www.x.com">www.x.com</a>` | `[www.x.com](www.x.com)` |
| `<a href="mailto:a@b.com">a@b.com</a>` | `[a@b.com](mailto:a@b.com)` |
| `<a href="http://x">\nhttp://x\n</a>` | `[ http://x ](http://x)` |
| `<a href="http://x"></a>` | `[](http://x)` |
| `<a href="">t</a>` | `[t]()` (`[t](<>)` when protected) |
| `<a href=" http://x ">sp</a>` | `[sp]( http://x )` |
| title `T (1) [2]` | `[text](u "T \(1\) \[2\]")` |
| title of only whitespace | title omitted |
| `foo<a href="u"> bar </a>baz` | `foo[ bar ](u)baz` |
| `<a href="u"><p>para</p></a>` | `[para](u)` (no break inside a link) |
| nested `<a>` | `[x[y](u2)z](u1)` |
| `<a href="http://x">http://x<br></a>` | `<http://x>[  \n](http://x)` |

- Automatic links require the whole piece to equal the href exactly, and the href to match `^[a-zA-Z+]+://`.
- In a URL, `\`, `[`, `]`, `(` and `)` are backslash-escaped: `http://x/a\(b\)`.

### `<img>` start (`:548-604`)
- Needs a `src` attribute with a value; otherwise nothing is output.
- `alt` is the `alt` attribute or `""`.
- If a link is pending, `o("[")` first.
- Output is `o("![" + escape_md(alt) + "]")` then `o("(" + escape_md(src) + ")")`.
- `title`, `width` and `height` are ignored. The alt text is not whitespace-collapsed (a newline in alt stays).
- Examples: `[![A](i.png)](u)`, `![](i \(1\).png)`.
- Images do not consume `stressed` and do not update `preceding_data`.

---

## 8. Tables (`:665-718`)

```
<table>:     table_start = true                  (no p(), no break before or after)
<td>/<th>:   if split_next_td: o("| "); split_next_td = true; td_count += 1
<tr>:        td_count = 0
</tr>:       split_next_td = false; soft_br()
             if table_start: o("---" joined by "|", td_count times); soft_br(); table_start = false
```
- The first row is always treated as the header, even when it uses `<td>`.
- The separator is `---|---`. There are no outer pipes and no spaces.
- Each row ends with `"  \n"`.
- `<p>` and `<div>` inside cells are ignored: `p1p2| d`. `<br>` inside a cell breaks the row.
- `colspan` is ignored. `thead`, `tbody` and `caption` produce nothing (`Capa`).
- A missing `</tr>` leaves `split_next_td` set, which **turns off all later `<p>`/`<div>` breaks**: `a| bxy`.

| Input | Output |
|---|---|
| compact table (no whitespace between tags) | `A| B  \n---|---  \n1| 2\n` |
| same table, pretty-printed | `A | B  \n---|---  \n1 | 2\n` |
| empty middle cell, compact | `1| | 3` |
| empty middle cell, pretty-printed | `a |  | c` |
| `<td><b>x</b></td><td>y</td>` | `**x**|  y` |
| `<p>text</p><table>…</table><p>after</p>` | `text\n\na| b  \n---|---  \n  \nafter\n` |

---

## 9. Reusing one instance across `handle()` calls

`email_processor.py:23` creates one `HTML2Text` per `EmailProcessor`. `get_email_body` calls `handle()` once for each `text/html` part found by `walk()`, including parts of forwarded messages, and the last result wins.

**Reset on each call:** only `start`, `outtextlist`, `p_p` and `space`.

**Carried over:**
- `abbr_list` keeps growing and is printed again at the end of every later document: `'second\n  *[A]: T\n'`.
- `br_toggle`: `'p1  \n  \np2\n'` after an earlier table.
- `quiet`, `list`, `blockquote`, `astack`, `pre`, `code`, `quote`, the link and emphasis flags, the table flags, `preceding_data`, `lastWasNL` and `lastWasList`.
- The parser's raw-text mode: after an unclosed `<script>`, the next document starts inside the script.

The table converter (`textutils.py`) creates a fresh instance each time, so it is not affected.

---

## 10. Verified test outputs

| Input | Output |
|---|---|
| `<p>a</p><p>b</p>` | `a\n\nb\n` |
| `<div>a<div>b</div>c</div>` | `a\n\nb\n\nc\n` |
| `<p>a</p><p></p><p></p><p>b</p>` | `a\n\nb\n` |
| `<br><br><br>x` | `  \n  \n  \nx\n` |
| `x<br><br><br>` | `x  \n  \n  \n\n` |
| `<p>x</p><br><p>y</p>` | `x\n\n  \n\n\ny\n` |
| `<h1>A</h1><h2>B</h2>text` | `# A\n\n## B\n\ntext\n` |
| `a<hr>b` | `a\n\n* * *\n\nb\n` |
| `foo<i>bar</i>baz` | `foo _bar_ baz\n` |
| `foo.<i>bar</i>` | `foo._bar_\n` |
| `<i>x</i>, y; <b>z</b>: w <b>s</b>(t) <b>u</b>!` | `_x_ , y; **z** : w **s**(t) **u**!\n` |
| `x<b> bold </b>y` | `x**bold** y\n` |
| `<b>&amp;</b>x` | `**&** x\n` |
| `<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>` | `  * a\n    * b\n  * c\n\n\n` |
| `<ol start="5"><li>a</li><li>b</li></ol>` | `  5. a\n  6. b\n\n\n` |
| `<ul><li>a</li></ul><p>c</p>` | `  * a\n\n\n\nc\n` |
| `<blockquote><p>a</p><p>b</p></blockquote>after` | `> a\n> \n> b\n\nafter\n` |
| `<blockquote>a<br>b</blockquote>` | `> a  \n> b\n` |
| `<pre>line1\nline2</pre>` | `\n    line1\n    line2\n` |
| `<ul><li>item<pre>code\nmore</pre></li></ul>` | `  * item\n        \n        code\n        more\n\n\n\n` |
| `<dl><dt>Term</dt><dd>Def</dd></dl>after` | `Term\n    Def\nafter\n` |
| `x &#10; y` | `x  y\n` |
| `+ plus\n- dash\n-- emdash` | `\+ plus \- dash \-- emdash\n` |
| `back\slash \*` | `back\slash \\*\n` |
| `<html><head><title>T</title>…</head><body><p>x</p></body></html>` | `x\n` |
| `<title>T &amp; U</title><p>x</p>` | `T & U\n\nx\n` |
| `<!--[if mso]><p>m</p><![endif]-->x<![if !mso]>y<![endif]>z` | `xyz\n` |
| `<p class=MsoNormal>a<o:p></o:p></p><p class=MsoNormal>b<o:p>&nbsp;</o:p></p>` | `a\n\nb \n` |
| `</head>hidden`, `<head>never closed` | `""` |
| `&#65abc;` | raises `ValueError` |

For the table path, take the output and apply Python `str.strip()`, which removes Unicode whitespace at both ends only.

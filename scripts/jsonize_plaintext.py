#! /usr/bin/env python3

import sys
import json
import re

book_data = {"format": "source"}
chapters = []
current_chapter = None
current_paragraph_lines = []
code_lines = None

def join_lines(lines):
  if not lines: return ""
  if re.search("^> ", lines[0]):
    role = "blockquote"
  else:
    role = "paragraph"
  new_lines = []
  for line in lines:
    if role == "blockquote":
      line = re.sub("^> +", "", line)
    line = line.strip()
    if line:
      new_lines.append(line)
  text = " ".join(new_lines)
  return role, text

line_num = 0
start_line_num = 0
for line in sys.stdin:
  line_num += 1
  line = re.sub(r"\s", " ", line).rstrip()
  if code_lines is None and re.search(r"^```", line):
    start_line_num = line_num
    code_lines = [line]
    continue
  if code_lines is not None:
    code_lines.append(line)
    if re.search(r"^```", line):
      if not current_chapter:
        current_chapter = {"body": []}
      if current_paragraph_lines:
        role, text = join_lines(current_paragraph_lines)
        current_chapter["body"].append((role, text, start_line_num))
        current_paragraph_lines = []
      text = "\n".join(code_lines)
      current_chapter["body"].append(("code", text, start_line_num))
      code_lines = None
    continue
  if line == "":
    if not current_chapter:
      current_chapter = {"body": []}
    if current_paragraph_lines:
      role, text = join_lines(current_paragraph_lines)
      current_chapter["body"].append((role, text, start_line_num))
      current_paragraph_lines = []
    continue
  if line.startswith("# "):
    if "title" not in book_data:
      book_data["title"] = line[2:].strip()
    continue
  match = re.search(r"^- *@id +(.*)$", line)
  if match:
    if "id" not in book_data:
      book_data["id"] = match.group(1)
    continue
  match = re.search(r"^- *@author +(.*)$", line)
  if match:
    if "author" not in book_data:
      book_data["author"] = match.group(1)
    continue
  if line.startswith("## "):
    if current_chapter:
      if current_paragraph_lines:
        role, text = join_lines(current_paragraph_lines)
        current_chapter["body"].append((role, text, start_line_num))
        current_paragraph_lines = []
      if current_chapter["body"]:
        chapters.append(current_chapter)
    chapter_title = line[3:].strip()
    current_chapter = {"title": chapter_title, "body": [], "raw_line": line_num}
    continue
  match = re.search(r"^- *@macro +(.*)$", line)
  if match:
    macro = match.group(1)
    if not current_chapter:
      current_chapter = {"body": []}
    if current_paragraph_lines:
      role, text = join_lines(current_paragraph_lines)
      current_chapter["body"].append((role, text, start_line_num))
      current_paragraph_lines = []
    current_chapter["body"].append(("macro", macro, line_num))
    continue
  header_match = re.search(r"^### +(.*)$", line)
  list_match = re.search(r"^- +(.*)$", line)
  table_match = re.search(r"^\|.*\|$", line)
  if header_match or list_match or table_match:
    if not current_chapter:
      current_chapter = {"body": []}
    if current_paragraph_lines:
      role, text = join_lines(current_paragraph_lines)
      current_chapter["body"].append((role, text))
      current_paragraph_lines = []
    if header_match:
      current_chapter["body"].append(("header", header_match.group(1), line_num))
    elif list_match:
      current_chapter["body"].append(("list", list_match.group(1), line_num))
    elif table_match:
      current_chapter["body"].append(("table", line, line_num))
    continue
  if not current_paragraph_lines:
    start_line_num = line_num
  current_paragraph_lines.append(line)

if current_chapter:
  if current_paragraph_lines:
    role, text = join_lines(current_paragraph_lines)
    current_chapter["body"].append((role, text, start_line_num))
  chapters.append(current_chapter)

new_chapters = []
for chapter in chapters:
  body = chapter["body"]
  new_body = []
  for role, text, line_num in body:
    mode = None
    if role == "code":
      match = re.fullmatch(r"```(\w+)?\n(.*?)\n```", text, flags=re.DOTALL)
      if match:
        mode = match.group(1)
        text = match.group(2)
    if text:
      record = {
        role: text,
        "raw_line": line_num,
      }
      if role in ["list", "table"] and new_body:
        prev_record = new_body[-1]
        if role in prev_record and prev_record["raw_line"] == line_num - 1:
          record["concat"] = True
      if mode:
        record["mode"] = mode
      new_body.append(record)
  chapter["body"] = new_body
  if "raw_line" not in chapter and new_body:
    chapter["raw_line"] = new_body[0]["raw_line"]
  if "title" in chapter or new_body:
    new_chapters.append(chapter)

if new_chapters:
  book_data["chapters"] = new_chapters

print(json.dumps(book_data, ensure_ascii=False, indent=2))

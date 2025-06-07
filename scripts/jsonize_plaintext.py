#! /usr/bin/env python3

import sys
import json
import re

book_data = {}
chapters = []
current_chapter = None
current_paragraph_lines = []

for line in sys.stdin:
  line = re.sub(r"\s", " ", line).strip()

  if line == "":
    if not current_chapter:
      current_chapter = {"body": []}
    if current_paragraph_lines:
      paragraph = " ".join(current_paragraph_lines)
      current_chapter["body"].append(paragraph)
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
        paragraph = " ".join(current_paragraph_lines)
        current_chapter["body"].append(paragraph)
        current_paragraph_lines = []
      if current_chapter["body"]:
        chapters.append(current_chapter)
    chapter_title = line[3:].strip()
    current_chapter = {"title": chapter_title, "body": []}
    continue

  match = re.search(r"^- *@macro +(.*)$", line)
  if match:
    macro = match.group(1)
    if not current_chapter:
      current_chapter = {"body": []}
    if current_paragraph_lines:
      paragraph = " ".join(current_paragraph_lines)
      current_chapter["body"].append(paragraph)
      current_paragraph_lines = []
    current_chapter["body"].append(line)
    continue

  current_paragraph_lines.append(line)

if current_chapter:
  if current_paragraph_lines:
    paragraph = " ".join(current_paragraph_lines)
    current_chapter["body"].append(paragraph)
  chapters.append(current_chapter)

new_chapters = []
for chapter in chapters:
  body = chapter["body"]
  new_body = []
  for line in body:
    match = re.search(r"^- *@macro +(.*)$", line)
    if match:
      macro = match.group(1)
      new_body.append({"macro": macro})
      continue
    if line:
      new_body.append({"paragraph": line})
  chapter["body"] = new_body
  if "title" in chapter or new_body:
    new_chapters.append(chapter)

if new_chapters:
  book_data["chapters"] = new_chapters

print(json.dumps(book_data, ensure_ascii=False, indent=2))

#! /usr/bin/env python3#!/usr/bin/python3

import sys
import json
import re

book_data = {}
chapters = []
current_chapter = None
current_paragraph_lines = []

for line in sys.stdin:
  line = line.strip()

  if line == "":
    if not current_chapter:
      current_chapter = {"paragraphs": []}
    if current_paragraph_lines:
      paragraph = " ".join(current_paragraph_lines)
      current_chapter["paragraphs"].append(paragraph)
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
        current_chapter["paragraphs"].append(paragraph)
        current_paragraph_lines = []
      if current_chapter["paragraphs"]:
        chapters.append(current_chapter)
    chapter_title = line[3:].strip()
    current_chapter = {"title": chapter_title, "paragraphs": []}
    continue
  current_paragraph_lines.append(line)

if current_chapter:
  if current_paragraph_lines:
    paragraph = " ".join(current_paragraph_lines)
    current_chapter["paragraphs"].append(paragraph)
  chapters.append(current_chapter)

if chapters:
  book_data["chapters"] = chapters

print(json.dumps(book_data, ensure_ascii=False, indent=2))

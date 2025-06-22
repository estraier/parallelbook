#! /usr/bin/env python3

import argparse
import json
from pathlib import Path
import re
import sys


def load_input_data(path):
  with open(path, encoding="utf-8") as f:
    data = json.load(f)
  if data.get("format") != "parallel":
    raise ValueError("Not parallel book data")
  return data


def output_element(elem):
  if not elem: return
  if "source" not in elem: return
  if "target" not in elem: return
  def normalize(text):
    return re.sub(r"\s+", " ", text).strip()
  source = normalize(elem["source"])
  target = normalize(elem["target"])
  print(f"{source}\t{target}")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("input_file",
                      help="path of the input JSON file")
  args = parser.parse_args()
  input_path = Path(args.input_file)
  book = load_input_data(input_path)
  output_element(book.get("title"))
  output_element(book.get("author"))
  for chapter in book.get("chapters") or []:
    output_element(chapter.get("title"))
    for element in chapter.get("body") or []:
      output_element(element.get("header"))
      for name in ["paragraph", "blockquote", "list"]:
        value = element.get(name)
        if value:
          for item in value:
            output_element(item)
      for row in element.get("table") or []:
        for cell in row:
          output_element(cell)


if __name__ == "__main__":
  main()

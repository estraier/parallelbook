#! /usr/bin/env python3

import argparse
from datetime import datetime
import hashlib
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom
import zipfile


PROG_NAME = "make_parallel_epub.py"


logging.basicConfig(format="%(message)s", stream=sys.stderr)
logger = logging.getLogger(PROG_NAME)
logger.setLevel(logging.INFO)


def load_input_data(path):
  with open(path, encoding="utf-8") as f:
    data = json.load(f)
  if data.get("format") != "parallel":
    raise ValueError("Not parallel book data")
  if data.get("source_language") != "en":
    raise ValueError("Source language is not English")
  if data.get("target_language") != "ja":
    raise ValueError("Target language is not Japanese")
  return data


def prepare_working_directories(args, root_path):
  meta_inf = root_path / "META-INF"
  oebps = root_path / "OEBPS"
  for path in [meta_inf, oebps]:
    if path.exists():
      for item in path.iterdir():
        if item.is_dir():
          shutil.rmtree(item)
        else:
          item.unlink()
  (root_path / "META-INF").mkdir(parents=True, exist_ok=True)
  (root_path / "OEBPS" / "text").mkdir(parents=True, exist_ok=True)
  (root_path / "OEBPS" / "css").mkdir(parents=True, exist_ok=True)
  (root_path / "OEBPS" / "image").mkdir(parents=True, exist_ok=True)


def prettify(elem):
  rough_string = ET.tostring(elem, encoding='utf-8')
  parsed = minidom.parseString(rough_string)
  return parsed.toprettyxml(indent='  ')


def make_cover_file(args, output_path):
  shutil.copy(args.cover, output_path)


def make_nav_file(args, output_path, book):
  if args.title:
    book_title = args.title
  else:
    book_title = book.get("title", {}).get("source") or "untitled"
  html = ET.Element("html", {
    "xmlns": "http://www.w3.org/1999/xhtml",
    "xmlns:epub": "http://www.idpf.org/2007/ops",
    "lang": "en"
  })
  head = ET.SubElement(html, "head")
  ET.SubElement(head, "meta", {"charset": "utf-8"})
  ET.SubElement(head, "title").text = book_title
  body = ET.SubElement(html, "body")
  ET.SubElement(body, "h1").text = book_title
  nav = ET.SubElement(body, "nav", {
    "epub:type": "toc",
  })
  ET.SubElement(nav, "h2").text = "Table of Contents"
  ol = ET.SubElement(nav, "ol")
  for i, chapter in enumerate(book.get("chapters", []), start=1):
    chapter_title = chapter.get("title", {}).get("source") or f"Chapter {i}"
    li = ET.SubElement(ol, "li")
    a = ET.SubElement(li, "a", {
      "href": f"chapter-{i:03d}.xhtml",
    })
    a.text = chapter_title
  tree = ET.ElementTree(html)
  with open(output_path, "w", encoding="utf-8") as f:
    f.write(prettify(tree.getroot()))


def create_parallel_element(tag, class_name, source, target, analysis):
  container = ET.Element(tag, {"class": f"{class_name} parallel"})
  source_span = ET.SubElement(container, "span", {"class": "source", "lang": "en"})
  source_span.text = source
  target_span = ET.SubElement(container, "span", {"class": "target", "lang": "ja"})
  target_span.text = target
  if analysis:
    analysis_ul = ET.SubElement(container, "ul", {"class": "analysis"})
    for sentence in analysis:
      render_sentence(analysis_ul, sentence)
  return container


def render_sentence(parent, sentence):
  li = ET.SubElement(parent, "li", {"class": "sentence"})
  pattern = sentence.get("pattern")
  if pattern:
    span_pat = ET.SubElement(li, "span", {
      "class": f"pattern pattern-{pattern.lower()}"
    })
    span_pat.text = pattern
  text = sentence.get("text")
  if text:
    span_txt = ET.SubElement(li, "span", {"class": "text"})
    span_txt.text = text
  elements = sentence.get("elements")
  if elements:
    ul_elem = ET.SubElement(li, "ul", {"class": "element-list"})
    for element in elements:
      render_element_item(ul_elem, element)


def render_element_item(parent, element):
  li = ET.SubElement(parent, "li", {"class": "element-item"})
  typ = element.get("type")
  if typ:
    span_type = ET.SubElement(li, "span", {"class": f"type type-{typ.lower()}"})
    span_type.text = typ
  text = element.get("text")
  if text:
    span_txt = ET.SubElement(li, "span", {"class": "text"})
    span_txt.text = text
  tran = element.get("translation")
  if tran:
    span_tran = ET.SubElement(li, "span", {"class": "tran"})
    span_tran.text = tran
  verb_map = {
    "tense": {"past": "過去"},
    "aspect": {
      "progressive": "進行",
      "perfect": "完了",
      "perfect progressive": "完進"
    },
    "mood": {
      "imperative": "命令",
      "subjunctive": "仮定",
      "conditional": "条件"
    },
    "voice": {"passive": "受動"}
  }
  for attr, mapping in verb_map.items():
    label = mapping.get(element.get(attr))
    if label:
      vattr = ET.SubElement(li, "span", {"class": "vattr"})
      vattr.text = label


def make_chapter_file(args, output_path, chapter, chapter_num):
  chapter_title = chapter.get("title", {}).get("source") or f"Chapter {chapter_num}"
  html = ET.Element("html", {
    "xmlns": "http://www.w3.org/1999/xhtml",
    "xml:lang": "en",
    "lang": "en"
  })
  head = ET.SubElement(html, "head")
  ET.SubElement(head, "meta", {"charset": "utf-8"})
  ET.SubElement(head, "title").text = chapter_title
  ET.SubElement(head, "link", {
    "rel": "stylesheet",
    "href": "../css/style.css",
    "type": "text/css",
  })
  body = ET.SubElement(html, "body")
  if "title" in chapter:
    item = chapter["title"]
    ET.SubElement(body, "h2").append(create_parallel_element(
      "span", "title", item["source"], item["target"], None))
  for block in chapter["body"]:
    if "header" in block:
      el = ET.SubElement(body, "h3")
      item = block["header"]
      el.append(create_parallel_element(
        "span", "header", item["source"], item["target"], None))
    elif "paragraph" in block:
      p = ET.SubElement(body, "p", {"class": "paragraph"})
      for item in block["paragraph"]:
        p.append(create_parallel_element(
          "span", "sentence", item["source"], item["target"], item.get("analysis")))
    elif "blockquote" in block:
      bq = ET.SubElement(body, "blockquote", {"class": "blockquote"})
      for item in block["blockquote"]:
        bq.append(create_parallel_element(
          "span", "sentence", item["source"], item["target"], item.get("analysis")))
    elif "list" in block:
      ul = ET.SubElement(body, "ul", {"class": "list"})
      for item in block["list"]:
        li = ET.SubElement(ul, "li")
        li.append(create_parallel_element(
          "span", "sentence", item["source"], item["target"], item.get("analysis")))
    elif "table" in block:
      table = ET.SubElement(body, "table", {"class": "table"})
      for row in block["table"]:
        tr = ET.SubElement(table, "tr")
        for cell in row:
          td = ET.SubElement(tr, "td")
          td.append(create_parallel_element(
            "span", "sentence", cell["source"], cell["target"], None))
    elif "code" in block:
      pre = ET.SubElement(body, "pre", {"class": "code"})
      pre.text = block["code"]["text"]
  tree = ET.ElementTree(html)
  with open(output_path, "w", encoding="utf-8") as f:
    f.write(prettify(tree.getroot()))


def make_style_file(args, output_path):
  css = """
.parallel {
  display: block;
}

.parallel span {
  display: block;
}

.parallel span.target {
  font-size: 80%;
  color: #777;
  margin-left: 1ex;
}

blockquote {
  margin-left: 0.8ex;
  padding-left: 0.8ex;
  border-left: solid 2px #ddd;
}

ul {
  padding-left: 2.8ex;
}

table {
  margin-left: 0.4ex;
  border-collapse: collapse;
  font-size: 95%;
}
td {
  border: 1px solid #ddd;
  padding: 0 0.5ex;
}

pre {
  margin-left: 0.4ex;
  padding: 0 0.4ex;
  font-size: 90%;
  white-space: pre-wrap; word-wrap: break-word;
  line-height: 1.2;
  border: 1px solid #ddd;
}
.analysis {
  font-size: 90%;
  font-weight: normal;
  margin: 0;
  padding-left: 0;
  text-align: left;
  background: #fff;
  border: solid 2px #fff;
  border-radius: 0.5ex;
}
.analysis ul {
  margin: 0 0 0 2ex;
  padding: 0;
}
.analysis li {
  padding-left: 0;
  list-style: none;
}
.analysis span.text .element-s { background: #fde; }
.analysis span.text .element-v { background: #def; }
.analysis span.text .element-o { background: #efd; }
.analysis span.text .element-c { background: #ffd; }
.analysis span.pattern {
  display: inline-block;
  text-align: center;
  min-width: 4ex;
  margin-right: 0.5ex;
  padding: 0 0.2ex;
  font-size: 85%;
  background: #eee;
  border: 1px solid #999;
  border-radius: 0.5ex;
  opacity: 0.8;
}
.analysis span.pattern-sv {
  background: #def;
}
.analysis span.pattern-svo {
  background: #efd;
}
.analysis span.pattern-svc {
  background: #ffd;
}
.analysis span.pattern-svoo {
  background: #efc;
}
.analysis span.pattern-svoc {
  background: #fed;
}
.analysis span {
  display: inline;
}
.analysis span.type {
  display: inline-block;
  text-align: center;
  min-width: 2.5ex;
  margin-right: 0.5ex;
  padding: 0 0.2ex;
  font-size: 85%;
  background: #eee;
  border: 1px solid #ddd;
  border-radius: 0.5ex;
  opacity: 0.7;
}
.analysis span.type-s {
  background: #fde;
}
.analysis span.type-v {
  background: #def;
}
.analysis span.type-o {
  background: #efd;
}
.analysis span.type-c {
  background: #ffd;
}
.analysis span.tran {
  margin-left: 1.2ex;
  color: #036;
  opacity: 0.7;
  font-size: 85%;
}
.analysis span.relation {
  margin-right: 0.5ex;
  font-size: 80%;
  opacity: 0.7;
}
.analysis span.relation:before {
  content: "(";
}
.analysis span.relation:after {
  content: ")";
}
.analysis span.tran:before {
  content: "(";
}
.analysis span.tran:after {
  content: ")";
}
.analysis span.vattr {
  font-size: 75%;
  color: #333;
  opacity: 0.8;
  background: #eee;
  border: solid 1pt #ddd;
  border-radius: 0.8ex;
  margin-left: 0.3ex;
}
.analysis .subclause-list {
  font-size: 90%;
  opacity: 0.9;
}
.analysis .subsentence-list {
  font-size: 90%;
  opacity: 0.9;
}
""".strip()
  output_path.write_text(css, encoding="utf-8")


def compute_book_id(book):
  serialized = json.dumps(book, ensure_ascii=False, sort_keys=True)
  digest = hashlib.sha1(serialized.encode("utf-8")).digest()
  uuid_bytes = bytearray(digest[:16])
  uuid_bytes[6] = (uuid_bytes[6] & 0x0F) | 0x50
  uuid_bytes[8] = (uuid_bytes[8] & 0x3F) | 0x80
  return str(uuid.UUID(bytes=bytes(uuid_bytes)))


def make_content_opf_file(args, output_path, book):
  if args.renew_id:
    book_id = str(uuid.uuid4())
  else:
    book_id = compute_book_id(book)
  if args.title:
    book_title = args.title
  else:
    book_title = book.get("title", {}).get("source") or "untitled"
    book_title = "[PB] " + book_title
  if args.author:
    book_author = args.author
  else:
    book_author = book.get("author", {}).get("source") or "anonymous"
  timestamp = datetime.now().isoformat(timespec="seconds") + "Z"
  package = ET.Element("package", {
    "xmlns": "http://www.idpf.org/2007/opf",
    "xmlns:dc": "http://purl.org/dc/elements/1.1/",
    "version": "3.0",
    "unique-identifier": "book-id"
  })
  metadata = ET.SubElement(package, "metadata")
  ET.SubElement(metadata, "dc:identifier", {"id": "book-id"}).text = f"urn:uuid:{book_id}"
  ET.SubElement(metadata, "dc:title").text = book_title
  ET.SubElement(metadata, "dc:creator").text = book_author
  ET.SubElement(metadata, "dc:language").text = "en"
  ET.SubElement(metadata, "dc:language").text = "ja"
  ET.SubElement(metadata, "dc:publisher").text = "estraier/parallelbook"
  ET.SubElement(metadata, "dc:subject").text = "parallel corpus"
  ET.SubElement(metadata, "meta", {"property": "dcterms:modified"}).text = timestamp
  manifest = ET.SubElement(package, "manifest")
  if args.cover:
    ext = Path(args.cover).suffix.lower() or ".jpg"
    if ext in [".jpg", ".jpeg"]:
      img_type = "image/jpeg"
    elif ext in [".png"]:
      img_type = "image/png"
    elif ext in [".svg"]:
      img_type = "image/svg+xml"
    elif ext in [".gif"]:
      img_type = "image/gif"
    elif ext in [".webp"]:
      img_type = "image/webp"
    else:
      img_type = "image/" + ext[1:]
    ET.SubElement(manifest, "item", {
      "id": "cover",
      "href": f"image/cover{ext}",
      "media-type": img_type,
      "properties": "cover-image",
    })
  ET.SubElement(manifest, "item", {
    "id": "style",
    "href": "css/style.css",
    "media-type": "text/css",
  })
  ET.SubElement(manifest, "item", {
    "id": "nav",
    "href": "text/nav.xhtml",
    "media-type": "application/xhtml+xml",
    "properties": "nav",
  })
  chapter_count = len(book.get("chapters", []))
  for i in range(1, chapter_count + 1):
    ET.SubElement(manifest, "item", {
      "id": f"chapter-{i:03d}",
      "href": f"text/chapter-{i:03d}.xhtml",
      "media-type": "application/xhtml+xml",
    })
  spine = ET.SubElement(package, "spine")
  for i in range(1, chapter_count + 1):
    ET.SubElement(spine, "itemref", {
      "idref": f"chapter-{i:03d}",
    })
  tree = ET.ElementTree(package)
  with open(output_path, "w", encoding="utf-8") as f:
    f.write(prettify(tree.getroot()))


def make_container_file(args, output_path):
  container = ET.Element("container", {
    "version": "1.0",
    "xmlns": "urn:oasis:names:tc:opendocument:xmlns:container",
  })
  rootfiles = ET.SubElement(container, "rootfiles")
  ET.SubElement(rootfiles, "rootfile", {
    "full-path": "OEBPS/content.opf",
    "media-type": "application/oebps-package+xml",
  })
  tree = ET.ElementTree(container)
  with open(output_path, "w", encoding="utf-8") as f:
    f.write(prettify(tree.getroot()))


def make_epub_archive(args, working_path, output_path):
  mimetype_path = working_path / "mimetype"
  mimetype_path.write_text("application/epub+zip", encoding="utf-8")
  with zipfile.ZipFile(output_path, "w") as zf:
    zf.write(mimetype_path, arcname="mimetype", compress_type=zipfile.ZIP_STORED)
    for file_path in working_path.rglob("*"):
      if file_path.name == "mimetype":
        continue
      archive_name = file_path.relative_to(working_path)
      zf.write(file_path, arcname=str(archive_name), compress_type=zipfile.ZIP_DEFLATED)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("input_file",
                      help="path of the input JSON file")
  parser.add_argument("--output", default=None,
                      help="path of the output EPUB file")
  parser.add_argument("--working", default=None,
                      help="path of the working EPUB directory")
  parser.add_argument("--renew-id", action="store_true",
                      help="Renew the book ID every time")
  parser.add_argument("--title", default=None,
                      help="Override the book title")
  parser.add_argument("--author", default=None,
                      help="Override the book author")
  parser.add_argument("--cover", default=None,
                      help="Path to PNG file to use as cover image")
  args = parser.parse_args()
  input_path = Path(args.input_file)
  input_stem = input_path.stem
  input_stem = re.sub(r"-(epub)", "", input_path.stem)
  if args.output:
    output_path = Path(args.output)
  else:
    output_path = input_path.with_name(input_stem + ".epub")
  if args.working:
    working_path = Path(args.state)
  else:
    working_path = input_path.with_name(input_stem + "-epub")
  logger.info(f"Loading data from {input_path}")
  book = load_input_data(input_path)
  logger.info(f"Preparing the directory as {working_path}")
  prepare_working_directories(args, working_path)
  if args.cover:
    ext = Path(args.cover).suffix.lower() or ".jpg"
    cover_path = working_path / "OEBPS" / "image" / f"cover{ext}"
    make_cover_file(args, cover_path)
  nav_path = working_path / "OEBPS" / "text" / "nav.xhtml"
  logger.info(f"Writing the navigation file as {nav_path}")
  make_nav_file(args, nav_path, book)
  for i, chapter in enumerate(book.get("chapters", []), 1):
    chapter_path = working_path / "OEBPS" / "text" / f"chapter-{i:03d}.xhtml"
    logger.info(f"Writing the chapter file as {chapter_path}")
    make_chapter_file(args, chapter_path, chapter, i)
  style_path = working_path / "OEBPS" / "css" / "style.css"
  logger.info(f"Writing the style file as {style_path}")
  make_style_file(args, style_path)
  opf_path = working_path / "OEBPS" / "content.opf"
  logger.info(f"Writing the OPF file as {opf_path}")
  make_content_opf_file(args, opf_path, book)
  container_path = working_path / "META-INF" / "container.xml"
  logger.info(f"Writing the container file as {container_path}")
  make_container_file(args, container_path)
  logger.info(f"Writing the EPUB file as {output_path}")
  make_epub_archive(args, working_path, output_path)


if __name__ == "__main__":
  main()

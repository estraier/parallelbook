#! /usr/bin/env python3

import argparse
import json
import Levenshtein
import logging
import openai
import os
import regex
import sqlite3
import sys
import tiktoken
import time
from pathlib import Path


PROG_NAME = "make_parallel_corpus.py"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHATGPT_MODELS = [
  ("gpt-4.1-mini",  0.00040, 0.00160),
  ("gpt-4.1",       0.00200, 0.00800),
  ("gpt-4.1-nano",  0.00010, 0.00040),
  ("gpt-3.5-turbo", 0.00050, 0.00150),
  ("gpt-4o",        0.00250, 0.01000),
  ("gpt-4-turbo",   0.01000, 0.03000),
  ("gpt-4",         0.01000, 0.03000),
]


logging.basicConfig(format="%(message)s", stream=sys.stderr)
logger = logging.getLogger(PROG_NAME)
logger.setLevel(logging.INFO)


class StateManager:
  def __init__(self, db_path):
    self.db_path = db_path

  def initialize(self, input_tasks):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
          idx INTEGER PRIMARY KEY,
          role TEXT,
          source_text TEXT,
          response TEXT
        )
      ''')
      cur.execute('DELETE FROM tasks')
      for i, (role, text, attrs) in enumerate(input_tasks):
        cur.execute(
          'INSERT INTO tasks (idx, role, source_text) VALUES (?, ?, ?)',
          (i, role, text)
        )
      conn.commit()

  def load(self, index):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('SELECT idx, role, source_text, response FROM tasks WHERE idx = ?', (index,))
      row = cur.fetchone()
      if row:
        return {
          "index": row[0],
          "role": row[1],
          "source_text": row[2],
          "response": json.loads(row[3]) if row[3] is not None else None
        }
      return None

  def reset_task(self, index, role, source_text):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('UPDATE tasks SET role = ?, source_text = ?, response = NULL WHERE idx = ?',
                  (role, source_text, index))
      conn.commit()

  def set_response(self, index, response):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      response_json = json.dumps(response, separators=(',', ':'), ensure_ascii=False)
      cur.execute('UPDATE tasks SET response = ? WHERE idx = ?', (response_json, index))
      conn.commit()

  def find_undone(self):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('SELECT idx FROM tasks WHERE response IS NULL ORDER BY idx ASC LIMIT 1')
      row = cur.fetchone()
      return row[0] if row else -1

  def count(self):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('SELECT COUNT(*) FROM tasks')
      return cur.fetchone()[0]

  def load_all(self):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('SELECT idx, role, source_text, response FROM tasks ORDER BY idx ASC')
      rows = cur.fetchall()
      return [
        {
          "index": row[0],
          "role": row[1],
          "source_text": row[2],
          "response": json.loads(row[3]) if row[3] is not None else None
        } for row in rows
      ]


def load_input_data(path):
  with open(path, encoding="utf-8") as f:
    data = json.load(f)
  if data.get("format") != "source":
    raise ValueError("Not source book data")
  meta = {}
  book_id = data.get("id")
  if book_id:
    meta["id"] = book_id
  tasks = []
  book_title = data.get("title")
  if book_title:
    tasks.append(("book_title", book_title, {}))
    meta["title"] = book_title
  book_author = data.get("author")
  if book_author:
    tasks.append(("book_author", book_author, {}))
    meta["author"] = book_author
  for chapter_index, chapter in enumerate(data.get("chapters", [])):
    raw_line = chapter.get("raw_line")
    if raw_line:
      name = f"chapter_raw_line_{chapter_index}"
      meta[name] = raw_line
    chapter_title = chapter.get("title")
    if chapter_title:
      tasks.append(("chapter_title", chapter_title, {}))
    chapter_body = chapter.get("body")
    for element in chapter_body:
      attrs = {}
      for name in ["raw_line", "concat"]:
        value = element.get(name)
        if value is not None:
          attrs[name] = value
      for name in ["paragraph", "blockquote", "header", "list", "table", "code", "macro"]:
        value = element.get(name)
        if value:
          tasks.append((name, value, attrs))
  return meta, tasks



def merge_translations(translations):
  merged = []
  i = 0
  while i < len(translations):
    en = translations[i]["source"].strip()
    ja = translations[i]["target"].strip()
    j = i + 1
    while j < len(translations):
      next_en = translations[j]["source"].strip()
      next_ja = translations[j]["target"].strip()
      concat = False
      if regex.search(r"[,]$", en) and regex.search(r"^[a-zA-Z0-9]", next_en):
        concat = True
      elif regex.search(r"[a-z]$", en) and regex.search("^([a-z]|I )", next_en):
        concat = True
      if concat:
        en += " " + next_en
        if not regex.search(r"[,.:：、。！？]$", ja):
          ja_sep = "：" if en.endswith(":") else "、"
        else:
          ja_sep = ""
        ja += ja_sep + next_ja
        j += 1
      else:
        break
    merged.append({"source": en, "target": ja})
    i = j
  return merged


def postprocess_tasks(tasks):
  for task in tasks:
    role = task["role"]
    if role in ["macro", "code"]: continue
    response = task.get("response")
    if not response: continue
    content = response["content"]
    response["content"] = merge_translations(content)


def validate_tasks(tasks):
  for task in tasks:
    role = task["role"]
    if role in ["macro", "code"]: continue
    source_text = task["source_text"]
    response = task.get("response")
    if not response: continue
    content = response["content"]
    if not validate_content(role, source_text, content):
      logger.warning(f"Invalid task content: {task}")
      return False
  return True


def build_text_record(task, concat=False):
  response = task["response"]
  index = task["index"]
  has_error = "error" in response
  has_intact = "intact" in response
  pairs = []
  for seq, content in enumerate(response["content"]):
    pair = {
      "id": f"{index:05d}-{seq:03d}",
      "source": content["source"],
      "target": content["target"],
    }
    if has_error:
      pair["error"] = True
    if has_intact:
      pair["intact"] = True
    pairs.append(pair)
  if concat:
    pair = {
      "id": f"{index:05d}-{0:03d}",
      "source": " ".join([x["source"] for x in pairs]),
      "target": " ".join([x["target"] for x in pairs]),
    }
    if has_error:
      pair["error"] = True
    if has_intact:
      pair["intact"] = True
    pairs = [pair]
  return pairs


def build_macro_record(task):
  response = task["response"]
  index = task["index"]
  content = response["content"]
  record = {
    "id": f"{index:05d}-000",
    "name": content["name"],
  }
  value = content.get("value")
  if value is not None:
    record["value"] = value
  return record


def build_code_record(task):
  response = task["response"]
  index = task["index"]
  content = response["content"]
  record = {
    "id": f"{index:05d}-000",
    "text": content.get("value"),
  }
  return record


def build_table_cells(index, item):
  def get_cells(text):
    text = regex.sub(r"^\|", "", text.strip())
    text = regex.sub(r"\|$", "", text.strip())
    return text.split("|")
  src_cells = get_cells(item["source"])
  trg_cells = get_cells(item["target"])
  max_len = max(len(src_cells), len(trg_cells))
  src_cells += [""] * (max_len - len(src_cells))
  trg_cells += [""] * (max_len - len(trg_cells))
  cells = []
  for src_cell, trg_cell in zip(src_cells, trg_cells):
    cell = {
      "id": f"{index:05d}-{len(cells):03d}",
      "source": src_cell,
      "target": trg_cell,
    }
    cells.append(cell)
  return cells


def build_output(input_meta, input_tasks, tasks):
  book = {"format": "parallel"}
  input_book_id = input_meta.get("id")
  if input_book_id:
    book["id"] = input_book_id
  book["source_language"] = "en"
  book["target_language"] = "ja"
  total_cost = 0
  chapters = []
  live_tasks = []
  index_line_map = {}
  index_concat_set = set()
  for task in tasks:
    response = task.get("response")
    if not response:
      logger.warning(f"Stop by an unprocessed task: {task['index']}")
      break
    index = task["index"]
    role = task["role"]
    source_text = task["source_text"]
    if index >= 0 and index < len(input_tasks):
      input_role, input_text, input_attrs = input_tasks[index]
      if role != input_role:
        logger.warning(f"mismatch input role: {index}: {role}")
      if source_text != input_text:
        short_text = cut_text_by_width(source_text, 80)
        logger.warning(f"mismatch input text: {index}: {short_text}")
      raw_line = input_attrs.get("raw_line")
      if raw_line:
        index_line_map[index] = raw_line
      concat = input_attrs.get("concat")
      if concat:
        index_concat_set.add(index)
    else:
      logger.warning(f"no matching input: {index}")
    live_tasks.append(task)
  done_seqs = set()
  for seq, task in enumerate(live_tasks):
    if seq in done_seqs: continue
    done_seqs.add(seq)
    index = task["index"]
    role = task["role"]
    response = task["response"]
    total_cost += response.get("cost", 0)
    if role == "book_title":
      if "title" not in book:
        book["title"] = build_text_record(task, concat=True)[0]
    elif role == "book_author":
      if "author" not in book:
        book["author"] = build_text_record(task, concat=True)[0]
    elif role == "chapter_title":
      chapter = {
        "title": build_text_record(task, concat=True)[0],
        "body": [],
      }
      chapters.append(chapter)
    else:
      if not chapters:
        chapter = {
          "body": [],
        }
        chapters.append(chapter)
      chapter = chapters[-1]
      raw_line = index_line_map.get(index)
      if role in ["paragraph", "blockquote"]:
        record = {role: build_text_record(task)}
        if raw_line:
          record["raw_line"] = raw_line
        chapter["body"].append(record)
      elif role in ["header"]:
        chapter["body"].append({role: build_text_record(task, True)[0]})
      elif role in ["list", "table"]:
        items = []
        next_seq = seq
        while next_seq < len(live_tasks):
          next_task = live_tasks[next_seq]
          next_index = next_task["index"]
          if next_seq > seq:
            if next_task["role"] != role: break
            if next_index not in index_concat_set: break
          items.append(build_text_record(next_task, True)[0])
          done_seqs.add(next_seq)
          next_seq += 1
        if role == "table":
          rows = []
          for i, item in enumerate(items):
            cells = build_table_cells(index + i, item)
            if cells:
              rows.append(cells)
          items = rows
        record = {role: items}
        if raw_line:
          record["raw_line"] = raw_line
        chapter["body"].append(record)
      elif role == "macro":
        record = {role: build_macro_record(task)}
        if raw_line:
          record["raw_line"] = raw_line
        chapter["body"].append(record)
      elif role == "code":
        record = {role: build_code_record(task)}
        if raw_line:
          record["raw_line"] = raw_line
        chapter["body"].append(record)
      else:
        logger.warning(f"Unknown role: {index}: {role}")
  if chapters:
    for chapter_index, chapter in enumerate(chapters):
      name = f"chapter_raw_line_{chapter_index}"
      chapter_raw_line = input_meta.get(name)
      if chapter_raw_line:
        chapter["raw_line"] = chapter_raw_line
    book["chapters"] = chapters
  book["cost"] = round(total_cost, 3)
  return book


def split_sentences_english(text):
  norm_text = text.strip()
  norm_text = regex.sub(r"(?i)(mrs|mr|ms|jr|dr|prof|st|etc|i\.e|a\.m|p\.m|vs)\.",
                        r"\1__PERIOD__", norm_text)
  norm_text = regex.sub(r"(\W)([A-Z])\.", r"\1\2__PERIOD__", norm_text)
  norm_text = regex.sub(r"([a-zA-Z])([.!?;]+)(\s+)([A-Z])", r"\1\2{SEP}\4", norm_text)
  norm_text = regex.sub(r"([^.!?;{}]{100,})([.!?;]+)(\s+)", r"\1\2{SEP}", norm_text)
  norm_text = regex.sub(r'([.!?;]+)(\s+)(["“‘*\p{Ps}])', r"\1{SEP}\2\3", norm_text)
  norm_text = regex.sub(r'([.!?;]+["”’)\p{Pe}”])', r"\1{SEP}", norm_text)
  norm_text = regex.sub(r"__PERIOD__", ".", norm_text)
  sentences = []
  for sentence in norm_text.split("{SEP}"):
    sentence = sentence.strip()
    if sentence:
      sentences.append(sentence)
  return sentences


def calculate_width(text):
  total = 0
  for char in text:
    codepoint = ord(char)
    if codepoint >= 0x3000:
      total += 2
    else:
      total += 1
  return total


def cut_text_by_width(text, max_width):
  result = []
  current_width = 0
  for char in text:
    codepoint = ord(char)
    char_width = 2 if codepoint >= 0x3000 else 1
    if current_width + char_width > max_width:
      break
    result.append(char)
    current_width += char_width
  return ''.join(result)


def normalize_context_text(text):
  return regex.sub(r"\s+", " ", text).strip()


def get_hint(sm, index):
  min_index = max(0, index - 8)
  index -= 1
  while index >= min_index:
    record = sm.load(index)
    if not record: break
    response = record["response"]
    if not response: break
    hint = response.get("hint")
    if hint:
      return hint
    index -= 1
  return ""


def get_prev_context(sm, index, max_width=500):
  all_sentences = []
  trg_index = max(0, index - 8)
  while trg_index < index:
    record = sm.load(trg_index)
    if not record: break
    text = normalize_context_text(record["source_text"])
    sentences = split_sentences_english(text)
    all_sentences.extend(sentences)
    trg_index += 1
  all_sentences.reverse()
  sum_width = 0
  picked_sentences = []
  for sentence in all_sentences:
    if sum_width >= max_width:
      break
    width = calculate_width(sentence)
    if width > max_width:
      sentence = cut_text_by_width(sentence, max_width).strip() + "..."
      width = calculate_width(sentence)
    picked_sentences.append(sentence)
    sum_width += width
  picked_sentences.reverse()
  return picked_sentences


def get_next_context(sm, index, max_width=200):
  all_sentences = []
  trg_index = index + 1
  max_index = min(index + 5, sm.count())
  while trg_index < max_index:
    record = sm.load(trg_index)
    if not record: break
    text = normalize_context_text(record["source_text"])
    sentences = split_sentences_english(text)
    all_sentences.extend(sentences)
    trg_index += 1
  sum_width = 0
  picked_sentences = []
  for sentence in all_sentences:
    if sum_width >= max_width:
      break
    width = calculate_width(sentence)
    if width > max_width:
      sentence = cut_text_by_width(sentence, max_width).strip() + "..."
      width = calculate_width(sentence)
    picked_sentences.append(sentence)
    sum_width += width
  return picked_sentences


def make_prompt(book_title, role, source_text,
                hint, prev_context, next_context, extra_hint, attempt,
                jsonize_input, use_source_example):
  lines = []
  def p(line):
    lines.append(line)
  if book_title:
    p(f"あなたは『{book_title}』の英日翻訳を担当しています。")
  else:
    p(f"あなたは書籍の英日翻訳を担当しています。")
  p("以下の情報をもとに、与えられたパラグラフを自然な日本語に翻訳してください。")
  p("----")
  if jsonize_input:
    data = {}
    if hint:
      data["現在の場面の要約"] = hint
    if prev_context:
      data["直前のパラグラフ"] = prev_context
    if next_context:
      data["直後のパラグラフ"] = next_context
    data["翻訳対象のパラグラフ"] = source_text
    p(json.dumps(data, ensure_ascii=False, indent=2))
    p("")
  else:
    if hint:
      p("現在の場面の要約（前回出力された文脈ヒント）:")
      p(f"- {hint}")
      p("")
    if prev_context:
      p("直前のパラグラフ:")
      for sentence in prev_context:
        p(f" - {sentence}")
      p("")
    if next_context:
      p("直後のパラグラフ:")
      for sentence in next_context:
        p(f" - {sentence}")
      p("")
    p("----")
    p("翻訳対象のパラグラフ:")
    if attempt >= 3:
      proc_source_text = "\n".join(split_sentences_english(source_text))
    else:
      proc_source_text = source_text
    p(proc_source_text)
  p("")
  p("----")
  p("出力形式はJSONとし、次の要素を含めてください:")
  p('{')
  p('  "translations": [')
  if role in ["paragraph", "blockquote"]:
    p('    { "en": "原文の文1", "ja": "対応する訳文1" },')
    p('    { "en": "原文の文2", "ja": "対応する訳文2" }')
    p('    // ...')
  else:
    p('    { "en": "原文の文", "ja": "対応する訳文" }')
  p('  ],')
  p('  "context_hint": "この段落を含めた現在の場面の要約、登場人物、心情、場の変化などを1文（100トークン程度）で簡潔に記述してください。",')
  p('}')
  p("")
  p("----")
  if attempt >= 3:
    if use_source_example:
      translations = []
      if role in ["paragraph", "blockquote"]:
        for split_source in split_sentences_english(source_text)[:2]:
          translation = {
            "en": split_source,
            "ja": "(enの訳文...)",
          }
          translations.append(translation)
      else:
        translation = {
          "en": source_text,
          "ja": "(enの訳文...)",
        }
        translations.append(translation)
      example = {
        "translations": translations,
        "context_hint": "マイケルが言ったことと反対のことをマリアが言うやり取りをしている。",
      }
      p("例を示します:")
      p(json.dumps(example, ensure_ascii=False, indent=2))
      p("")
      p("----")
    else:
      p("例を示します:")
      p('{')
      p('  "translations": [')
      if role in ["paragraph", "blockquote"]:
        p('    { "en": "He said, “Hello, world!”", "ja": "「こんにちは世界！」と彼は言った。" },')
        p('    { "en": "“Good-bye, world”, I replied.", "ja": "「さよなら世界」と私は応えた。" }')
        p('    // ...')
      else:
        p('    { "en": "He said, “Hello, world!”", "ja": "「こんにちは世界！」と彼は言った。" }')
      p('  ],')
      p('  "context_hint": "ジョーが言ったことと反対のことをナンシーが言うやり取りをしている。",')
      p('}')
      p("")
      p("----")
  if role == "book_title":
    p("このパラグラフは本の題名です。")
  if role == "chapter_title":
    p("このパラグラフは章の題名です。")
  if role in ["paragraph", "blockquote"]:
    p("英文は文法に従って文分割してください。たとえ短い文でも、文とみなせれば独立させてください。")
    p("ただし、分割の際に元の英文を1文字も変更しないでください。句読点や引用符も含めて全て保持してください。")
    if attempt >= 3 and regex.search(r"\p{Quotation_Mark}", source_text):
      p("【重要】 翻訳対象には引用符が含まれています。それを絶対に消さないでください。")
  elif role == "header":
    p("英文はヘッダなので、文分割は不要です。入力を1文として扱ってください。")
  elif role == "list":
    p("英文はリストの項目なので、文分割は不要です。入力を1文として扱ってください。")
  elif role == "table":
    p("英文は \"|\" で区切られたテーブルの要素です。文分割は不要です。\"|\" は維持した上で、それ以外の中身を翻訳してください。")
  p("日本語訳は文体・語調に配慮しつつも、できるだけ直訳調にとどめ、構文や語順の対応関係が分かるようにしてください。")
  p("片仮名語の音写をなるべく使わずに、意味のわかる訳語を当ててください。")
  p("context_hintは次の段落の翻訳時に役立つような背景情報を含めてください（例：誰が話しているか、舞台の変化、話題の推移など）。")
  p("不要な解説や装飾、サマリー文などは含めず、必ず上記JSON構造のみを出力してください。")
  if attempt >= 2:
    p("JSONの書式には細心の注意を払ってください。引用符や括弧やカンマの仕様を厳密に守ってください。")
    p("文分割の際に原文を変更しないでください。出力の \"en\" の値を連結すると原文と同じになるようにしてください。")
    p(f"過去のエラーによる現在の再試行回数={attempt-1}")
  extra_hint = extra_hint.strip()
  if extra_hint:
    p(extra_hint)
  return "\n".join(lines)


def count_chatgpt_tokens(text, model):
  encoding = tiktoken.get_encoding("cl100k_base")
  tokens = encoding.encode(text)
  return len(tokens)


def calculate_chatgpt_cost(prompt, response, model):
  for name, input_cost, output_cost in CHATGPT_MODELS:
    if name == model:
      num_input_tokens = count_chatgpt_tokens(prompt, model)
      num_output_tokens = count_chatgpt_tokens(response, model)
      total_cost = num_input_tokens / 1000 * input_cost + num_output_tokens / 1000* output_cost
      logger.debug(f"Cost: {total_cost:.6f} ({num_input_tokens/1000:.3f}*{input_cost}+{num_output_tokens/1000:.3f}*{output_cost})")
      return total_cost
  raise RuntimeError("No matching model")


def validate_content(role, source_text, content):
  def first_text(text):
    return regex.sub(r"\s", "", text)[:8]
  def last_text(text):
    return regex.sub(r"\s", "", text)[-4:]
  def normalize_text(text):
    return regex.sub(r"\s+", " ", text).lower().strip()
  def extract_marks(text):
    return regex.sub(r"[^\p{Quotation_Mark}]", "", text)
  def extract_verticals(text):
    return regex.sub(r"[^|]", "", text)
  joint_text = " ".join([x["source"] for x in content])
  first_orig = first_text(source_text)
  first_proc = first_text(joint_text)
  if first_orig != first_proc:
    logger.debug(f"First text diff: {first_orig} vs {first_proc}")
    return False
  last_orig = last_text(source_text)
  last_proc = last_text(joint_text)
  if last_orig != last_proc:
    logger.debug(f"Last text diff: {last_orig} vs {last_proc}")
    return False
  norm_orig = normalize_text(source_text)
  norm_proc = normalize_text(joint_text)
  distance = Levenshtein.distance(norm_orig, norm_proc)
  length = max(1, (len(norm_orig) + len(norm_proc)) / 2)
  diff = distance / length
  if diff > 0.1:
    logger.debug(f"Too much diff: {diff:.2f}, {norm_orig} vs {norm_proc}")
    return False
  mark_orig = extract_marks(source_text)
  mark_proc = extract_marks(joint_text)
  if mark_orig != mark_proc:
    logger.debug(f"Different marks: {mark_orig} vs {mark_proc}")
    return False
  if role == "table":
    vert_orig = extract_verticals(source_text)
    vert_proc = extract_verticals(joint_text)
    if vert_orig != vert_proc:
      logger.debug(f"Different verticals: {vert_orig} vs {vert_proc}")
      return False
  for pair in content:
    source = pair["source"]
    target = pair["target"]
    if regex.search(r"[A-Za-z]{2,} +[A-Za-z]{3,}", source) and not target:
      logger.debug(f"Too short target: {source} vs {target}")
      return False
  return True


def execute_task(
    book_title, role, source_text, hint, prev_context, next_context,
    main_model, failsoft, no_fallback, extra_hint):
  if len(source_text) <= 2000:
    return execute_task_single(
      book_title, role, source_text, hint, prev_context, next_context,
      main_model, failsoft, no_fallback, extra_hint)
  sentences = split_sentences_english(source_text)
  batches = [[]]
  batch_len = 0
  for sentence in sentences:
    if batch_len > 1000:
      batches.append([])
      batch_len = 0
    batches[-1].append(sentence)
    batch_len += len(sentence)
  if len(batches) > 1 and batch_len < 400:
    last_batch = batches.pop()
    batches[-1].extend(last_batch)
  batch_records = []
  batch_hint = hint
  batch_prev_context = prev_context
  for i, batch in enumerate(batches):
    batch_text = " ".join(batch)
    if i == len(batches) - 1:
      batch_next_context = next_context
    else:
      batch_next_context = []
      context_width = 0
      for sentence in batches[i+1]:
        batch_next_context.append(sentence)
        context_width += calculate_width(sentence)
        if context_width > 100: break
    record = execute_task_single(
      book_title, role, batch_text, hint, batch_prev_context, batch_next_context,
      main_model, failsoft, no_fallback, batch_hint)
    batch_records.append(record)
    batch_prev_context = []
    context_width = 0
    for sentence in reversed(batches[i]):
      batch_prev_context.append(sentence)
      context_width += calculate_width(sentence)
      if context_width > 200: break
    batch_prev_context.reverse()
    batch_hint = record["hint"]
  content = []
  cost = 0
  for record in batch_records:
    for translation in record["content"]:
      content.append(translation)
    cost += record.get("cost", 0)
  merged_record = {
    "content": content,
    "hint": batch_hint,
    "cost": cost,
  }
  return merged_record


def execute_task_single(
    book_title, role, source_text, hint, prev_context, next_context,
    main_model, failsoft, no_fallback, extra_hint):
  latins = regex.sub(r"[^\p{Latin}]", "", source_text)
  if len(latins) < 2:
    logger.debug(f"Not English: intact data is generated")
    record = {}
    content = []
    content.append({
      "source": source_text,
      "target": source_text,
    })
    record["content"] = content
    if hint:
      record["hint"] = hint
    record["intact"] = True
    return record
  models = [main_model]
  if not no_fallback:
    sub_model = None
    for name, _, _ in CHATGPT_MODELS:
      if name != main_model:
        models.append(name)
        break
  for model in models:
    configs = [(0.0, True, False), (0.0, False, False),
               (0.4, True, False), (0.4, False, False),
               (0.8, True, True), (0.8, False, True)]
    for attempt, (temp, jsonize_input, use_source_example) in enumerate(configs, 1):
      prompt = make_prompt(
        book_title, role, source_text, hint, prev_context, next_context, extra_hint, attempt,
        jsonize_input, use_source_example)
      logger.debug(f"Prompt:\n{prompt}")
      try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY).with_options(timeout=30)
        response = client.chat.completions.create(
          model=model,
          messages=[{ "role": "user", "content": prompt }],
          temperature=temp,
        )
        usage = response.usage.model_dump()
        logger.debug(f"Usage:\n{usage}")
        response = response.choices[0].message.content
        match = regex.search(r'```(?:json)?\s*([{\[].*?[}\]])\s*```', response, regex.DOTALL)
        if match:
          response = match.group(1)
        response = regex.sub(r',\s*([\]}])', r'\1', response)
        logger.debug(f"Response:\n{response}")
        data = json.loads(response)
        if type(data.get("translations")) != list:
          raise ValueError("No translaitons")
        if type(data.get("context_hint")) != str:
          raise ValueError("No context_hint")
        record = {}
        content = []
        for translation in data.get("translations"):
          if "en" not in translation:
            raise ValueError("No en in translaiton")
          if "ja" not in translation:
            raise ValueError("No ja in translaiton")
          rec_tran = {
            "source": translation["en"],
            "target": translation["ja"],
          }
          content.append(rec_tran)
        if content:
          match = regex.search(r"^(\p{Quotation_Mark})", source_text)
          if match:
            src_quot = match.group(1)
            first_tran = content[0]
            if not first_tran["source"].startswith(src_quot):
              first_tran["source"] = src_quot + first_tran["source"]
              if not regex.search(r"^(\p{Quotation_Mark})", first_tran["target"]):
                first_tran["target"] = "「" + first_tran["target"]
          match = regex.search(r"(\p{Quotation_Mark})$", source_text)
          if match:
            src_quot = match.group(1)
            last_tran = content[-1]
            if not last_tran["source"].endswith(src_quot):
              last_tran["source"] = last_tran["source"] + src_quot
              if not regex.search(r"(\p{Quotation_Mark})$", last_tran["target"]):
                last_tran["target"] = last_tran["target"] + "」"
        record["content"] = content
        record["hint"] = data.get("context_hint")
        record["cost"] = round(calculate_chatgpt_cost(prompt, response, model), 8)
        if not validate_content(role, source_text, content):
          raise ValueError("Validation error")
        return record
      except Exception as e:
        logger.info(f"Attempt {attempt} failed"
                    f" (model={model}, temperature={temp},"
                    f" j={jsonize_input}, x={use_source_example}): {e}")
        time.sleep(0.2)
  if failsoft:
    logger.warning(f"Failsoft: dummy data is generated")
    record = {}
    content = []
    content.append({
      "source": source_text,
      "target": "[*FAILSOFT*]",
    })
    record["content"] = content
    if hint:
      record["hint"] = hint
    record["error"] = True
    return record
  raise RuntimeError("All retries failed: unable to parse valid JSON with required fields")


def simulate_task_as_macro(source_text):
  record = {}
  name = "unknown"
  value = None
  match = regex.search(r"^([-_a-zA-Z0-9]+)(\s.*)?$", source_text)
  if match:
    name = match.group(1)
    value = match.group(2)
  content = {
    "name": name,
  }
  if value is not None:
    content["value"] = value.strip()
  record["content"] = content
  return record


def simulate_task_as_code(source_text):
  record = {}
  name = "unknown"
  value = source_text
  content = {
    "name": "code",
    "value": value,
  }
  record["content"] = content
  return record


def list_available_models():
  models = openai.models.list()
  for model in models.data:
    print(model.id)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("input_file",
                      help="path of the input JSON file")
  parser.add_argument("--output", default=None,
                      help="path of the output JSON file")
  parser.add_argument("--state", default=None,
                      help="path of the state SQLite file")
  parser.add_argument("--reset", action="store_true",
                      help="resets the state and start over all tasks")
  parser.add_argument("--num-tasks", type=int, default=None,
                      help="limits the number of tasks to do")
  parser.add_argument("--redo", type=str, default=None,
                      help="comma-separated list of task indexes to redo")
  parser.add_argument("--force-finish", action="store_true",
                      help="makes the output file even if all tasks are not done")
  parser.add_argument("--failsoft", action="store_true",
                      help="continue tasks on failure")
  parser.add_argument("--model", default=CHATGPT_MODELS[0][0],
                      help="sets the ChatGPT model by the name")
  parser.add_argument("--no-fallback", action="store_true",
                      help="do not use the fallback model")
  parser.add_argument("--extra-hint", default="",
                      help="extra hint to be appended to the prompt")
  parser.add_argument("--debug", action="store_true",
                      help="prints the debug messages too")
  parser.add_argument("--list-models", action="store_true",
                      help="prints known models and exit")
  if "--list-models" in sys.argv:
    list_available_models()
    sys.exit(0)
  args = parser.parse_args()
  if args.debug:
    logger.setLevel(logging.DEBUG)
  input_path = Path(args.input_file)
  input_stem = regex.sub(r"-(source|input)", "", input_path.stem)
  if args.output:
    output_path = Path(args.output)
  else:
    output_path = input_path.with_name(input_stem + "-parallel.json")
  if args.state:
    state_path = Path(args.state)
  else:
    state_path = input_path.with_name(input_stem + "-state.db")
  logger.info(f"Loading data from {input_path}")
  input_meta, input_tasks = load_input_data(input_path)
  sm = StateManager(state_path)
  if args.reset or not state_path.exists():
    sm.initialize(input_tasks)
  total_tasks = sm.count()
  logger.info(f"Total tasks: {total_tasks}")
  book_title = ""
  for index in range(100):
    record = sm.load(index)
    if not record: break
    if record["role"] == "book_title":
      book_title = record["source_text"]
      logger.info(f"Title: {book_title}")
      break
  logger.info(f"GPT model: {args.model}")
  redo_indexes = []
  if args.redo:
    try:
      redo_indexes = set(int(x.strip()) for x in args.redo.split(",") if x.strip())
      redo_indexes = list(reversed(sorted(list(redo_indexes))))
    except ValueError:
      logger.error(f"Invalid format for redo: {args.redo}")
  if redo_indexes:
    for redo_index in redo_indexes:
      if redo_index < len(input_tasks):
        role, source_text, attrs = input_tasks[redo_index]
        sm.reset_task(redo_index, role, source_text)
      else:
        logger.error(f"Invalid task ID for redo: {redo_index}")
  total_cost = 0
  done_tasks = 0
  max_done_tasks = total_tasks if args.num_tasks is None else args.num_tasks
  try:
    while done_tasks < max_done_tasks:
      index = sm.find_undone()
      if index < 0:
        break
      record = sm.load(index)
      role = record["role"]
      source_text = record["source_text"]
      short_source_text = regex.sub(r"\s+", " ", source_text).strip()
      short_source_text = cut_text_by_width(short_source_text, 64)
      logger.info(f"Task {index}: {role} - {short_source_text}")
      hint = get_hint(sm, index)
      prev_context = get_prev_context(sm, index)
      next_context = get_next_context(sm, index)
      if role == "macro":
        response = simulate_task_as_macro(source_text)
      elif role == "code":
        response = simulate_task_as_code(source_text)
      else:
        response = execute_task(
          book_title, role, source_text,
          hint, prev_context, next_context,
          args.model, args.failsoft, args.no_fallback, args.extra_hint,
        )
      sm.set_response(index, response)
      total_cost += response.get("cost", 0)
      done_tasks += 1
  except KeyboardInterrupt:
    logger.warning(f"Stop by Ctrl-C")
  logger.info(f"Done: tasks={done_tasks}, total_cost=${total_cost:.4f} (Y{total_cost*150:.2f})")
  index = sm.find_undone()
  if index < 0 or args.force_finish:
    tasks = sm.load_all()
    logger.info(f"Postprocessing the output")
    postprocess_tasks(tasks)
    logger.info(f"Validating the output")
    if not validate_tasks(tasks):
      raise RuntimeError("Validation failed")
    logger.info(f"Writing data into {output_path}")
    output_data = build_output(input_meta, input_tasks, tasks)
    with open(output_path, "w", encoding="utf-8") as f:
      print(json.dumps(output_data, ensure_ascii=False, indent=2), file=f)
    logger.info("Finished")
  else:
    logger.info("To be continued")


if __name__ == "__main__":
  main()

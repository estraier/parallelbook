#! /usr/bin/env python3

import argparse
import json
import Levenshtein
import logging
import os
import regex
import sqlite3
import sys
import tiktoken
import time
from datetime import datetime, timezone
from openai import OpenAI
from pathlib import Path


PROG_NAME = "make_parallel_book_chatgpt"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHATGPT_MODELS = [
  # model name, input token cost (USD/1K), output token cost (USD/1K)
  ("gpt-3.5-turbo", 0.0005, 0.0015),
  ("gpt-4o", 0.005, 0.015),
  ("gpt-4-turbo", 0.01, 0.03),
  ("gpt-4", 0.03, 0.06),
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
      for i, (role, text) in enumerate(input_tasks):
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


def load_json(path):
  with open(path, encoding="utf-8") as f:
    return json.load(f)


def parse_input_data(data):
  result = []
  book_title = data.get("title")
  if book_title:
    result.append(("book_title", book_title))
  book_author = data.get("author")
  if book_author:
    result.append(("book_author", book_author))
  for chapter in data.get("chapters", []):
    chapter_title = chapter.get("title")
    if chapter_title:
      result.append(("chapter_title", chapter_title))
    chapter_body = chapter.get("body")
    for element in chapter_body:
      for name in ["paragraph", "macro"]:
        value = element.get(name)
        if value:
          result.append((name, value))
  return result


def validate_tasks(tasks):
  def normalize_text(text):
    return regex.sub(r"\s+", " ", text).lower().strip()
  for task in tasks:
    role = task["role"]
    if role == "macro": continue
    source_text = task["source_text"]
    response = task.get("response")
    if not response: continue
    content = response["content"]
    if not validate_content(source_text, content):
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
    pairs = [pairs]
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


def build_output(input_data, tasks):
  book = {}
  input_book_id = input_data.get("id")
  if input_book_id:
    book["id"] = input_book_id
  book["source_language"] = "en"
  book["target_language"] = "ja"
  total_cost = 0
  chapters = []
  for task in tasks:
    role = task["role"]
    response = task.get("response")
    if not response:
      logger.warning(f"Stop by an unprocessed task: {task['index']}")
      break
    total_cost += response.get("cost", 0)
    role = task["role"]
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
      if role == "paragraph":
        chapter["body"].append({"paragraph": build_text_record(task)})
      elif role == "macro":
        chapter["body"].append({"macro": build_macro_record(task)})
      else:
        logger.warning(f"Unknown role: {role}")
  if chapters:
    book["chapters"] = chapters
  book["cost"] = round(total_cost, 3)
  book["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
  return book


def split_sentences_english(text):
  norm_text = text.strip()
  norm_text = regex.sub(r"(?i)(mrs|mr|ms|jr|dr|prof|st|etc|i\.e|a\.m|p\.m|vs)\.",
                        r"\1__PERIOD__", norm_text)
  norm_text = regex.sub(r"(\W)([A-Z])\.", r"\1\2__PERIOD__", norm_text)
  norm_text = regex.sub(r"([a-zA-Z])([.!?;]+)(\s+)([A-Z])", r"\1\2{SEP}\4", norm_text)
  norm_text = regex.sub(r"([^.!?;{}]{100,})([.!?;]+)(\s+)", r"\1\2{SEP}", norm_text)
  norm_text = regex.sub(r'([.!?;]+)(\s+)(["“‘\p{Ps}])', r"\1{SEP}\2\3", norm_text)
  norm_text = regex.sub(r'([.!?;]+["”’\p{Pe}”])', r"\1{SEP}", norm_text)
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
    sentences = split_sentences_english(record["source_text"])
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
    sentences = split_sentences_english(record["source_text"])
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


def make_prompt_enja(book_title, role, source_text, hint, prev_context, next_context, attempt):
  lines = []
  def p(line):
    lines.append(line)
  if book_title:
    p(f"あなたは『{book_title}』の英日翻訳を担当しています。")
  else:
    p(f"あなたは書籍の英日翻訳を担当しています。")
  p("以下の情報をもとに、与えられたパラグラフを自然な日本語に翻訳してください。")
  p("")
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
  p("----")
  p("出力形式はJSONとし、次の2つの要素を含めてください:")
  if attempt >= 3:
    p('{')
    p('  "translations": [')
    if role == "paragraph":
      p('    { "en": "He said, “Hello, world!”", "ja": "「こんにちは世界！」と彼は言った。" },')
      p('    { "en": "“Good-bye, world”, I replied.", "ja": "「さよなら世界」と私は応えた。" }')
      p('    // ...')
    else:
      p('    { "en": "He said, “Hello, world!”", "ja": "「こんにちは世界！」と彼は言った。" }')
    p('  ],')
    p('  "context_hint": "ジョーが言ったことと反対のことをナンシーが言うやり取りをしている。"')
    p('}')
  else:
    p('{')
    p('  "translations": [')
    if role == "paragraph":
      p('    { "en": "原文の文1", "ja": "対応する訳文1" },')
      p('    { "en": "原文の文2", "ja": "対応する訳文2" }')
      p('    // ...')
    else:
      p('    { "en": "原文の文", "ja": "対応する訳文" }')
    p('  ],')
    p('  "context_hint": "この段落を含めた現在の場面の要約、登場人物、心情、場の変化などを1文（100トークン程度）で簡潔に記述してください。"')
    p('}')
  if role == "book_title":
    p("このパラグラフは本の題名です。")
  if role == "chapter_title":
    p("このパラグラフは章の題名です。")
  if role == "paragraph":
    p("英文は意味的に自然な単位で文分割してください。たとえ短い文でも、文とみなせれば独立させてください。")
  p("日本語訳は文体・語調に配慮し、自然な対訳文を生成してください。")
  p("context_hint は次の段落の翻訳時に役立つような背景情報を含めてください（例：誰が話しているか、舞台の変化、話題の推移など）。")
  p("不要な解説や装飾、サマリー文などは含めず、必ず上記JSON構造のみを出力してください。")
  if attempt >= 2:
    p("JSONの書式には細心の注意を払ってください。引用符や括弧やカンマの仕様を厳密に守ってください。")
    p("原文を変更しないでください。出力の \"en\" の値を連結すると原文と同じになるようにしてください。")
    p(f"過去のエラーによる現在の再試行回数={attempt-1}")
  return "\n".join(lines)


def count_chatgpt_tokens(text, model):
  encoding = tiktoken.encoding_for_model(model)
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


def validate_content(source_text, content):
  def normalize_text(text):
    return regex.sub(r"\s+", " ", text).lower().strip()
  norm_orig = normalize_text(source_text)
  norm_proc = normalize_text(" ".join([x["source"] for x in content]))
  distance = Levenshtein.distance(norm_orig, norm_proc)
  length = max(1, (len(norm_orig) + len(norm_proc)) / 2)
  diff = distance / length
  if diff > 0.3:
    logger.debug(f"Too much diff: {diff:.2f}, {norm_orig} vs {norm_proc}")
    return False
  for pair in content:
    source = pair["source"]
    target = pair["target"]
    if regex.search(r"[A-Za-z]{2,} +[A-Za-z]{3,}", target) and len(target) < 1:
      logger.debug(f"Too short target: {source} vs {target}")
      return False
  return True


def execute_task_by_chatgpt_enja(
    book_title, role, source_text, hint, prev_context, next_context, main_model, failsoft, no_fallback):
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
    configs = [(0.0, True), (0.4, True), (0.6, True), (0.8, True), (0.0, False), (0.5, False)]
    for attempt, (temp, use_context) in enumerate(configs, 1):
      if use_context:
        p_hint = hint
        p_prev_context = prev_context
        p_next_context = next_context
      else:
        p_hint = ""
        p_prev_context = None
        p_next_context = None
      prompt = make_prompt_enja(
        book_title, role, source_text, p_hint, p_prev_context, p_next_context, attempt)
      logger.debug(f"Prompt:\n{prompt}")
      try:
        client = OpenAI(api_key=OPENAI_API_KEY).with_options(timeout=30)
        response = client.chat.completions.create(
          model=model,
          messages=[{ "role": "user", "content": prompt }],
          temperature=temp,
        )
        response = response.choices[0].message.content
        match = regex.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, regex.DOTALL)
        if match:
          response = match.group(1)
        response = regex.sub(r',\s*([\]}])', r'\1', response)
        logger.debug(f"Response:\n{response}")
        data = json.loads(response)
        if (type(data.get("translations")) == list and type(data.get("context_hint")) == str):
          record = {}
          content = []
          for translation in data.get("translations"):
            rec_tran = {
              "source": translation["en"],
              "target": translation["ja"],
            }
            content.append(rec_tran)
          record["content"] = content
          record["hint"] = data.get("context_hint")
          record["cost"] = round(calculate_chatgpt_cost(prompt, response, model), 8)
          if not validate_content(source_text, content):
            raise ValueError("Validation error")
          return record
      except Exception as e:
        logger.info(f"Attempt {attempt} failed"
                    f" (model={model}, temperature={temp}, use_context={use_context}): {e}")
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
  parser.add_argument("--debug", action="store_true",
                      help="prints the debug messages too")
  args = parser.parse_args()
  if args.debug:
    logger.setLevel(logging.DEBUG)
  input_path = Path(args.input_file)
  if args.output:
    output_path = Path(args.output)
  else:
    output_path = input_path.with_name(input_path.stem + "-parallel.json")
  if args.state:
    state_path = Path(args.state)
  else:
    state_path = input_path.with_name(input_path.stem + "-state.db")
  logger.info(f"Loading data from {input_path}")
  input_data = load_json(input_path)
  sm = StateManager(state_path)
  if args.reset or not state_path.exists():
    input_tasks = parse_input_data(input_data)
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
  logger.info(f"GPT models: {args.model}")
  redo_indexes = []
  if args.redo:
    try:
      redo_indexes = set(int(x.strip()) for x in args.redo.split(",") if x.strip())
      redo_indexes = list(reversed(sorted(list(redo_indexes))))
    except ValueError:
      logger.error(f"Invalid format for redo: {args.redo}")
  if redo_indexes:
    input_tasks = parse_input_data(input_data)
    for redo_index in redo_indexes:
      if redo_index < len(input_tasks):
        role, source_text = input_tasks[redo_index]
        print(index, role, source_text)
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
      short_source_text = cut_text_by_width(source_text, 64)
      logger.info(f"Task {index}: {role} - {short_source_text}")
      hint = get_hint(sm, index)
      prev_context = get_prev_context(sm, index)
      next_context = get_next_context(sm, index)
      if role == "macro":
        response = simulate_task_as_macro(source_text)
      else:
        response = execute_task_by_chatgpt_enja(
          book_title, role, source_text,
          hint, prev_context, next_context,
          args.model, args.failsoft, args.no_fallback,
        )
      sm.set_response(index, response)
      total_cost += response.get("cost", 0)
      done_tasks += 1
  except KeyboardInterrupt:
    logger.warning(f"Stop by Ctrl-C")
  logger.info(f"Done: tasks={done_tasks}, total_cost=${total_cost:.4f} (Y{total_cost*150:.2f})")
  index = sm.find_undone()
  if index < 0 or args.force_finish:
    input_data = load_json(input_path)
    tasks = sm.load_all()
    logger.info(f"Validating output")
    if not validate_tasks(tasks):
      raise RuntimeError("Validation failed")
    logger.info(f"Writing data into {output_path}")
    output_data = build_output(input_data, tasks)
    with open(output_path, "w", encoding="utf-8") as f:
      json.dump(output_data, f, ensure_ascii=False, indent=2)
    logger.info("Finished")
  else:
    logger.info("To be continued")


if __name__ == "__main__":
  main()

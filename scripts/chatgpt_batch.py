#!/usr/bin/env python3

import openai
import os
import sys
from datetime import datetime, UTC

openai.api_key = os.getenv("OPENAI_API_KEY")


def create_batch(input_jsonl):
  resp = openai.files.create(file=open(input_jsonl, "rb"), purpose="batch")
  batch = openai.batches.create(
    input_file_id=resp.id,
    endpoint="/v1/chat/completions",
    completion_window="24h"
  )
  print(f"created: {batch.id}")


def check_batch(batch_id):
  try:
    batch = openai.batches.retrieve(batch_id)
  except Exception as e:
    print("batch not found")
    sys.exit(1)
  print(f"status: {batch.status}")
  if batch.status == "failed":
    if batch.errors:
      print("errors:")
      for err in batch.errors:
        print(f"  {err}")
    else:
      print("No error details available.")


def save_batch(batch_id, output_path):
  batch = openai.batches.retrieve(batch_id)
  if batch.status != "completed":
    print("batch not completed yet")
    sys.exit(1)
  output_file_id = batch.output_file_id
  file_content = openai.files.content(output_file_id)
  with open(output_path, "wb") as f:
    f.write(file_content.read())
  print("done")


def cancel_batch(batch_id):
  try:
    batch = openai.batches.cancel(batch_id)
    print(f"canceled: {batch.id}")
  except Exception as e:
    print(f"cancel failed: {e}")
    sys.exit(1)


def list_batches():
  batches = list(openai.batches.list())
  if not batches:
    print("No batches found.")
    return
  print(f"{'batch_id':38}  {'status':12}  {'created_at':20}")
  for batch in batches:
    dt = datetime.fromtimestamp(batch.created_at, UTC).strftime('%Y-%m-%d %H:%M:%S')
    print(f"{batch.id:38}  {batch.status:12}  {dt}")


def list_models():
  models = openai.models.list()
  for model in models.data:
    print(model.id)


def main():
  if len(sys.argv) < 2:
    print("Usage:")
    print("  chatgpt_batch.py create <input.jsonl>")
    print("  chatgpt_batch.py check <batch_id>")
    print("  chatgpt_batch.py save <batch_id> <output.jsonl>")
    print("  chatgpt_batch.py cancel <batch_id>")
    print("  chatgpt_batch.py list")
    print("  chatgpt_batch.py models")
    sys.exit(1)
  cmd = sys.argv[1]
  if cmd == "create":
    if len(sys.argv) != 3:
      print("Usage: chatgpt_batch.py create <input.jsonl>")
      sys.exit(1)
    create_batch(sys.argv[2])
  elif cmd == "check":
    if len(sys.argv) != 3:
      print("Usage: chatgpt_batch.py check <batch_id>")
      sys.exit(1)
    check_batch(sys.argv[2])
  elif cmd == "save":
    if len(sys.argv) != 4:
      print("Usage: chatgpt_batch.py save <batch_id> <output.jsonl>")
      sys.exit(1)
    save_batch(sys.argv[2], sys.argv[3])
  elif cmd == "cancel":
    if len(sys.argv) != 3:
      print("Usage: chatgpt_batch.py cancel <batch_id>")
      sys.exit(1)
    cancel_batch(sys.argv[2])
  elif cmd == "list":
    list_batches()
  elif cmd == "models":
    list_models()
  else:
    print("Unknown command:", cmd)
    sys.exit(1)

if __name__ == "__main__":
  main()

#! /usr/bin/env python3

import argparse
import collections
import copy
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
import uuid
from pathlib import Path


PROG_NAME = "analyze_parallel_corpus.py"
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
MAX_TOKENS_IN_BATCH = 1000
MAX_SENTENCES_IN_BATCH = 16
ANALYZE_INSTRUCTIONS = """
あなたは英文法の構文解析の試験を受けている学生です。
減点を防ぐため、英文法の規則に厳密に従って答えてください。例外的な判断や分析を加えず、教科書的なルールや分類に忠実に構文要素を分類してください。
JSON形式で複数の英文とその対訳が与えられます。それぞれに要素について、英文"source"を文単位に分解し、各文について構文を解析し、結果をJSON形式で追加してください。
出力は、List[List[Object]] 形式で、第1層のリストの要素は入力の各要素に対応します。入力の各要素には複数の文が含まれている可能性があり、それを文単位で分解したものが第2層のリストの要素になります。第2層の各要素はオブジェクトであり、構文解析の結果を含みます。

```pseudo-json
[
  [
    {
      "format": "sentence",
      "text": "入力の第1要素の文字列から抽出した1つめの英文",
      "pattern": "SVOC", // 文型分類: SV, SVO, SVC, SVOO, SVOC, other
      "elements": [
        { "type": "S", "text": "...", "translation": "..." },  // 主語の語句または節
        { "type": "V", "text": "...", "translation": "...",    // 動詞の語句または節
          "tense": "...", "aspect": "...", "mood": "...", "voice": "..." },
        { "type": "O", "text": "...", "translation": "..." },  // 目的語の語句または節
        {
          "type": "C", "text": "...", "translation": "...",
          "subclauses": [  // その要素に従属節を含んでいれば記述
            "format": "clause",
            "relation": "...", // 従属節と主節の関係：apposition, cause, timeなど
            "pattern": "SVC",
            "elements": [
              { "type": "S", "text": "...", "translation": "..." },
              { "type": "V", "text": "...", "translation": "...",
                "tense": "...", "aspect": "...", "mood": "...", "voice": "..." },
              { "type": "C", "text": "...", "translation": "..." },
              { "type": "M", "text": "...", "translation": "..." }
            ]
          ]
        },
        {"type": "M", "text": "..."}                           // 修飾語の語句または節
      ],
      "subclauses": [  // 文全体の副詞節はここに記述
        "format": "clause",
        "text": "...",
        "relation": "...",
        "pattern": "SV",
        "elements": [
          { "type": "S", "text": "...", "translation": "..." },
          { "type": "V", "text": "...", "translation": "...",
            "tense": "...", "aspect": "...", "mood": "...", "voice": "..." }
        ]
      ]
    },
    {
      "format": "sentence",
      "text": "入力の第1要素の文字列から抽出した2つめの英文",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "...", "translation": "..." },
        { "type": "V", "text": "...", "translation": "...",
          "tense": "...", "aspect": "...", "mood": "...", "voice": "..." },
        { "type": "O", "text": "...", "translation": "..." }
      ],
      "subsentences": [
        {
          "format": "sentence",
          "text": "2つめの英文に含まれる副文",
          "pattern": "SV",
          "elements": [
            { "type": "S", "text": "...", "translation": "..." },
            { "type": "V", "text": "...", "translation": "...",
              "tense": "...", "aspect": "...", "mood": "...", "voice": "..." }
          ]
        }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "入力の第2要素から抽出した英文",
      "pattern": "SVOO",
      "elements": [
        { "type": "S", "text": "...", "translation": "..." },
        { "type": "V", "text": "...", "translation": "...",
          "tense": "...", "aspect": "...", "mood": "...", "voice": "..." },
        { "type": "O", "text": "...", "translation": "..." },
        { "type": "O", "text": "...", "translation": "..." }
      ]
    }
  ]
]
```

出力はJSONのみで、余計な装飾やブラケットは省いてください。
必ず "format": "sentence" を各文のトップに含め、全体はJSONの2次元配列で返してください。入力の配列の要素数と出力の第1層の配列の要素数は同じになります。
各文の本文は "text" 属性として表現してください。英字だけでなく、引用符や句読点も含めた全ての文字を複写してください。複写した文字列は原文から一切の変更をしないでください。
文や節の文型 "pattern" は、 以下のいずれかで示します。
- SV : 動詞が自動詞で、目的語も補語も取らない。例：I ran quickly.
- SVO : 動詞が他動詞で、目的語を1つ取る。例：You ate a big apple quickly.
- SVC : 動詞がbe動詞などのlinking動詞で、補語を1つ取る。例：He is a popular teacher.
- SVOO : 動詞が他動詞で、目的語を2つ取る。例：She gave him chocolate.
- SVOC : 動詞が他動詞で、目的語を1つと補語1つを取る。例：You make me happy.
- other : 動詞を含まず、上記の5つに当てはまらないもの。例：Nice to meet you.
文や節の文型を構成する要素は "element" の中に配列で示します。要素の種類 "type" は、S（主語）、V（動詞）、O（目的語）、C（補語）、M（修飾語）のいずれかで示します。
主語や目的語になれるのは、通常は名詞句だけです。補語になれるのは、通常は名詞句か形容詞句だけです。
名詞にかかる形容詞は名詞句に含めてください。動詞にかかる副詞は修飾語（M）として扱ってください。ただし、助動詞や句動詞は動詞句（V）に結合してください。倒置や慣用により位置が飛び飛びになっている動詞句も、結合して表現してください。
名詞にかかる不定詞句や動名詞句や前置詞句は形容詞句なので、それがかかる名詞と同じ要素に含めてください。動詞にかかる不定詞句や分詞構文や前置詞句は副詞句なので、修飾語として扱って下さい。
動詞句（V）には、"tense"（時制）と "aspect"（相）と "mood"（法）と "voice"（態）の分類を付けます。
"tense" は以下のものから選びます。
- present : 現在時制。例：I live in Tokyo.
- past : 過去時制。例：I lived in Tokyo.
"aspect" は以下のものから選びます。
- simple : 単純相。例：I live in Tokyo.
- progressive : 進行相。例：I'm living in Tokyo.
- perfect : 完了相。例：I've lived in Tokyo.
- perfect progressive : 完了進行相。例：I've been living in Tokyo.
"mood" は以下のものから選びます。
- indicative : 直説法。例：I run quickly.
- imperative : 命令法。例：Run quickly!
- subjunctive : 仮定法。例：If I were a bird, ...
- conditional : 条件法。I would fly to you.
"voice" は以下のものから選びます。
- active : 能動態。例：I picked up the flower.
- passive : 受動態。例：The flower was picked up by me.
- none : 態なし。動作ではない場合。例：I am Nancy.
各 "elements" オブジェクトには、構文要素の直訳を示す "translation" 属性を付加してください。これは "text" に対応する日本語訳であり、構文構成の意味を読解するための補助となります。翻訳は直訳調で構いません。入力の "target" を参考にしつつも、その要素の語句の辞書的な語義の範疇で最も文脈に合ったものを表現してください。
各 "element" の "text" の中にthat節、関係詞節、if節、whether節などの従属節が含まれる場合は、"subclauses" に分解して2階層目まで構文を分析してください。再帰させないでください。つまり、従属節の中の従属節は抽出しないでください。従属節として抽出した文字列も元の "text" に含めたままにして下さい。
文全体にかかる副詞節は、"elements" と並列の層に "subclauses" として抽出してください。
従属節の "relation" には、主節に対する従属節の関係を記述します。代表的な語彙は以下のものです。
- content : それ自体が名詞節で、動詞や形容詞の内容を表す節（that節など）。例：I heard that he won.
- apposition : 名詞を補足説明する同格節（that節など）。例：I know the news that he won.
- reason : 理由・原因を示す節（because節など）。例：I noticed it because it is red.
- condition : 条件を示す節（if節など）。例：I will buy it if it is cheap.
- supposition : 仮定を示す節（if節など）。例：If I were you, I would buy it.
- purpose : 目的を示す節（so that節など）。例：I stay here so that I can take care of him.
- result : 結果を示す節（so ... that節など）。例：It is so big that you can see it from here.
- contrast : 逆接・対比を示す節（although節など）。例：He bought it although it is expensive.
- concession : 譲歩を示す節（even if節など）。例：I'll go even if it rains.
- time : 時間を示す節（when節など）。例：I left home when the sun came up.
- place : 場所を示す節（where節など）。例：I live where the crime rate is low.
- manner : 様態・方法を示す節（as if節など）。例：He was sleeping as if he was dead.
- comparison : 比較を示す節（than節など）。例：She is taller than I am.
- extent : 程度を表す節（as節など）。例：She is as tall as he is.
節と句を区別してください。節とは主語と述語を含む文法構造であり、文型を持ちます。句はそうではありません。不定詞句や動名詞句は意味上の動詞を持ちますが、節にはならず、名詞句か形容詞句か副詞句になります。前置詞句は形容詞句か副詞句になります。
引用符を使った直接話法の副文を含む場合、"subsentences" に分解して2階層目まで構文を分析してください。再帰させないでください。つまり、副文の中の副文は抽出しないでください。副文として抽出した文字列も主文の "text" に含めたままにして下さい。
入力の "target" を構文解釈の参考として補助的に用いてください。意味的な整合性を高めるためのヒントとして使ってください。

典型的な入力例を示します。

```json
[
  {
    "source": "I studied hard because I wanted to pass, even though I was tired.",
    "target": "私は合格したかったので、一生懸命勉強しました。疲れていたにもかかわらず。"
  }
]
```

その出力例を示します。入力の配列の要素数が1つなので、それに対応して出力の第1層の配列の要素数は1つになります。また、入力の文が分解されなかったので、第2層の要素数も1つになります。

```json
[
  [
    {
      "format": "sentence",
      "text": "I studied hard because I wanted to pass, even though I was tired.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "studied", "translation": "勉強した",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "M", "text": "hard", "translation": "一生懸命に" },
        {
          "type": "M",
          "text": "even though I was tired", "translation": "疲れていたけれど",
          "subclauses": [
            {
              "format": "clause",
              "pattern": "SVC",
              "relation": "concession",
              "elements": [
                { "type": "M", "text": "even though", "translation": "〜だけれど" },
                { "type": "S", "text": "I", "translation": "私は" },
                { "type": "V", "text": "was", "translation": "状態だった",
                  "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "none" },
                { "type": "C", "text": "tired", "translation": "疲れた" }
              ]
            }
          ]
        }
      ],
      "subclauses": [
        {
          "format": "clause",
          "text": "because I wanted to pass",
          "pattern": "SVO",
          "relation": "cause",
          "elements": [
            { "type": "M", "text": "because", "translation": "なぜなら" },
            { "type": "S", "text": "I", "translation": "私は" },
            { "type": "V", "text": "wanted", "translation": "欲した",
              "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
            { "type": "O", "text": "to pass", "translation": "合格することを" }
          ]
        }
      ]
    }
  ]
]
```

2つの要素を含む入力例を示します。

```json
[
  {
    "source": "He loved linguistics.",
    "target": "彼は言語学を好んだ。"
  },
  {
    "source": "It gave him wisdom.",
    "target": "それは彼に知恵を与えた。"
  }
]
```

その出力例を示します。入力の配列の要素数が2つなので、それに対応して出力の第1層の配列の要素数は2つになります。また、入力の文が分解されなかったので、第2層の要素数は1つになります。

```json
[
  [
    {
      "format": "sentence",
      "text": "He loved linguistics.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "He", "translation": "彼は" },
        { "type": "V", "text": "loved", "translation": "好んだ",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "linguistics", "translation": "言語学を" }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "It gave him wisdom.",
      "pattern": "SVOO",
      "elements": [
        { "type": "S", "text": "It", "translation": "それは" },
        { "type": "V", "text": "gave", "translation": "与えた",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "him", "translation": "彼に" },
        { "type": "O", "text": "wisdom", "translation": "知恵を" }
      ]
    }
  ]
]
```

2つの要素のそれぞれが2つの文を含む入力例を示します。

```json
[
  {
    "source": "Go forward.  Be happy.",
    "target": "行け。幸せになれ。"
  },
  {
    "source": "Oh! That's great.",
    "target": "ああ。素晴らしい。"
  }
]
```

その出力例を示します。入力の配列の要素数が2つなので、それに対応して出力の第1層の配列の要素数は2つになります。また、入力の文が分解されたので、第2層の要素数はそれぞれ2つになります。

```json
[
  [
    {
      "format": "sentence",
      "text": "Go forward.",
      "pattern": "SV",
      "elements": [
        { "type": "V", "text": "Go", "translation": "行く",
          "tense": "present", "aspect": "simple", "mood": "imperative", "voice": "active" },
        { "type": "M", "text": "forward", "translation": "前に" }
      ]
    },
    {
      "format": "sentence",
      "text": "Be happy.",
      "pattern": "SVC",
      "elements": [
        { "type": "V", "text": "Be", "translation": "なれ",
          "tense": "present", "aspect": "simple", "mood": "imperative", "voice": "none" },
        { "type": "C", "text": "happy", "translation": "幸せに" }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "Oh!",
      "pattern": "other",
      "elements": [
        { "type": "M", "text": "Oh", "translation": "ああ" }
      ]
    },
    {
      "format": "sentence",
      "text": "That's great.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "That", "translation": "あれ" },
        { "type": "V", "text": "is", "translation": "状態である",
          "tense": "present", "aspect": "simple", "mood": "imperative", "voice": "none" },
        { "type": "C", "text": "great", "translation": "素晴らしい" }
      ]
    }

  ]
]
```

形式主語を含む入力例を示します。

```json
[
  {
    "source": "It is true that I am Japanese.",
    "target": "私が日本人だというのは本当だ。"
  }
]
```

その出力例を示します。形式主語 "it" と、その内容を示す "that" 節の両方を主語（S要素）として扱います。

```json
[
  [
    {
      "format": "sentence",
      "text": "It is true that I am Japanese.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "It", "translation": "それは" },
        { "type": "V", "text": "is", "translation": "状態だ",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "true", "translation": "真実の" },
        {
          "type": "S",
          "text": "that I am Japanese",
          "translation": "私が日本人であること",
          "subclauses": [
            {
              "format": "clause",
              "text": "that I am Japanese",
              "relation": "apposition",
              "pattern": "SVO",
              "elements": [
                { "type": "M", "text": "that", "translation": "〜であること" },
                { "type": "S", "text": "I", "translation": "私は" },
                { "type": "V", "text": "am", "translation": "存在だ",
                  "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
                { "type": "C", "text": "Japanese", "translation": "日本人という" }
              ]
            }
          ]
        }
      ]
    }
  ]
]
```

副文を含む入力例を示します。

```json
[
  {
    "source": "“Excuse me!”, shouted John.",
    "target": "「すみません！」とジョンは叫んだ。"
  },
  {
    "source": "Nancy was mumbling “Spiders are not insects...”",
    "target": "ナンシーは「蜘蛛は昆虫じゃないわ」と呟いていた。"
  }
]
```

その出力例を示します。倒置構文でも "elements" の要素は出現順ではなく、分かりやすい順番で良いです。副文は文として分割するのではなく、主文の属性 "subsentences" の要素として扱います。"text" の値には引用符も含めてください。副文の内容を主文の "text" から削除しないでください。

```json
[
  [
    {
      "format": "sentence",
      "text": "“Excuse me!”, shouted John.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "John", "translation": "ジョンは" },
        { "type": "V", "text": "shouted", "translation": "叫んだ",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "“Excuse me!”", "translation": "「すみません」と" }
      ],
      "subsentences": [
        {
          "format": "sentence",
          "text": "“Excuse me!”",
          "pattern": "SVO",
          "elements": [
            { "type": "V", "text": "Excuse", "translation": "許す",
              "tense": "present", "aspect": "simple", "mood": "imperative", "voice": "active" },
            { "type": "O", "text": "me", "translation": "私を" }
          ]
        }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "Nancy is mumbling “Spiders are not insects...”",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "Nancy", "translation": "ナンシーは" },
        { "type": "V", "text": "was mumbling", "translation": "呟いていた",
          "tense": "past", "aspect": "progressive", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "“Spiders are not insects...”", "translation": "「蜘蛛は昆虫ではない」と" }
      ],
      "subsentences": [
        {
          "format": "sentence",
          "text": "“Spiders are not insects...”",
          "pattern": "SVC",
          "elements": [
            { "type": "S", "text": "Spiders", "translation": "蜘蛛は" },
            { "type": "V", "text": "are not", "translation": "存在ではない",
              "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
            { "type": "C", "text": "insects", "translation": "昆虫という" }
          ]
        }
      ]
    }
  ]
]
```

関係代名詞節と関係副詞節を含む例を示します。

```json
[
  {
    "source": "John, who is a rich investor in 30s, lives in a house where many ghosts hide.",
    "target": "30代の裕福な投資家であるジョンは、多くの幽霊が隠れている屋敷に住んでいる。"
  }
]
```

その出力例を示します。関係詞節は "subclauses" として示して下さい。関係代名詞は従属節の中で主語や目的語になることが多く、関係副詞は従属節の中で副詞句になります。

```json
[
  [
    {
      "format": "sentence",
      "text": "John, who is a rich investor in 30s, lives in a house where many ghosts hide.",
      "pattern": "SV",
      "elements": [
        {
          "type": "S",
          "text": "John, who is a rich investor in 30s",
          "translation": "30代の裕福な投資家であるジョンは",
          "subclauses": [
            {
              "format": "clause",
              "text": "who is a rich investor in 30s",
              "relation": "apposition",
              "pattern": "SVC",
              "elements": [
                { "type": "S", "text": "who", "translation": "その人は" },
                { "type": "V", "text": "is", "translation": "である",
                  "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
                { "type": "C", "text": "a rich investor in 30s", "translation": "30代の裕福な投資家である" }
              ]
            }
          ]
        },
        { "type": "V", "text": "lives", "translation": "住んでいる" },
        {
          "type": "M",
          "text": "in a house where many ghosts hide",
          "translation": "多くの幽霊が隠れている屋敷に",
          "subclauses": [
            {
              "format": "clause",
              "text": "where many ghosts hide",
              "relation": "place",
              "pattern": "SV",
              "elements": [
                { "type": "M", "text": "where", "translation": "そこでは" },
                { "type": "S", "text": "many ghosts", "translation": "多くの幽霊が" },
                { "type": "V", "text": "hide", "translation": "隠れている",
                  "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" }
              ]
            }
          ]
        }
      ]
    }
  ]
]
```

文全体が引用符で囲まれている例を示します。

```json
[
  {
    "source": "“Did he make you mad?”",
    "target": "彼があなたを怒らせたのね？"
  }
]
```

その出力例を示します。全体が引用文の場合、その文を主文としてください。"text" で引用符は省略しないでください。助動詞と動詞は1つの動詞句として扱ってください。

```json
[
  [
    {
      "format": "sentence",
      "text": "“Did he make you mad?”",
      "pattern": "SVOC",
      "elements": [
        { "type": "S", "text": "John", "translation": "ジョンは" },
        { "type": "V", "text": "did make", "translation": "状態にさせた",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "you", "translation": "あなたを" },
        { "type": "C", "text": "mad", "translation": "怒った" }
      ]
    }
  ]
]
```

多様な副詞節を含む例を示します。

```json
[
  {
    "source": "When he saw her, he fell in love at once.",
    "target": "彼は彼女を一目見て恋に落ちた。"
  },
  {
    "source": "I'll go if you excuse me.",
    "target": "それでは失礼させていただきます。"
  },
  {
    "source": "They live where wild animals loiter.",
    "target": "彼らは野生動物が徘徊するところに住んでいる。"
  }
]
```

その出力例を示します。従属節は "subclauses" として抽出しますが、文の "text" から該当部分を取り除かないでください。文全体の副詞句である従属節は、文の直下の "subclauses" にします。その場合、主節の "elements" には該当部分を載せません。

```json
[
  [
    {
      "format": "sentence",
      "text": "When he saw her, he fell in love at once.",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "he", "translation": "彼は" },
        { "type": "V", "text": "fell", "translation": "落ちた",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "M", "text": "in love", "translation": "恋に" },
        { "type": "M", "text": "at once", "translation": "たちまち" }
      ],
      "subclauses": [
        {
          "format": "clause",
          "relation": "time",
          "text": "When he saw her",
          "pattern": "SVO",
          "elements": [
            { "type": "M", "text": "When", "translation": "〜の時に" },
            { "type": "S", "text": "he", "translation": "彼が" },
            { "type": "V", "text": "saw", "translation": "見た",
              "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
            { "type": "O", "text": "her", "translation": "彼女を" }
          ]
        }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "I'll go if you excuse me.",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "will go", "translation": "立ち去る",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" }
      ],
      "subclauses": [
        {
          "format": "clause",
          "relation": "condition",
          "text": "if you excuse me",
          "pattern": "SVO",
          "elements": [
            { "type": "M", "text": "if", "translation": "もし〜なら" },
            { "type": "S", "text": "you", "translation": "あなたが" },
            { "type": "V", "text": "excuse", "translation": "許す",
              "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
            { "type": "O", "text": "me", "translation": "私を" }
          ]
        }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "They live where wild animals loiter.",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "They", "translation": "彼らは" },
        { "type": "V", "text": "live", "translation": "住んでいる",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" }
      ],
      "subclauses": [
        {
          "format": "clause",
          "relation": "place",
          "text": "where wild animals loiter",
          "pattern": "SV",
          "elements": [
            { "type": "M", "text": "where", "translation": "〜の場所で" },
            { "type": "S", "text": "wild animals", "translation": "野生動物が" },
            { "type": "V", "text": "loiter", "translation": "徘徊する",
              "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" }
          ]
        }
      ]
    }
  ]
]
```

修飾語が多い例を示します。

```json
[
  {
    "source": "The pretty girl often loves different boys without specific reasons. We don't trust her. She is not trustable.",
    "target": "その魅力的な少女は頻繁に違う少年を特別な理由もなく愛する。しかし、私達は彼女を信用しない。彼女は信用できない。"
  }
]
```

その出力例を示します。主語に係る修飾語は "S" に含め、目的語に係る修飾語は "O" に含め、動詞にかかる修飾語は "M" として独立させます。"rather"、"often"、"little"、"seldom"、"significantly" などの副詞が動詞にかかっている場合は "M" として独立させます。一方、"not" や "never" は副詞ですが、動詞との結びつきが強いので、"V" に含めます。

```json
[
  [
    {
      "format": "sentence",
      "text": "The pretty girl often loves different boys without specific reasons.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "The pretty girl", "translation": "その魅力的な少女は" },
        { "type": "M", "text": "often", "translation": "頻繁に" },
        { "type": "V", "text": "loves", "translation": "愛する",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "different boys", "translation": "異なる少年を" },
        { "type": "M", "text": "without specific reasons", "translation": "特別な理由もなく" }
      ]
    },
    {
      "format": "sentence",
      "text": "We don't trust her.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "We", "translation": "私達は" },
        { "type": "V", "text": "don't trust", "translation": "信用しない",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "her", "translation": "彼女を" }
      ]
    },
    {
      "format": "sentence",
      "text": "She is not trustable.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "She", "translation": "彼女は" },
        { "type": "V", "text": "is not", "translation": "存在ではない",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "O", "text": "trustable", "translation": "信用できる" }
      ]
    }
  ]
]
```

群助動詞や句動詞を含む例を示します。"be going to"、"used to"、"have to"、"would like to" などが群助動詞です。"give up"、"come up with"、"get carried away" などが句動詞です。

```json
[
  {
    "source": "He ought not to give it up.",
    "target": "彼は諦めるべきではない。"
  }
]
```

その出力例を示します。群助動詞や句動詞も一連の動詞句として扱って下さい。

```json
[
  [
    {
      "format": "sentence",
      "text": "He ought not to give it up.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "He", "translation": "彼は" },
        { "type": "V", "text": "ought not to give up", "translation": "諦めるべきではない",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "it", "translation": "それを" }
      ]
    }
  ]
]
```

"come to" を含む例を示します。

```json
[
  {
    "source": "She came to love you. We've come to see you.",
    "target": "彼女は君を愛し始めた。我々は君に合うために来た。"
  }
]
```

"come to"、"get to" などを群助動詞として扱うべきかどうかは、文脈に応じて判断してください。

```json
[
  [
    {
      "format": "sentence",
      "text": "She came to love you.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "She", "translation": "彼女は" },
        { "type": "V", "text": "came to love", "translation": "愛し始めた",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "you", "translation": "君を" }
      ]
    },
    {
      "format": "sentence",
      "text": "We've come to see you.",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "We", "translation": "我々は" },
        { "type": "V", "text": "have come", "translation": "来た",
          "tense": "present", "aspect": "perfect", "mood": "indicative", "voice": "active" },
        { "type": "M", "text": "to see you", "translation": "君に会うために" }
      ]
    }
  ]
]
```

複雑な修飾関係のある例を示します。

```json
[
  {
    "source": "Our fathers brought forth on this continent a new nation conceived in Liberty",
    "target": "我々の先祖たちはこの大陸に新しい国をもたらしたが、その国は自由に構想され、すべての人間が平等に創造されたという命題に捧げられた。"
  }
]
```

その出力例を示します。副詞句は、VとOの間に挿入されても、Mとして扱ってください。長い名詞句でも分解しないでください。現在分詞や過去分詞が後置されて名詞句が長くなっていたとしても、それは句であって、節ではないので、"subclauses" にはしないでください。

```json
[
  [
    {
      "format": "sentence",
      "text": "Our fathers brought forth on this continent a new nation conceived in Liberty.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "Our fathers", "translation": "我々の先祖たち" },
        { "type": "V", "text": "brought forth", "translation": "もたらした",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "M", "text": "on this continent", "translation": "この大陸に" },
        { "type": "O", "text": "a new nation conceived in Liberty", "translation": "自由の下に構想された新しい国を"}
      ]
    }
  ]
]
```

多様な態（voice）や相（aspect）を含む例を示します。

```json
[
  {
    "source": "He was surprising everyone. He surprised me too. I was surprised by him. It was surprising. It made everyone surprised. Everyone was made surprised by it. Thus, I was suprised. I'd never been surprised before that.",
    "target": "彼は皆を驚かせていた。彼は私も驚かせた。私は彼に驚かされた。それは驚異的だった。それゆえ、私は驚いた。私はそれ以前は驚いたことがなかった。"
  }
]
```

その出力例を示します。be動詞に動詞の分詞が付いた形でも、動作を意味すれば受動態や進行相として動詞に含め、状態を意味すれば形容詞として補語に含めてください。能動態でSVOである文に対応する受動態の文はSVになり、能動態でSVOOである文に対応する受動態の文はSVOになり、能動態でSVOCである文に対応する受動態はSVCになります。

```json
[
  [
    {
      "format": "sentence",
      "text": "He was surprising everyone.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "He", "translation": "彼は" },
        { "type": "V", "text": "was surprising", "translation": "驚かせていた",
          "tense": "past", "aspect": "progressive", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "everyone", "translation": "皆を" }
      ]
    },
    {
      "format": "sentence",
      "text": "He surprised me too.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "He", "translation": "彼は" },
        { "type": "V", "text": "surprised", "translation": "驚かせた",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "me", "translation": "私を" },
        { "type": "M", "text": "too", "translation": "〜も" }
      ]
    },
    {
      "format": "sentence",
      "text": "I was surprised by him.",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "was surprised", "translation": "驚かされた",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "passive" },
        { "type": "M", "text": "by him", "translation": "彼によって" }
      ]
    },
    {
      "format": "sentence",
      "text": "It was surprising.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "It", "translation": "それは" },
        { "type": "V", "text": "was", "translation": "状態だった",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "surprising", "translation": "驚異的な" }
      ]
    },
    {
      "format": "sentence",
      "text": "It made everyone surprised.",
      "pattern": "SVOC",
      "elements": [
        { "type": "S", "text": "It", "translation": "それは" },
        { "type": "V", "text": "made", "translation": "状態にした",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "everyone", "translation": "皆を" },
        { "type": "C", "text": "surprised", "translation": "驚いた" }
      ]
    },
    {
      "format": "sentence",
      "text": "Everyone was made surprised by it.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "Everyone", "translation": "皆は" },
        { "type": "V", "text": "was made", "translation": "状態にされた",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "passive" },
        { "type": "C", "text": "surprised", "translation": "驚いた" },
        { "type": "M", "text": "by it", "translation": "それによって" }
      ]
    },
    {
      "format": "sentence",
      "text": "Thus, I was surprised.",
      "pattern": "SVC",
      "elements": [
        { "type": "M", "text": "Thus", "translation": "それゆえ" },
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "was", "translation": "状態だった",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "surprised", "translation": "驚いた" }
      ]
    },
    {
      "format": "sentence",
      "text": "I'd never been surprised before that.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "had never been", "translation": "一度も状態にならなかった",
          "tense": "past", "aspect": "perfect", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "surprised", "translation": "驚いた" },
        { "type": "M", "text": "before that", "translation": "それ以前に" }
      ]
    }
  ]
]
```

受動態の動詞を持つSV文型の例と、動詞の過去分詞由来の形容詞を持つSVC文型の例を示します。

```json
[
  {
    "source": "It is associated with many hints. We are engaged in a big trouble.",
    "target": "それらはたくさんのヒントと関連づけられている。我々は大きな問題に巻き込まれている。"
  }
]
```

その出力例を示します。述語を受動態とみなすなら、過去分詞はbe動詞と結合して動詞として扱います。述語を形容詞の叙述用法とみなすなら、be動詞だけを動詞として扱って過去分詞由来の形容詞は補語として扱います。いずれにせよ、前置詞句の副詞句は修飾語として扱います。受動態の動作主を表す "by" で始まる前置詞句も修飾語として扱います。

```json
[
  [
    {
      "format": "sentence",
      "text": "It is associated with many hints.",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "It", "translation": "それは" },
        { "type": "V", "text": "is associated", "translation": "関連付けられている",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "passive" },
        { "type": "M", "text": "with many hints", "translation": "たくさんのヒントに" }
      ]
    },
    {
      "format": "sentence",
      "text": "We are engaged in a big trouble.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "We", "translation": "我々は" },
        { "type": "V", "text": "are", "translation": "状態である",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "engaged", "translation": "巻き込まれた" },
        { "type": "M", "text": "in a big trouble", "translation": "大きな問題に" }
      ]
    }
  ]
]
```

分詞構文を含む例を示します。

```json
[
  {
    "source": "Living in Tokyo, we cannot avoid traffic congestion basically.",
    "target": "東京に住んでいるわけで、交通渋滞は避けられない。"
  }
]
```

その出力例を示します。文全体にかかる副詞句は修飾語として扱ってください。

```json
[
  [
    {
      "format": "sentence",
      "text": "Living in Tokyo, we cannot avoid traffic congestion basically.",
      "pattern": "SVO",
      "elements": [
        { "type": "M", "text": "Living in Tokyo", "translation": "東京に住んでいるので" },
        { "type": "S", "text": "we", "translation": "私達は" },
        { "type": "V", "text": "cannot avoid", "translation": "避けられない",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "traffic congestion", "translation": "交通渋滞を" },
        { "type": "M", "text": "basically", "translation": "基本的に" }
      ]
    }
  ]
]
```

不定詞句や前置詞句を含む例を示します。

```json
[
  {
    "source": "The girl to leave tomorrow was happy to join with you. The dog in the park now was in the cage yesterday.",
    "target": "明日出発する少女はあなたたちに加われて幸せだった。今公園を走っているその犬は昨日は檻の中に居た。"
  }
]
```

その出力例を示します。名詞に係る不定詞は名詞の要素に含め、動詞に係る不定詞は修飾語にします。名詞に係る前置詞句は名詞の要素に含め、動詞に係る前置詞句は修飾語にします。通常、前置詞句は単体では主語や目的語にはなり得ず、補語や副詞になるか、名詞に係って主語や目的語の一部になります。理由や結果や状況を表す前置詞句や不定詞句は動詞に係る副詞句になることが多いです。その場合、修飾語として動詞や補語からは独立させてください。

```json
[
  [
    {
      "format": "sentence",
      "text": "The girl to leave tomorrow was happy to join with you.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "The girl to leave tomorrow", "translation": "明日出発する少女" },
        { "type": "V", "text": "was", "translation": "状態だった",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "happy", "translation": "幸せな" },
        { "type": "M", "text": "to join with you", "translation": "あなた達に加わって" }
      ]
    },
    {
      "format": "sentence",
      "text": "The dog in the park now was in the cage yesterday.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "The dog in the park now", "translation": "今公園にいる犬" },
        { "type": "V", "text": "was", "translation": "存在した",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "in the cage", "translation": "檻の中に" },
        { "type": "M", "text": "yesterday", "translation": "昨日" }
      ]
    }
  ]
]
```

文型が "other" になる例を示します。

```json
[
  {
    "source": "Oh! Hello, Nancy. Yes, sir. How to win.",
    "target": "あら。こんにちはナンシー。承知しました。"
  }
]
```

その出力例を示します。文型（S, V, O, C）に直接関与しない感動詞や呼びかけ語などは修飾語として扱ってください。全体が名詞句や形容詞句や副詞句である場合も "other" にします。

```json
[
  [
    {
      "format": "sentence",
      "text": "Oh!",
      "pattern": "other",
      "elements": [
        { "type": "M", "text": "Oh", "translation": "あら" }
      ]
    },
    {
      "format": "sentence",
      "text": "Hello, Nancy.",
      "pattern": "other",
      "elements": [
        { "type": "M", "text": "Hello", "translation": "こんにちは" },
        { "type": "M", "text": "Nancy", "translation": "ナンシー" }
      ]
    },
    {
      "format": "sentence",
      "text": "Yes, sir.",
      "pattern": "other",
      "elements": [
        { "type": "M", "text": "Yes", "translation": "はい" },
        { "type": "M", "text": "sir", "translation": "旦那様" }
      ]
    },
    {
      "format": "sentence",
      "text": "How to win.",
      "pattern": "other",
      "elements": [
        { "type": "M", "text": "How to win", "translation": "勝つ方法" }
      ]
    }
  ]
]
```

命令法の例を示します。

```json
[
  {
    "source": "Let's go! Hey, do it now.",
    "target": "行きましょう！今すぐしろ。"
  }
]
```

その出力例を示します。命令法は主語が省略されていますが、隠れた主語が存在するとみなして文型を選択してください。

```json
[
  [
    {
      "format": "sentence",
      "text": "Let's go!",
      "pattern": "SVOC",
      "elements": [
        { "type": "V", "text": "Let", "translation": "仕向ける",
          "tense": "present", "aspect": "simple", "mood": "imperative", "voice": "active" },
        { "type": "O", "text": "us", "translation": "私達が" },
        { "type": "C", "text": "go", "translation": "行くように" }
      ]
    },
    {
      "format": "sentence",
      "text": "Hey, do it now.",
      "pattern": "SVO",
      "elements": [
        { "type": "M", "text": "Hey", "translation": "おい" },
        { "type": "V", "text": "do", "translation": "しろ",
          "tense": "present", "aspect": "simple", "mood": "imperative", "voice": "active" },
        { "type": "O", "text": "it", "translation": "それを" },
        { "type": "M", "text": "now", "translation": "今すぐ" }
      ]
    }
  ]
]
```

仮定法と条件法の例を示します。

```json
[
  {
    "source": "If I were a bird, I would fly to you. If I had been an adult at the time, I could have married him.",
    "target": "もし私が鳥なら、あなたのもとに飛んでいくのに。もし私が当時大人だったら、彼と結婚できたのに。"
  }
]
```

その出力例を示します。条件法の主節や仮定法の条件節は動詞の表層形が過去方向にずれますが、"tense" と "aspect" の値はその表層形ではなく深層の意味に基づいて決めてください。つまり、仮定法や条件法において、動詞句が過去形である場合、"tense" は "present" になり、動詞句が過去完了形である場合、"tense" は "past" になります。意味が完了相でない場合、"aspect" は "simple" にします。

```json
[
  [
    {
      "format": "sentence",
      "text": "If I were a bird, I would fly to you.",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "would fly", "translation": "飛ぶ",
          "tense": "present", "aspect": "simple", "mood": "conditional", "voice": "active" },
        { "type": "M", "text": "to you", "translation": "あなたに" }
      ],
      "subclauses": [
        {
          "format": "clause",
          "text": "If I were a bird",
          "relation": "condition",
          "pattern": "SVC",
          "elements": [
            { "type": "M", "text": "If", "translation": "もし" },
            { "type": "S", "text": "I", "translation": "私が" },
            { "type": "V", "text": "were", "translation": "存在である",
              "tense": "present", "aspect": "simple", "mood": "subjunctive", "voice": "none" },
            { "type": "C", "text": "a bird", "translation": "鳥" }
          ]
        }
      ]
    },
    {
      "format": "sentence",
      "text": "If I had been an adult at the time, I could have married him.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "could have married", "translation": "結婚できた",
          "tense": "past", "aspect": "simple", "mood": "conditional", "voice": "active" },
        { "type": "O", "text": "him", "translation": "彼と" }
      ],
      "subclauses": [
        {
          "format": "clause",
          "text": "If I had been an adult at the time",
          "relation": "condition",
          "pattern": "SVC",
          "elements": [
            { "type": "M", "text": "If", "translation": "もし" },
            { "type": "S", "text": "I", "translation": "私が" },
            { "type": "V", "text": "had been", "translation": "存在であった",
              "tense": "past", "aspect": "simple", "mood": "subjunctive", "voice": "none" },
            { "type": "C", "text": "an adult", "translation": "大人" },
            { "type": "M", "text": "at the time", "translation": "当時" }
          ]
        }
      ]
    }
  ]
]
```

"would", "could", "should" が現在時制で用いられる例を示します。

```json
[
  {
    "source": "I would rather say that he's right.",
    "target": "私はむしろ彼が正しいと言いたいくらいだ。"
  },
  {
    "source": "Could you pass me the salt?",
    "target": "塩を取ってくれますか。"
  },
  {
    "source": "You should do it yourself.",
    "target": "自分でやりなさいよ。"
  }
]
```

その出力例を示します。"would", "could", "should" が現在時制で用いられている場合、過去時制ではなく、現在時制の条件法として扱ってください。

```json
[
  [
    {
      "format": "sentence",
      "text": "I would rather say that he's right.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "would say", "translation": "言うだろう",
          "tense": "present", "aspect": "simple", "mood": "conditional", "voice": "active" },
        { "type": "M", "text": "rather", "translation": "むしろ" },
        { "type": "O", "text": "that he's right", "translation": "彼は正しい",
          "subclauses": [
            {
              "format": "clause",
              "pattern": "SVC",
              "relation": "content",
              "elements": [
                { "type": "S", "text": "he", "translation": "彼は" },
                { "type": "V", "text": "is", "translation": "状態だ",
                  "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
                { "type": "C", "text": "right", "translation": "正しい" }
              ]
            }
          ]
        }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "Could you pass me the salt?",
      "pattern": "SVOO",
      "elements": [
        { "type": "S", "text": "you", "translation": "あなたは" },
        { "type": "V", "text": "Could pass", "translation": "渡せるか",
          "tense": "present", "aspect": "simple", "mood": "conditional", "voice": "active" },
        { "type": "O", "text": "me", "translation": "私に" },
        { "type": "O", "text": "the salt", "translation": "その塩を" }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "You should do it yourself.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "you", "translation": "あなたは" },
        { "type": "V", "text": "should do", "translation": "すべきである",
          "tense": "present", "aspect": "simple", "mood": "conditional", "voice": "active" },
        { "type": "O", "text": "it", "translation": "それを" },
        { "type": "M", "text": "yourself", "translation": "自分で" }
      ]
    }
  ]
]
```

句動詞の判別のための例を示します。

```json
[
  {
    "source": "Nancy came up with the plan on the double.",
    "target": "ナンシーは大急ぎでその計画を考えた。"
  },
  {
    "source": "John graduated from the school in two years.",
    "target": "ジョンは2年でその学校を卒業した。"
  }
]
```

その出力例を示します。"come up" 単体だと意味を成さないので、"come up with" を他動詞の句動詞とみなして扱います。一方で、"graduate" は単体で意味を成すので、"from" 以降は分離して副詞句の前置詞句のとして扱います。また、動詞に係る前置詞句は副詞句として要素に分けます。

```json
[
  [
    {
      "format": "sentence",
      "text": "Nancy came up with the plan on the double.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "Nancy", "translation": "ナンシーは" },
        { "type": "V", "text": "came up with", "translation": "考案した",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "the plan", "translation": "その計画を" },
        { "type": "M", "text": "on the double", "translation": "大急ぎで" }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "John graduated from the school in two years.",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "John", "translation": "ジョンは" },
        { "type": "V", "text": "graduated", "translation": "卒業した",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "M", "text": "from the school", "translation": "その学校から" },
        { "type": "M", "text": "in two years", "translation": "2年間で" }
      ]
    }
  ]
]
```

不定詞句を多く含む例を示します。

```json
[
  {
    "source": "I want to run to lose weight.",
    "target": "体重を落とすために走りたい。"
  },
  {
    "source": "She bought a knife to cut paper to decorate the room.",
    "target": "彼女は部屋を飾るために、髪を切るナイフを買った。"
  },
  {
    "source": "The bike is to commute; It's a bike to commute. I'm glad to have it.",
    "target": "その二輪車は通勤用だ。それは通勤用の二輪車だ。私はそれを持てて嬉しい。"
  }
]
```

その出力例を示します。"want" などに続く不定詞句は名詞句の目的語なので独立した要素になります。目的語ではなく動詞にかかる不定詞は副詞句として独立した要素になります。名詞にかかる不定詞は形容詞句として名詞の要素に含めます。形容詞句として補語そのものになる不定詞句もありますし、名詞である補語にかかる不定詞句もあります。補語の原因や帰結を示す不定詞は副詞句として独立させます。

```json
[
  [
    {
      "format": "sentence",
      "text": "I want to run to lose weight.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "want", "translation": "欲する",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "to run", "translation": "走ることを" },
        { "type": "M", "text": "to lose weight", "translation": "痩せるために" }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "She bought a knife to cut paper to decorate the room.",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "She", "translation": "彼女は" },
        { "type": "V", "text": "bought", "translation": "買った",
          "tense": "past", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "a knife to cut paper", "translation": "紙を切るためのナイフを" },
        { "type": "M", "text": "to decorate the room", "translation": "部屋を飾るために" }
      ]
    }
  ],
  [
    {
      "format": "sentence",
      "text": "The bike is to commute;",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "The bike", "translation": "その二輪車は" },
        { "type": "V", "text": "is", "translation": "存在である",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "to commute", "translation": "通勤するための" }
      ]
    },
    {
      "format": "sentence",
      "text": "It's a bike to commute.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "It", "translation": "それは" },
        { "type": "V", "text": "is", "translation": "存在である",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "O", "text": "a bike to commute", "translation": "通勤用の自転車" }
      ]
    },
    {
      "format": "sentence",
      "text": "I'm glad to have it.",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "am", "translation": "状態である",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "glad", "translation": "嬉しい" },
        { "type": "M", "text": "to have it", "translation": "それを持てて" }
      ]
    }
  ]
]
```

2つの文が接続詞で結合された例を示します。

```json
[
  {
    "source": "I love chocolate but it makes me fat.",
    "target": "私はチョコレートが好きだが、それは私を太らせる。"
  }
]
```

その出力例を示します。文を分けて解釈するのが自然である場合、第1階層の要素として分けて記述してください。

```json
[
  [
    {
      "format": "sentence",
      "text": "I love chocolate",
      "pattern": "SVO",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "love", "translation": "好きだ",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "chocolate", "translation": "チョコレートが" }
      ]
    },
    {
      "format": "sentence",
      "text": "but it makes me fat.",
      "pattern": "SVOC",
      "elements": [
        { "type": "M", "text": "but", "translation": "しかし" },
        { "type": "S", "text": "it", "translation": "それは" },
        { "type": "V", "text": "makes", "translation": "状態にする",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" },
        { "type": "O", "text": "me", "translation": "私を" },
        { "type": "C", "text": "fat", "translation": "太った" }
      ]
    }
  ]
]
```

2つの文が接続詞で結合されて、かつ主語が省略された例を示します。

```json
[
  {
    "source": "I'm a boxer so can't run away.",
    "target": "私はボクサーなので、逃げるわけにはいかない。"
  }
]
```

その出力例を示します。省略がある場合には、省略を補った上で文型を推定してください。文を分割して複数の要素を出力する場合、"text" の内容が重複しないようにしてください。各要素の "text" を結合すると元の文の "source" に一致する必要があります。

```json
[
  [
    {
      "format": "sentence",
      "text": "I'm a boxer",
      "pattern": "SVC",
      "elements": [
        { "type": "S", "text": "I", "translation": "私は" },
        { "type": "V", "text": "am", "translation": "である",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "none" },
        { "type": "C", "text": "a boxer", "translation": "ボクサーである" }
      ]
    },
    {
      "format": "sentence",
      "text": "so can't run away.",
      "pattern": "SV",
      "elements": [
        { "type": "M", "text": "so", "translation": "だから" },
        { "type": "V", "text": "can't run away", "translation": "逃げられない",
          "tense": "present", "aspect": "simple", "mood": "indicative", "voice": "active" }
      ]
    }
  ]
]
```

"pattern" が示す文型と "elements" の各要素の "type" の対応関係には注意して下さい。文型が "SV" の場合、"type" は "S" と "V" が存在する必要があり、"O" や "C" は存在してはいけません。文型が "SVO" の場合、"S" と "V" と "O" が存在し、"C" は存在してはいけません。文型が "SVC" の場合、"S" と "V" と "C" が存在し、"O" は存在してはいけません。文型が "SVOO" の場合、"S" と "V" と "O" 2つが存在し、"C" は存在してはいけません。文型が "SVOC" の場合、"S" と "V" と "O" と "C" が存在する必要があります。"M" はどの文型でいくつ存在しても構いません。そうしないと減点されます。
副詞節は "subclauses" として独立させてください。副詞句は "elements" として独立させてください。副詞句である不定詞句や前置詞句は、動詞や補語からは分離してください。そうしないと減点されます。
"""


logging.basicConfig(format="%(message)s", stream=sys.stderr)
logger = logging.getLogger(PROG_NAME)
logger.setLevel(logging.INFO)


def validate_content(content, pairs):
  if type(content) != list:
    raise ValueError("Not a list")
  for item in content:
    validate_sentence_content(item)
  if pairs is not None:
    if len(content) != len(pairs):
      raise ValueError("Invalid size of the output list")
    def normalize_text(text):
      return regex.sub(r"\s+", " ", text).lower().strip()
    for item, pair in zip(content, pairs):
      norm_orig = normalize_text(pair["source"])
      norm_first = normalize_text(item[0]["text"])
      short_orig = norm_orig[:len(norm_first)]
      if short_orig[:3] != norm_first[:3]:
        raise ValueError(f"Inconsistent text {short_orig} vs {norm_first}")
      distance = Levenshtein.distance(short_orig, norm_first)
      length = max(1, (len(short_orig) + len(norm_first)) / 2)
      diff = distance / length
      if diff > 0.1:
        raise ValueError(f"Too much diff {short_orig} vs {norm_first}")
      if norm_orig == norm_first and len(item) > 1 and item[0]["text"] == item[1]["text"]:
        raise ValueError(f"Duplicated texts: {short_orig}")


def validate_sentence_content(content):
  def check_sentence(sentence, fmt):
    if type(sentence) != dict:
      raise ValueError("Not a dict")
    if sentence.get("format") != fmt:
      raise ValueError(f"Not a {fmt} format")
    if not sentence.get("text"):
      raise ValueError("No text")
    if not sentence.get("pattern"):
      raise ValueError("No pattern")
    elements = sentence.get("elements")
    if type(elements) != list:
      raise ValueError("Not elements list")
    for element in elements:
      if type(element.get("type")) != str:
        raise ValueError("Invalid element type")
      if type(element.get("text")) != str:
        raise ValueError("Invalid element text")
    for subclause in sentence.get("subclauses") or []:
      check_sentence(subclause, "clause")
    for subsentence in sentence.get("subsentences") or []:
      check_sentence(subsentence, "sentence")
  if type(content) != list:
    raise ValueError("Not a list")
  for sentence in content:
    check_sentence(sentence, "sentence")


def validate_instruction(text):
  results = []
  json_blocks = regex.findall(r'```json(.*?)```', text, regex.DOTALL)
  for idx, block in enumerate(json_blocks):
    block_stripped = block.strip()
    try:
      data = json.loads(block_stripped)
    except json.JSONDecodeError as e:
      logger.warning(f"Invalid instruction: {e}\n{block}")
      raise ValueError("Instruction: invalid JSON")
    if type(data) != list:
      logger.warning(f"Invalid instruction: not list\n{block}")
      raise ValueError("Instruction: invalid JSON")
    if not data:
      logger.warning(f"Invalid instruction: empty list\n{block}")
      raise ValueError("Instruction: invalid JSON")
    if "source" in data[0]:
      if not "target" in data[0]:
        logger.warning(f"Invalid instruction: no target\n{block}")
        raise ValueError("Instruction: invalid JSON")
    else:
      try:
        validate_content(data, None)
      except ValueError as e:
        logger.warning(f"Invalid instruction: {e}\n{block}")
        raise ValueError("Instruction: invalid JSON")


class StateManager:
  def __init__(self, db_path):
    self.db_path = db_path

  def initialize(self, requests):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
          idx INTEGER PRIMARY KEY,
          request TEXT,
          response TEXT
        )
      ''')
      cur.execute('DELETE FROM tasks')
      for i, request in enumerate(requests):
        request_json = json.dumps(request, separators=(',', ':'), ensure_ascii=False)
        cur.execute(
          'INSERT INTO tasks (idx, request) VALUES (?, ?)', (i, request_json)
        )
      conn.commit()

  def load(self, index):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('SELECT idx, request, response FROM tasks WHERE idx = ?',
                  (index,))
      row = cur.fetchone()
      if row:
        return {
          "index": row[0],
          "request": json.loads(row[1]) if row[1] is not None else None,
          "response": json.loads(row[2]) if row[2] is not None else None
        }
      return None

  def reset_task(self, index, request):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      request_json = json.dumps(request, separators=(',', ':'), ensure_ascii=False)
      cur.execute('UPDATE tasks SET request = ?, response = NULL'
                  ' WHERE idx = ?',
                  (request_json, index))
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
      cur.execute('SELECT idx, request, response FROM tasks ORDER BY idx ASC')
      rows = cur.fetchall()
      return [
        {
          "index": row[0],
          "request": json.loads(row[1]) if row[1] is not None else None,
          "response": json.loads(row[2]) if row[2] is not None else None
        } for row in rows
      ]


def load_input_data(path):
  with open(path, encoding="utf-8") as f:
    data = json.load(f)
  if data.get("format") != "parallel":
    raise ValueError("Not parallel book data")
  pairs = []
  def add_pair(obj):
    pairs.append((obj["source"], obj["target"]))
  book_title = data.get("title")
  if book_title:
    add_pair(book_title)
  book_author = data.get("author")
  if book_author:
    add_pair(book_author)
  for chapter_index, chapter in enumerate(data.get("chapters", [])):
    chapter_title = chapter.get("title")
    if chapter_title:
      add_pair(chapter_title)
    for element in chapter.get("body") or []:
      for name in ["header", "paragraph", "blockquote", "list", "table"]:
        value = element.get(name)
        if type(value) == dict:
          add_pair(value)
        elif type(value) == list:
          for item in value:
            if type(item) == dict:
              add_pair(item)
            elif type(item) == list:
              for cell in item:
                add_pair(cell)
  return data, pairs


def read_batch_output_data(path):
  records = {}
  with open(path, encoding="utf-8") as f:
    line_num = 0
    for line in f:
      line_num += 1
      try:
        data = json.loads(line)
      except Exception as e:
        logger.warning(f"invalid batch data: line={line_num}: {e}")
        continue
      custom_id = data.get("custom_id")
      if not custom_id: continue
      match = regex.search(r"-(\d+)$", custom_id)
      if not match: continue
      task_index = int(match.group(1))
      response = data.get("response")
      if not response: continue
      body = response.get("body")
      if not body: continue
      usage = body.get("usage")
      if not usage: continue
      choices = body.get("choices")
      if not choices: continue
      message = choices[0].get("message")
      if not message: continue
      content = message.get("content")
      if not content: continue
      match = regex.search(r'```(?:json)?\s*([{\[].*?[}\]])\s*```', content, regex.DOTALL)
      if match:
        content = match.group(1)
      try:
        content = json.loads(content)
      except Exception:
        content = []
      record = {
        "index": task_index,
        "content": content,
        "usage": usage,
      }
      records[task_index] = record
  return records


def count_chatgpt_tokens(text):
  encoding = tiktoken.get_encoding("cl100k_base")
  tokens = encoding.encode(text)
  return len(tokens)


def calculate_chatgpt_cost(prompt, response, model):
  for name, input_cost, output_cost in CHATGPT_MODELS:
    if name == model:
      num_input_tokens = count_chatgpt_tokens(prompt)
      num_output_tokens = count_chatgpt_tokens(response)
      total_cost = num_input_tokens / 1000 * input_cost + num_output_tokens / 1000* output_cost
      logger.debug(f"Cost: {total_cost:.6f} ({num_input_tokens/1000:.3f}*{input_cost}+{num_output_tokens/1000:.3f}*{output_cost})")
      return total_cost
  raise RuntimeError("No matching model")


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


def make_tasks(input_pairs):
  tasks = []
  task_tokens = 0
  task_items = 0
  for source, target in input_pairs:
    item_tokens = count_chatgpt_tokens(source)
    if (not tasks or
        (task_tokens > 0 and task_tokens + item_tokens > MAX_TOKENS_IN_BATCH) or
        (task_items > 0 and task_items >= MAX_SENTENCES_IN_BATCH)):
      tasks.append([])
      task_tokens = 0;
      task_items = 0
    tasks[-1].append({"source": source, "target": target})
    task_tokens += item_tokens
    task_items += 1
  return tasks


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


def make_prompt(pairs, attempt, extra_hint, use_source_example):
  lines = []
  def p(line):
    lines.append(line)
  p(ANALYZE_INSTRUCTIONS.strip())
  p("----")
  p("以下の情報をもとに、インストラクションの指示に従って構文解析を行ってください。")
  p("----")
  p(json.dumps(pairs, ensure_ascii=False, indent=2))
  if use_source_example:
    p("----")
    p("出力例を示します。")
    example = []
    for pair in pairs:
      source = pair["source"]
      items = []
      sentences = split_sentences_english(source)
      for sentence in sentences:
        item = {
          "format": "sentence",
          "text": sentence,
          "pattern": "...",
          "elements": [
            {"type": "...", "text": "...", "translation": "..."},
            {"type": "...", "text": "...", "translation": "...",
             "tense": "...", "aspect": "...", "mood": "...", "voice": "..."},
          ]
        }
        items.append(item)
      example.append(items)
    p(json.dumps(example, ensure_ascii=False, indent=2))
  extra_hint = extra_hint.strip()
  if extra_hint:
    p("----")
    p(extra_hint)
  return "\n".join(lines)


def execute_task(request, main_model, failsoft, no_fallback, extra_hint, batch_response):
  pairs = []
  void_pairs = collections.defaultdict(list)
  for item in request:
    source = item["source"]
    target = item["target"]
    latins = regex.sub(r"[^\p{Latin}]", "", source)
    pair = {
      "source": source,
      "target": target,
    }
    if len(latins) < 2:
      void_pairs[len(pairs)].append(pair)
    else:
      pairs.append(pair)
  models = [main_model]
  if not no_fallback:
    sub_model = None
    for name, _, _ in CHATGPT_MODELS:
      if name != main_model:
        models.append(name)
        break
  valid_content = None
  valid_cost = 0
  for model in models:
    if not pairs: break
    if valid_content: break
    configs = [(0.0, False), (0.0, True),
               (0.4, False), (0.4, True),
               (0.8, False), (0.8, True)]
    for attempt, (temp, use_source_example) in enumerate(configs, 1):
      if attempt == 1 and batch_response:
        try:
          content = batch_response["content"]
          usage = batch_response["usage"]
          texts = []
          for item in content:
            for sentence in item:
              texts.append(sentence["text"])
          short_text = cut_text_by_width(" ".join(texts), 80)
          logger.info(f"Reusing: {short_text}")
          logger.debug(f"Usage:\n{usage}")
          logger.debug(f"Response:\n{content}")
          validate_content(content, pairs)
          valid_content = content
          break
        except Exception as e:
          logger.info(f"Attempt {attempt} failed (batch): {e}")
          time.sleep(0.2)
          continue
      prompt = make_prompt(pairs, attempt, extra_hint, use_source_example)
      logger.debug(f"Prompt:\n{prompt}")
      try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY).with_options(timeout=300)
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
        content = json.loads(response)
        validate_content(content, pairs)
        valid_content = content
        valid_cost = round(calculate_chatgpt_cost(prompt, response, model), 8)
        break
      except Exception as e:
        logger.info(f"Attempt {attempt} failed (model={model},"
                    f" temperature={temp}, x={use_source_example}): {e}")
        time.sleep(0.2)
  if pairs and not valid_content:
    if failsoft:
      logger.warning(f"Failsoft: dummy data is generated")
      for pair in pairs:
        void_pairs[0].append({
          "source": "[*FAILSOFT*]",
          "target": "[*FAILSOFT*]",
        })
      valid_content = []
    else:
      raise RuntimeError("All retries failed: unable to parse valid JSON with required fields")
  def make_dummy_content(void_item):
    source = void_item["source"]
    target = void_item["target"]
    item = {
      "format": "sentence",
      "text": source,
      "pattern": "other",
      "elements": [
        {
          "type": "M",
          "text": source,
          "translation": target,
        }
      ]
    }
    return [item]
  merged_content = []
  for index, item in enumerate(valid_content):
    void_items = void_pairs.get(index)
    if void_items:
      for void_item in void_items:
        merged_content.append(make_dummy_content(void_item))
    merged_content.append(item)
  void_items = void_pairs.get(len(valid_content))
  if void_items:
    for void_item in void_items:
      merged_content.append(make_dummy_content(void_item))
  record = {
    "content": merged_content,
    "cost": valid_cost,
  }
  return record


def postprocess_sentence(sentence, index):
  pattern = sentence["pattern"]
  text = sentence["text"]
  elem_types = collections.defaultdict(int)
  new_elements = []
  for element in sentence["elements"]:
    if not element["text"].strip(): continue
    new_elements.append(element)
    elem_types[element["type"]] += 1
  sentence["elements"] = new_elements
  if "V" in elem_types:
    if "O" in elem_types:
      if "C" in elem_types:
        if pattern != "SVOC":
          sentence["pattern"] = "SVOC"
          logger.debug(f"pattern corrected: {pattern} -> SVOC : task={index}: {text}")
      else:
        if elem_types.get("O") >= 2:
          if pattern != "SVOO":
            sentence["pattern"] = "SVOO"
            logger.debug(f"pattern corrected: {pattern} -> SVOO : task={index}: {text}")
        else:
          if pattern != "SVO":
            sentence["pattern"] = "SVO"
            logger.debug(f"pattern corrected: {pattern} -> SVO : task={index}: {text}")
    elif "C" in elem_types:
      if pattern != "SVC":
        sentence["pattern"] = "SVC"
        logger.debug(f"pattern corrected: {pattern} -> SVC : task={index}: {text}")
    else:
      if pattern != "SV":
        sentence["pattern"] = "SV"
        logger.debug(f"pattern corrected: {pattern} -> SV : task={index}: {text}")


def postprocess_tasks(tasks):
  for task in tasks:
    index = task["index"]
    request = task["request"]
    response = task.get("response")
    if not response: continue
    for item, req_item in zip(response["content"], request):
      source = req_item["source"]
      if len(item) == 2:
        first, second = item
        if first["text"] == source and first["text"].endswith(second["text"]):
          short_text = first["text"][0:-len(second["text"])].rstrip()
          if len(short_text) >= 3:
            first["text"] = short_text
      for sentence in item:
        postprocess_sentence(sentence, index)
        for subclause in sentence.get("subclauses") or []:
          postprocess_sentence(subclause, index)
        for subsentence in sentence.get("subsentences") or []:
          postprocess_sentence(subsentence, index)


def validate_tasks(tasks):
  for task in tasks:
    index = task["index"]
    request = task["request"]
    response = task.get("response")
    if not response: continue
    content = response["content"]
    try:
      validate_content(content, request)
    except Exception as e:
      logger.warning(f"invalid task data: index={index}: {e}")
      return False
  return True


def build_output(data, tasks):
  depot = collections.defaultdict(list)
  for task in tasks:
    index = task["index"]
    request = task["request"]
    response = task.get("response")
    if not response:
      logger.warning(f"Stop by an unprocessed task: {index}")
      break
    for seq, (req_item, res_item) in enumerate(zip(request, response["content"])):
      index_seq = f"{index:05d}-{seq:03d}"
      source = req_item["source"]
      depot[source].append((index_seq, res_item))
  def normalize_sentence(sentence):
    del sentence["format"]
    for subclause in sentence.get("subclauses") or []:
      del subclause["format"]
    for subsentence in sentence.get("subsentences") or []:
      del subsentence["format"]
  def add_result(element):
    source = element["source"]
    results = depot.get(source)
    if results:
      depot[source] = results[1:]
      index_seq, content = results[0]
      content = content.copy()
      for i, sentence in enumerate(content):
        new_sentence = {
          "id": f"{index_seq}-{i:03d}",
        }
        for name, value in sentence.items():
          new_sentence[name] = value
        content[i] = new_sentence
      element["analysis"] = content
  book_title = data.get("title")
  if book_title:
    add_result(book_title)
  book_author = data.get("author")
  if book_author:
    add_result(book_author)
  for chapter_index, chapter in enumerate(data.get("chapters", [])):
    chapter_title = chapter.get("title")
    if chapter_title:
      add_result(chapter_title)
    for element in chapter.get("body") or []:
      for name in ["header", "paragraph", "blockquote", "list", "table"]:
        value = element.get(name)
        if type(value) == dict:
          add_result(value)
        elif type(value) == list:
          for item in value:
            if type(item) == dict:
              add_result(item)
            elif type(item) == list:
              for cell in item:
                add_result(cell)
  return data


def make_batch_input(tasks, model, extra_hint, input_stem):
  batch_input = []
  input_stem = regex.sub(r"[^\w]", "", input_stem).strip()[:16].strip()
  if not input_stem:
    input_stem = "book"
  custom_id_prefix = ("analyze-parallel-corpus-" + input_stem +
                      "-" + regex.sub(r"-", "", str(uuid.uuid4())))
  for index, task in enumerate(tasks):
    prompt = make_prompt(task, 1, extra_hint, False)
    item = {
      "method": "POST",
      "url": "/v1/chat/completions",
      "body": {
        "messages": [
          {"role": "user", "content": prompt},
        ],
        "model": "gpt-4.1-mini",
      },
      "custom_id": custom_id_prefix + f"-{index:05d}",
    }
    batch_input.append(item)
  return batch_input


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
  parser.add_argument("--make-batch-input", action="store_true",
                      help="outputs JSONL data to input onto the batch API")
  parser.add_argument("--use-batch-output", default=None,
                      help="uses JSONL data from the batch API")
  parser.add_argument("--debug", action="store_true",
                      help="prints the debug messages too")
  args = parser.parse_args()
  if args.debug:
    logger.setLevel(logging.DEBUG)
  input_path = Path(args.input_file)
  input_stem = regex.sub(r"-(parallel|analyzed)", "", input_path.stem)
  if args.output:
    output_path = Path(args.output)
  elif args.make_batch_input:
    output_path = input_path.with_name(input_stem + "-batch-input-analyze.jsonl")
  else:
    output_path = input_path.with_name(input_stem + "-analyzed.json")
  if args.state:
    state_path = Path(args.state)
  else:
    state_path = input_path.with_name(input_stem + "-state-analyze.db")
  batch_output_path = None
  if args.use_batch_output:
    if args.use_batch_output == "auto":
      batch_output_path = input_path.with_name(input_stem + "-batch-output-analyze.jsonl")
    else:
      batch_output_path = args.use_batch_output
  logger.info(f"Loading data from {input_path}")
  input_data, input_pairs = load_input_data(input_path)
  tasks = make_tasks(input_pairs)
  if args.make_batch_input:
    batch_input = make_batch_input(tasks, args.model, args.extra_hint, input_stem)
    logger.info(f"Total tasks: {len(batch_input)}")
    num_tokens = 0
    cost = 0
    for item in batch_input:
      for message in item["body"]["messages"]:
        num_tokens += count_chatgpt_tokens(message["content"])
        cost += calculate_chatgpt_cost(message["content"], "", args.model) / 2
    logger.info(f"Total tokens: {num_tokens}")
    logger.info(f"Total input cost: ${cost:.4f} (Y{cost*150:.2f})")
    logger.info(f"Writing batch input data into {output_path}")
    with open(output_path, "w") as f:
      for batch_item in batch_input:
        f.write(json.dumps(batch_item, ensure_ascii=False) + "\n")
    logger.info("Finished")
    return
  batch_output_data = None
  if batch_output_path:
    logger.info(f"Reading batch output data from {batch_output_path}")
    batch_output_data = read_batch_output_data(batch_output_path)
    input_tokens = 0
    output_tokens = 0
    for index, record in batch_output_data.items():
      usage = record["usage"]
      input_tokens += usage.get("prompt_tokens", 0)
      output_tokens += usage.get("completion_tokens", 0)
    logger.info(
      f"Batch info: tasks={len(batch_output_data)}, input_tokens={input_tokens},"
      f" output_tokens={output_tokens}")
  sm = StateManager(state_path)
  if args.reset or not state_path.exists():
    sm.initialize(tasks)
  total_tasks = sm.count()
  logger.info(f"Total tasks: {total_tasks}")
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
      if redo_index < len(tasks):
        request = tasks[redo_index]
        sm.reset_task(redo_index, request)
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
      request = record["request"]
      short_source_text = " ".join([x["source"] for x in record["request"]])
      short_source_text = regex.sub(r"\s+", " ", short_source_text).strip()
      short_source_text = cut_text_by_width(short_source_text, 80)
      logger.info(f"Task {index}: {short_source_text}")
      batch_response = None
      if batch_output_data:
        batch_response = batch_output_data.get(index)
      response = execute_task(
        request, args.model, args.failsoft, args.no_fallback, args.extra_hint, batch_response)
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
    output_data = build_output(input_data, tasks)
    with open(output_path, "w", encoding="utf-8") as f:
      print(json.dumps(output_data, ensure_ascii=False, indent=2), file=f)
    logger.info("Finished")
  else:
    logger.info("To be continued")


if __name__ == "__main__":
  validate_instruction(ANALYZE_INSTRUCTIONS)
  main()

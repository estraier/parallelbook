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
from pathlib import Path


PROG_NAME = "analyze_parallel_corpus.py"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHATGPT_MODELS = [
  # model name, input token cost (USD/1K), output token cost (USD/1K)
  ("gpt-3.5-turbo", 0.0005, 0.0015),
  ("gpt-4o", 0.005, 0.015),
  ("gpt-4-turbo", 0.01, 0.03),
  ("gpt-4", 0.03, 0.06),
]
ANALYZE_INSTRUCTIONS = """
あなたは英文の構文解析を行っている言語学者です。
JSON形式で与えられた英文"source"を文単位に分解し、各文について構文を解析し、結果をJSON形式で記述してください。
出力は List[Object] 形式で、各要素が1文に対応します。
各文の構文記述は以下の要素を含んでください：

```json
[
  {
    "format": "sentence",
    "text": "入力の文字列から抽出した1つめの英文",
    "pattern": "SVOC", // 文型分類: SV, SVO, SVC, SVOO, SVOC, other
    "elements": [
      { "type": "S", "text": "...", "translation": "..." },  // 主語の語句または節
      { "type": "V", "text": "...", "translation": "..." },  // 動詞の語句または節
      { "type": "O", "text": "...", "translation": "..." },  // 目的語の語句または節
      {
        "type": "C", "text": "...", "translation": "...",
        "subclauses": [  // その要素に従属節を含んでいれば記述
          "format": "clause",
          "relation": "...", // 従属節と主節の関係：apposition, cause, timeなど
          "conjunction": "...", // 接続詞：that, because, as, when, although, if, even thoughなど
          "pattern": "SVC",
          "elements": [
            { "type": "S", "text": "...", "translation": "..." },
            { "type": "V", "text": "...", "translation": "..." },
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
      "conjunction": "...",
      "pattern": "SV",
      "elements": [
        { "type": "S", "text": "...", "translation": "..." },
        { "type": "V", "text": "...", "translation": "..." }
      ]
    ]
  },
  {
    "format": "sentence",
    "text": "入力の文字列から抽出した2つめの英文",
    "pattern": "SV",
    "elements": [
      { "type": "S", "text": "...", "translation": "..." },
      { "type": "V", "text": "...", "translation": "..." },
      { "type": "O", "text": "...", "translation": "..." }
    ],
    "subsentences": [
      {
        "format": "sentence",
        "text": "2つめの英文に含まれる副文",
        "pattern": "SV",
        "elements": [
          { "type": "S", "text": "...", "translation": "..." },
          { "type": "V", "text": "...", "translation": "..." }
        ]
      }
    ]
  }
]
```

出力はJSON配列のみで、余計な装飾やブラケットは省いてください。
必ず "format": "sentence" を各文のトップに含め、全体はJSON配列で返してください。
各文の本文は "text" 属性として表現してください。英字だけでなく、引用符や句読点も含めた全ての文字を複写してください。複写した文字列は原文から一切の変更をしないでください。
文や節の文型 "pattern" は、 SV、SVO、SVC、SVOO、SVOC、other のいずれかで示します。
文や節の文型を構成する要素は "element" の中に配列で示します。要素の種類 "type" は、S（主語）、V（動詞）、O（目的語）、C（補語）、M（修飾語）のいずれかで示します。
名詞にかかる形容詞は名詞句に含めてください。動詞にかかる副詞は修飾語（M）として扱ってください。ただし、助動詞や句動詞は動詞句（V）に結合してください。倒置や慣用により位置が飛び飛びになっている動詞句も、結合して表現してください。
名詞にかかる不定詞句や動名詞句や前置詞句は形容詞句なので、それがかかる名詞と同じ要素に含めてください。動詞にかかる不定詞句や分詞構文や前置詞句は副詞句なので、修飾語として扱って下さい。
各 "elements" オブジェクトには、構文要素の直訳を示す "translation" 属性を付加してください。これは "text" に対応する日本語訳であり、構文構成の意味を読解するための補助となります。翻訳は直訳調で構いません。入力の "target" を参考にしつつも、その要素の語句の辞書的な語義の範疇で最も文脈に合ったものを表現してください。
各 "element" の "text" の中にthat節、関係詞節、if節、whether節などの従属節が含まれる場合は、"subclauses" に分解して2階層目まで構文を分析してください。再帰は最大1段階までにして、従属節の中の従属節は抽出しないでください。従属節として抽出した文字列も元の "text" に含めたままにして下さい。
文全体にかかる副詞節は、"elements" と並列の層に "subclauses" として抽出してください。
従属節の "relation" には、主節に対する従属節の関係を記述します。代表的な語彙は以下のものです。
- content : 動詞や形容詞の内容を表す節（that節など）
- apposition : 名詞を補足説明する同格節（that節など）
- reason : 理由・原因を示す節（because節など）
- condition : 条件を示す節（if節など）
- purpose : 目的を示す節（so that節など）
- result : 結果を示す節（so ... that節など）
- contrast : 逆接・対比を示す節（although節など）
- time : 時間を示す節（when節など）
- place : 場所を示す節（where節など）
- manner : 様態・方法を示す節（as if節など）
- comparison : 比較を示す節（than節など）
- concession : 譲歩を示す節（even if節など）
引用符を使った直接話法の副文を含む場合、"subsentences" に分解して2階層目まで構文を分析してください。再帰は最大1段階までにして、副文の中の副文は抽出しないでください。副文として抽出した文字列も主文の "text" に含めたままにして下さい。
入力の "target" を構文解釈の参考として補助的に用いてください。意味的な整合性を高めるためのヒントとして使ってください。

典型的な入力例を示します。

```json
{
  "source": "I studied hard because I wanted to pass, even though I was tired.",
  "target": "私は合格したかったので、一生懸命勉強しました。疲れていたにもかかわらず。"
}
```

その出力例を示します。

```json
[
  {
    "format": "sentence",
    "text": "I studied hard because I wanted to pass, even though I was tired.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "I", "translation": "私は" },
      { "type": "V", "text": "studied", "translation": "勉強した" },
      { "type": "O", "text": "hard", "translation": "一生懸命に" },
      {
        "type": "M",
        "text": "even though I was tired", "translation": "疲れていたけれど",
        "subclauses": [
          {
            "format": "clause",
            "pattern": "SVC",
            "conjunction": "even though",
            "relation": "concession",
            "elements": [
              { "type": "S", "text": "I", "translation": "私は" },
              { "type": "V", "text": "was", "translation": "状態だった" },
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
        "conjunction": "because",
        "relation": "cause",
        "elements": [
          { "type": "S", "text": "I", "translation": "私は" },
          { "type": "V", "text": "wanted", "translation": "欲した" },
          { "type": "O", "text": "to pass", "translation": "合格することを" }
        ]
      }
    ]
  }
]
```

2つの文を含む入力例を示します。

```json
{
  "source": "He loved linguistics. It gave him wisdom.",
  "target": "彼は言語学を好んだ。それは彼に知恵を与えた。"
}
```

その出力例を示します。

```json
[
  {
    "format": "sentence",
    "text": "He loved linguistics.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "He", "translation": "彼は" },
      { "type": "V", "text": "loved", "translation": "好んだ" },
      { "type": "O", "text": "linguistics", "translation": "言語学を" }
    ]
  },
  {
    "format": "sentence",
    "text": "It gave him wisdom.",
    "pattern": "SVOO",
    "elements": [
      { "type": "S", "text": "It", "translation": "それは" },
      { "type": "V", "text": "gave", "translation": "与えた" },
      { "type": "O", "text": "him", "translation": "彼に" },
      { "type": "O", "text": "wisdom", "translation": "知恵を" }
    ]
  }
]
```

形式主語を含む入力例を示します。

```json
{
  "source": "It is true that I am Japanese."
  "target": "私が日本人だというのは本当だ。"
}
```

その出力例を示します。形式主語 "it" と、その内容を示す "that" 節の両方を主語（S要素）として扱います。

```json
[
  {
    "format": "sentence",
    "text": "It is true that I am Japanese.",
    "pattern": "SVC",
    "elements": [
      { "type": "S", "text": "It", "translation": "それは" },
      { "type": "V", "text": "is", "translation": "状態だ" },
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
            "conjunction": "that",
            "pattern": "SVO",
            "elements": [
              { "type": "S", "text": "I", "translation": "私は" },
              { "type": "V", "text": "am", "translation": "存在だ" },
              { "type": "C", "text": "Japanese", "translation": "日本人という" }
            ]
          }
        ]
      }
    ]
  }
]
```

副文を含む入力例を示します。

```json
{
  "source": "“Excuse me!”, shouted John.",
  "target": "「すみません！」とジョンは叫んだ。"
}
```

その出力例を示します。倒置構文でも "elements" の要素は出現順ではなく、分かりやすい順番で良いです。

```json
[
  {
    "format": "sentence",
    "text": "“Excuse me!”, cried John.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "John", "translation": "ジョンは" },
      { "type": "V", "text": "shouted", "translation": "叫んだ" },
      { "type": "O", "text": "“Excuse me!”", "translation": "「すみません」と" }
    ],
    "subsentences": [
      {
        "format": "sentence",
        "text": "Excuse me!",
        "pattern": "SV",
        "elements": [
          { "type": "V", "text": "Excuse", "translation": "許す" },
          { "type": "O", "text": "me", "translation": "私を" }
        ]
      }
    ]
  }
]
```

関係代名詞節と関係副詞節を含む例を示します。

```json
{
  "source": "John, who is a rich investor in 30s, lives in a house where many ghosts hide.",
  "target": "30代の裕福な投資家であるジョンは、多くの幽霊が隠れている屋敷に住んでいる。"
}
```

その出力例を示します。関係詞節は "subclauses" として示して下さい。

```json
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
          "conjunction": "who",
          "pattern": "SVC",
          "elements": [
            { "type": "S", "text": "who", "translation": "その人は" },
            { "type": "V", "text": "is", "translation": "である" },
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
          "conjunction": "where",
          "pattern": "SV",
          "elements": [
            { "type": "S", "text": "many ghosts", "translation": "多くの幽霊が" },
            { "type": "V", "text": "hide", "translation": "隠れている" }
          ]
        }
      ]
    }
  ]
}
```

文全体が引用符で囲まれている例を示します。

```json
{
  "source": "“Did he make you mad?”",
  "target": "彼があなたを怒らせたのね？"
}
```

その出力例を示します。全体が引用文の場合、その文を主文としてください。"text" で引用符は省略しないでください。助動詞と動詞は1つの動詞句として扱ってください。

```json
[
  {
    "format": "sentence",
    "text": "“Did he make you mad?”",
    "pattern": "SVOC",
    "elements": [
      { "type": "S", "text": "John", "translation": "ジョンは" },
      { "type": "V", "text": "did make", "translation": "状態にさせた" },
      { "type": "O", "text": "you", "translation": "あなたを" },
      { "type": "C", "text": "mad", "translation": "怒った" }
    ]
  }
]
```

修飾語が多い例を示します。


```json
{
  "source": "The pretty girl often loves different boys without specific reasons.",
  "target": "その魅力的な少女は頻繁に違う少年を特別な理由もなく愛する。"
}
```

その出力例を示します。主語に係る修飾語は "S" に含め、目的語に係る修飾語は "O" に含め、動詞にかかる修飾語は "M" として独立させます。"rather"、"often"、"little"、"seldom"、"significantly" などの副詞が動詞にかかっている場合は "M" として独立させます。一方、"not" や "never" は副詞ですが、動詞との結びつきが強いので、"V" に含めます。

```json
[
  {
    "format": "sentence",
    "text": The pretty girl often loves different boys without specific reasons.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "The pretty girl", "translation": "その魅力的な少女は" },
      { "type": "M", "text": "often", "translation": "頻繁に" },
      { "type": "V", "text": "loves", "translation": "愛する" },
      { "type": "O", "text": "different boys", "translation": "異なる少年を" }
      { "type": "M", "text": "without specific reasons", "translation": "特別な理由もなく" }
    ]
  }
]
```

群助動詞や句動詞を含む例を示します。"be going to"、"used to"、"have to"、"would like to" などが群助動詞です。"give up"、"come up with"、"get carried away" などが句動詞です。

```json
{
  "source": "He ought not to give it up.",
  "target": "彼は諦めるべきではない。"
}
```

その出力例を示します。群助動詞や句動詞も一連の動詞句として扱って下さい。

```json
[
  {
    "format": "sentence",
    "text": "He ought not to give it up.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "He", "translation": "彼は" },
      { "type": "V", "text": "ought not to give up", "translation": "諦めるべきではない" },
      { "type": "O", "text": "it", "translation": "それを" }
    ]
  }
]
```

"come to" を含む例を示します。

```json
{
  "source": "She came to love you. We've come to see you.",
  "target": "彼女は君を愛し始めた。我々は君に合うために来た。"
}
```

"come to"、"get to" などを群助動詞として扱うべきかどうかは、文脈に応じて判断してください。

```json
[
  {
    "format": "sentence",
    "text": "She came to love you.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "She", "translation": "彼女は" },
      { "type": "V", "text": "came to love", "translation": "愛し始めた" },
      { "type": "O", "text": "you", "translation": "君を" }
    ]
  },
  {
    "format": "sentence",
    "text": "We've come to see you.",
    "pattern": "SV",
    "elements": [
      { "type": "S", "text": "We", "translation": "我々は" },
      { "type": "V", "text": "have come", "translation": "来た" },
      { "type": "M", "text": "to see you", "translation": "君に会うために" }
    ]
  }
]
```

複雑な修飾関係のある例を示します。

```json
{
  "source": "Our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal.",
  "target": "我々の先祖たちはこの大陸に新しい国をもたらしたが、その国は自由に構想され、すべての人間が平等に創造されたという命題に捧げられた。"
}
```

その出力例を示します。副詞句は、VとOの間に挿入されても、Mとして扱ってください。長い名詞句でも分解しないでください。

```json
[
  {
    "format": "sentence",
    "text": "Our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "Our fathers", "translation": "我々の先祖たち" },
      { "type": "V", "text": "brought forth", "translation": "もたらした" },
      { "type": "M", "text": "on this content", "translation": "この大陸に" },
      { "type": "O", "text": "a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal.",
        "translation": "自由の下に構想されて、全ての人間が平等に作られたという命題に捧げられた、新しい国を",
        "subclauses": [
          {
            "format": "clause",
            "text": "that all men are created equal",
            "relation": "content",
            "conjunction": "that",
            "pattern": "SVC",
            "elements": [
              { "type": "S", "text": "all men", "translation": "すべての人間は" },
              { "type": "V", "text": "are created", "translation": "創造された" },
              { "type": "C", "text": "equal", "translation": "平等に" }
            ]
          }
        ]
      },
    ]
  }
]
```

多様な態（voice）や相（aspect）を含む例を示します。

```json
{
  "source": "He was surprising everyone. He surprised me too. I was surprised by him. It was surprising. Thus, I was suprised. I'd never been surprised before that.",
  "target": "彼は皆を驚かせていた。彼は私も驚かせた。私は彼に驚かされた。それは驚異的だった。それゆえ、私は驚いた。私はそれ以前は驚いたことがなかった。"
}
```

その出力例を示します。be動詞に動詞の屈折形が付いた形でも、動作を意味すれば受動態や進行相として動詞に含め、状態を意味すれば形容詞として補語に含めてください。

```json
[
  {
    "format": "sentence",
    "text": "He was surprising everyone.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "He", "translation": "彼は" },
      { "type": "V", "text": "was surprising", "translation": "驚かせていた" },
      { "type": "O", "text": "everyone", "translation": "皆を" }
    ]
  },
  {
    "format": "sentence",
    "text": "He surprised me too.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "He", "translation": "彼は" },
      { "type": "V", "text": "surprised", "translation": "驚かせた" },
      { "type": "O", "text": "me", "translation": "私を" },
      { "type": "M", "text": "too", "translation": "〜も" }
    ]
  },
  {
    "format": "sentence",
    "text": "I was surprised by him.",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "I", "translation": "私は" },
      { "type": "V", "text": "was surprised", "translation": "驚かされた" },
      { "type": "O", "text": "by him", "translation": "彼によって" }
    ]
  },
  {
    "format": "sentence",
    "text": "It was surprising.",
    "pattern": "SVC",
    "elements": [
      { "type": "S", "text": "It", "translation": "それは" },
      { "type": "V", "text": "was", "translation": "状態だった" },
      { "type": "C", "text": "surprising", "translation": "驚異的な" }
    ]
  },
  {
    "format": "sentence",
    "text": "Thus, I was surprised.",
    "pattern": "SVC",
    "elements": [
      { "type": "M", "text": "Thus", "translation": "それゆえ" },
      { "type": "S", "text": "I", "translation": "私は" },
      { "type": "V", "text": "was", "translation": "状態だった" },
      { "type": "C", "text": "surprised", "translation": "驚いた" }
    ]
  },
  {
    "format": "sentence",
    "text": "I'd never been surprised before that.",
    "pattern": "SVC",
    "elements": [
      { "type": "S", "text": "I", "translation": "私は" },
      { "type": "V", "text": "had never been", "translation": "一度も状態にならなかった" },
      { "type": "C", "text": "surprised", "translation": "驚いた" },
      { "type": "M", "text": "before that", "translation": "それ以前に" }
    ]
  }
]
```

分詞構文を含む例を示します。

```json
{
  "source": "Living in Tokyo, we cannot avoid traffic congestion basically.",
  "target": "東京に住んでいるわけで、交通渋滞は避けられない。"
}
```

その出力例を示します。文全体にかかる副詞句は修飾語として扱ってください。

```json
[
  {
    "format": "sentence",
    "text": "Living in Tokyo, we cannot avoid traffic congestion basically.",
    "pattern": "SVO",
    "elements": [
      { "type": "M", "text": "Living in Tokyo", "translation": "東京に住んでいるので" },
      { "type": "S", "text": "we", "translation": "私達は" },
      { "type": "V", "text": "cannot avoid", "translation": "避けられない" },
      { "type": "O", "text": "traffic congestion", "translation": "交通渋滞を" },
      { "type": "M", "text": "basically", "translation": "基本的に" }
    ]
  }
]
```

文型が "other" になる例を示します。

```json
{
  "source": "Oh! Hello, Nancy. Yes, sir. How to win.",
  "target": "あら。こんにちはナンシー。承知しました。"
}
```

その出力例を示します。文型（S, V, O, C）に直接関与しない感動詞や呼びかけ語などは修飾語として扱ってください。全体が名詞句や形容詞句や副詞句である場合も "other" にします。

```json
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
```

命令法の例を示します。

```
{
  "source": "Let's go! Hey, do it now.",
  "target": "行きましょう！今すぐしろ。"
}
```

その出力例を示します。命令法は主語が省略されていますが、隠れた主語が存在するとみなして文型を選択してください。

```json
[
  {
    "format": "sentence",
    "text": "Let's go!",
    "pattern": "SVOC",
    "elements": [
      { "type": "V", "text": "Let", "translation": "仕向ける" },
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
      { "type": "V", "text": "do", "translation": "しろ" },
      { "type": "O", "text": "it", "translation": "それを" },
      { "type": "M", "text": "now", "translation": "今すぐ" }
    ]
  }
]
```

2つの文が接続詞で結合された例を示します。

```json
{
  "source": "I love chocolate but it makes me fat.",
  "target": "私はチョコレートが好きだが、それは私を太らせる。"
}
```

その出力例を示します。文を分けて解釈するのが自然である場合、第1階層の要素として分けて記述してください。

```json
[
  {
    "format": "sentence",
    "text": "I love chocolate",
    "pattern": "SVO",
    "elements": [
      { "type": "S", "text": "I", "translation": "私は" },
      { "type": "V", "text": "love", "translation": "好きだ" },
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
      { "type": "V", "text": "makes", "translation": "状態にする" },
      { "type": "O", "text": "me", "translation": "私を" },
      { "type": "C", "text": "fat", "translation": "太った" }
    ]
  }
]
```

2つの文が接続詞で結合されて、かつ主語が省略された例を示します。

```json
{
  "source": "I'm a boxer so can't run away",
  "target": "私はボクサーなので、逃げるわけにはいかない。"
}
```

その出力例を示します。省略がある場合には、省略を補った上で文型を推定してください。

```json
[
  {
    "format": "sentence",
    "text": "I'm a boxer",
    "pattern": "SVC",
    "elements": [
      { "type": "S", "text": "I", "translation": "私は" },
      { "type": "V", "text": "am", "translation": "である" },
      { "type": "C", "text": "a boxer", "translation": "ボクサーである" }
    ]
  },
  {
    "format": "sentence",
    "text": "so can't run away.",
    "pattern": "SV",
    "elements": [
      { "type": "M", "text": "so", "translation": "だから" },
      { "type": "V", "text": "can't run away", "translation": "逃げられない" }
    ]
  }
]
```

"pattern" が示す文型と "elements" の各要素の "type" の対応関係には注意して下さい。文型が "SV" の場合、"type" は "S" と "V" が存在する必要があり、"O" や "C" は存在してはいけません。文型が "SVO" の場合、"S" と "V" と "O" が存在し、"C" は存在してはいけません。文型が "SVC" の場合、"S" と "V" と "C" が存在し、"O" は存在してはいけません。文型が "SVOO" の場合、"S" と "V" と "O" 2つが存在し、"C" は存在してはいけません。文型が "SVOC" の場合、"S" と "V" と "O" と "C" が存在する必要があります。"M" はどの文型でいくつ存在しても構いません。
"""


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
          source_text TEXT,
          target_text TEXT,
          response TEXT
        )
      ''')
      cur.execute('DELETE FROM tasks')
      for i, (source_text, target_text) in enumerate(input_tasks):
        cur.execute(
          'INSERT INTO tasks (idx, source_text, target_text) VALUES (?, ?, ?)',
          (i, source_text, target_text)
        )
      conn.commit()

  def load(self, index):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('SELECT idx, source_text, target_text, response FROM tasks WHERE idx = ?',
                  (index,))
      row = cur.fetchone()
      if row:
        return {
          "index": row[0],
          "source_text": row[1],
          "target_text": row[2],
          "response": json.loads(row[3]) if row[3] is not None else None
        }
      return None

  def reset_task(self, index, source_text, target_text):
    with sqlite3.connect(self.db_path) as conn:
      cur = conn.cursor()
      cur.execute('UPDATE tasks SET source_text = ?, target_text = ?, response = NULL'
                  ' WHERE idx = ?',
                  (source_text, target_text, index))
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
      cur.execute('SELECT idx, source_text, target_text, response FROM tasks ORDER BY idx ASC')
      rows = cur.fetchall()
      return [
        {
          "index": row[0],
          "source_text": row[1],
          "target_text": row[2],
          "response": json.loads(row[3]) if row[3] is not None else None
        } for row in rows
      ]


def load_input_data(path):
  with open(path, encoding="utf-8") as f:
    data = json.load(f)
  if data.get("format") != "parallel":
    raise ValueError("Not parallel book data")
  tasks = []
  def add_task(obj):
    tasks.append((obj["source"], obj["target"]))
  book_title = data.get("title")
  if book_title:
    add_task(book_title)
  book_author = data.get("author")
  if book_author:
    add_task(book_author)
  for chapter_index, chapter in enumerate(data.get("chapters", [])):
    chapter_title = chapter.get("title")
    if chapter_title:
      add_task(chapter_title)
    for element in chapter.get("body") or []:
      for name in ["header", "paragraph", "blockquote", "list", "table"]:
        value = element.get(name)
        if type(value) == dict:
          add_task(value)
        elif type(value) == list:
          for item in value:
            if type(item) == dict:
              add_task(item)
            elif type(item) == list:
              for cell in item:
                add_task(cell)
  return data, tasks


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


def make_prompt(source_text, target_text, attempt, extra_hint, use_source_example):
  lines = []
  def p(line):
    lines.append(line)
  p(ANALYZE_INSTRUCTIONS.strip())
  p("----")
  p("以下の情報をもとに、インストラクションの指示に従って構文解析を行ってください。")
  p("----")
  input_data = {
    "source": source_text,
  }
  if target_text:
    input_data["target"] = target_text
  p(json.dumps(input_data, ensure_ascii=False, indent=2))
  if use_source_example:
    p("----")
    p("出力例を示します。")
    sentences = split_sentences_english(source_text)
    example = []
    for sentence in sentences:
      item = {
        "format": "sentence",
        "text": sentence,
        "pattern": "...",
        "elements": [
          {"type": "...", "text": "...", "translation": "..."},
        ]
      }
      example.append(item)
    p(json.dumps(example, ensure_ascii=False, indent=2))
  extra_hint = extra_hint.strip()
  if extra_hint:
    p("----")
    p(extra_hint)
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
  return True


def execute_task(source_text, target_text, main_model, failsoft, no_fallback, extra_hint):
  latins = regex.sub(r"[^\p{Latin}]", "", source_text)
  if len(latins) < 2:
    logger.debug(f"Not English: intact data is generated")
    record = {}
    content = []
    content.append({
      "format": "sentence",
      "text": source_text,
      "pattern": "other",
      "elements": [
        {"type": "M", "text": source_text},
      ],
    })
    record["content"] = content
    record["intact"] = True
    record["cost"] = 0
    return record
  models = [main_model]
  if not no_fallback:
    sub_model = None
    for name, _, _ in CHATGPT_MODELS:
      if name != main_model:
        models.append(name)
        break
  for model in models:
    configs = [(0.0, False), (0.0, True),
               (0.4, False), (0.4, True),
               (0.8, False), (0.8, True)]
    for attempt, (temp, use_source_example) in enumerate(configs, 1):
      prompt = make_prompt(source_text, target_text, attempt, extra_hint, use_source_example)
      logger.debug(f"Prompt:\n{prompt}")
      try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY).with_options(timeout=30)
        response = client.chat.completions.create(
          model=model,
          messages=[{ "role": "user", "content": prompt }],
          temperature=temp,
        ).choices[0].message.content
        match = regex.search(r'```(?:json)?\s*([{\[].*?[}\]])\s*```', response, regex.DOTALL)
        if match:
          response = match.group(1)
        response = regex.sub(r',\s*([\]}])', r'\1', response)
        logger.debug(f"Response:\n{response}")
        record = {}
        content = json.loads(response)
        record["content"] = content
        record["cost"] = round(calculate_chatgpt_cost(prompt, response, model), 8)
        if not validate_content(source_text, content):
          raise ValueError("Validation error")
        return record
      except Exception as e:
        logger.info(f"Attempt {attempt} failed (model={model},"
                    f" temperature={temp}, x={use_source_example}): {e}")
        time.sleep(0.2)
  if failsoft:
    logger.warning(f"Failsoft: dummy data is generated")
    record = {}
    content = []
    content.append({
      "format": "sentence",
      "text": source_text,
      "pattern": "other",
      "elements": [
        {"type": "M", "text": "[*FAILSOFT*]"},
      ],
    })
    record["content"] = content
    record["error"] = True
    record["cost"] = 0
    return record
  raise RuntimeError("All retries failed: unable to parse valid JSON with required fields")


def postprocess_tasks(tasks):
  pass


def validate_tasks(tasks):
  for task in tasks:
    source_text = task["source_text"]
    response = task.get("response")
    if not response: continue
    content = response["content"]
    if not validate_content(source_text, content):
      logger.warning(f"Invalid task content: {task}")
      return False
  return True


def build_output(data, tasks):
  depot = collections.defaultdict(list)
  for task in tasks:
    source = task["source_text"]
    response = task.get("response")
    if not response:
      logger.warning(f"Stop by an unprocessed task: {task['index']}")
      break
    depot[source].append(response)
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
      content = results[0]["content"]
      for sentence in content:
        normalize_sentence(sentence)
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
  args = parser.parse_args()
  if args.debug:
    logger.setLevel(logging.DEBUG)
  input_path = Path(args.input_file)
  input_stem = regex.sub(r"-(parallel|analyzed)", "", input_path.stem)
  if args.output:
    output_path = Path(args.output)
  else:
    output_path = input_path.with_name(input_stem + "-analyzed.json")
  if args.state:
    state_path = Path(args.state)
  else:
    state_path = input_path.with_name(input_stem + "-state-analyze.db")
  logger.info(f"Loading data from {input_path}")
  input_data, input_tasks = load_input_data(input_path)
  sm = StateManager(state_path)
  if args.reset or not state_path.exists():
    sm.initialize(input_tasks)
  total_tasks = sm.count()
  logger.info(f"Total tasks: {total_tasks}")
  logger.info(f"GPT models: {args.model}")
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
        source_text, target_text = input_tasks[redo_index]
        sm.reset_task(redo_index, source_text, target_text)
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
      source_text = record["source_text"]
      target_text = record["target_text"]
      short_source_text = regex.sub(r"\s+", " ", source_text).strip()
      short_source_text = cut_text_by_width(short_source_text, 64)
      logger.info(f"Task {index}: {short_source_text}")
      response = execute_task(
        source_text, target_text,
        args.model, args.failsoft, args.no_fallback, args.extra_hint)
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
      json.dump(output_data, f, ensure_ascii=False, indent=2)
    logger.info("Finished")
  else:
    logger.info("To be continued")


if __name__ == "__main__":
  main()

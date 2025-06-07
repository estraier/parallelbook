## 概要

parallelbookは、AIを使って対訳本を作る作るプロジェクトです。現状では英日翻訳に対応しています。

英日対訳本は、英語の本に現れる文のひとつひとつに対して、日本語訳を付与したものです。以下のような構造です。

|英文|日本語訳|
|---|---|
|I am happy to join with you today in what will go down in history as the greatest demonstration for freedom in the history of our nation.|私は今日、歴史に残るほどの自由のための最大のデモに参加できて嬉しいです。|
|Five score years ago, a great American, in whose symbolic shadow we stand today, signed the Emancipation Proclamation.|五十年前、偉大なアメリカ人が、彼の象徴的な影の下で今日立っている私たちが、奴隷解放宣言に署名しました。|
|This momentous decree came as a great beacon light of hope to millions of Negro slaves who had been seared in the flames of withering injustice.|この重大な布告は、数百万の黒人奴隷たちに、しぼんだ不正義の炎で焼かれた希望の大きな灯台として現れました。|
|It came as a joyous daybreak to end the long night of their captivity.|それは、彼らの長い捕囚の夜を終わらせる喜ばしい夜明けとして現れました。|

このような構造のデータを対訳コーパスとも呼びます。対訳コーパスは英語学習者の強い味方です。原文を読むだけでは語彙や語法や文法が難しくて意味が解釈できない場合も、訳文を読めばすぐに理解できます。原文だけで理解できる時は訳文を見ないで読み進めて速読・多読することもできますし、逐一訳文を確認して精読することもできます。

対訳コーパス形式の教材は巷に多くありますが、文章全体の対訳が並べられているものが多いです。それだと、原文で分からない文に出会った時に、訳文の中の該当文を探すのが面倒です。それに対策すべく、このプロジェクトでは、原文と訳文を文単位で対応付けます。躓きそうな時に即座に救いがあることで、多少難しい英文でも読み進められるようになります。

このプロジェクトは、生成機能群と変換機能群から構成されます。生成機能群はプレーンテキストやJSONの入力データを読み込んで、AIで処理してJSONの中間データを作ります。変換機能群は、JSONの中間データを読み込んで、HTMLやEPUBなどの出力データを作ります。

（現状、変換機能は未実装。TypeScriptでJSONを読み出してインタラクティブな対訳閲覧ページを作る予定。Kindle用のMOBIファイルも作る予定）

## インストール

Python3が動く環境であれば、OSは何でも大丈夫です。以下のモジュールが追加で必要になるので、インストールしてください。

```shell
pip3 install regex python-Levenshtein openai tiktoken
```

Gitコマンドで本プロジェクトのファイルをダウンロードします。

```shell
git clone https://github.com/estraier/parallelbook.git
```

以後の作業はparallelbookディレクトリの中で行います。

```shell
cd parallelbook
```

本プロジェクトでは、ChatGPTのAPIを使います。[OpenAIのサイト](https://openai.com/)にログインしてから、画面右上の歯車アイコンから設定ページに遷移して、「API keys」メニューからAPIキーを作成します。生成したAPIキーを環境変数として設定してください。

```shell
export OPENAI_API_KEY="sk-proj-xxxxxxxxxxx"
```

## 生成機能群のチュートリアル

まず、原文のデータを作りましょう。以下のようなプレーンテキストのファイルを用意します。minimum-raw.jsonという名前で保存しましょう。samplesディレクトリの中に同じものがあります。

```
Hello, world. We love translation.

Dr. Slump said, “We did it!” I was surprised.
```

パラグラフは空行で区切られます。1つのパラグラフの中に任意の数の文が書けます。

以下のコマンドを実行して、JSON形式に変換します。

```shell
./scripts/jsonize_plaintext.py < minimum-raw.txt > minimum.json
```

生成されたminimum.jsonの中身は以下のようになるはずです。何らかの方法でこの書式のJSONファイルを直接作っても構いません。

```json
{
  "chapters": [
    {
      "body": [
        {
          "paragraph": "Hello, world. We love translation."
        },
        {
          "paragraph": "Dr. Slump said, “We did it!” I was surprised."
        }
      ]
    }
  ]
}
```

以下のコマンドを実行して、ChatGPTで翻訳を行い、結果のJSONファイルを生成します。

```shell
./scripts/make_parallel_book_chatgpt.py minimum.json
```

生成されたminimum-parallel.jsonの中身は以下のようになるはずです。

```json
{
  "source_language": "en",
  "target_language": "ja",
  "chapters": [
    {
      "body": [
        {
          "paragraph": [
            {
              "id": "00000-000",
              "source": "Hello, world.",
              "target": "こんにちは、世界。"
            },
            {
              "id": "00000-001",
              "source": "We love translation.",
              "target": "私たちは翻訳が大好きです。"
            }
          ]
        },
        {
          "paragraph": [
            {
              "id": "00001-000",
              "source": "Dr. Slump said, “We did it!”",
              "target": "ドクタースランプは言った。「やったぞ！」"
            },
            {
              "id": "00001-001",
              "source": "I was surprised.",
              "target": "私は驚いた。"
            }
          ]
        }
      ]
    }
  ],
  "cost": 0.001,
  "timestamp": "2025-06-07T02:51:54.212895Z"
}
```

ChatGPTによって、パラグラフは文単位に区切られ、その文単位で翻訳が付与されます。また、cost属性は、ChatGPTを動かすために使った費用を示します。ここでは0.001 USドルなので、1ドル150円換算で、このタスクの実行によって0.15円くらいが請求されることがわかります。

もう少し実践的な例も見てみましょう。以下の内容をbasic-raw.txtとして保存してください。samplesディレクトリの中に同じものがあります。

```
# How to Make Parallel Books

- @id sample01: How to Make Parallel Books
- @author Mikio Hirabayashi

## Basics

Parallel corpora are powerful tools to learn languages.  With them, you can learn foreign languages easily by reading your favorite stories.  Each sentence in the original corpus is associated with its translation in your mother tongue.

This project provides scripts to make parallel books from arbitrary contents.  All you have to do is to prepare the original corpus and run some commands to make parallel books in various formats.  Translation is done by AI platforms like ChatGPT and Gemini.

- @macro image https://example.com/logo1.jpg
- @macro comment We will rock you.

## License

This software is distributed under the terms of Apache License version 2.0.  Sample data in this project are in public domain.  So, both can be redestributed freely without additional permissions.
```

「#」で始まる行は本のタイトルを示し、「##」で始まる行は章のタイトルを示します。「- @id」の行は文書のIDを示し、「- @author」の行は文書の著者を示します。「- @macro」の行は、翻訳せずに出力に持ち越したい情報を示します。

以下のコマンドを実行して、JSON形式に変換します。

```shell
./scripts/jsonize_plaintext.py < basic-raw.txt > basic.json
```

生成されたbasic.jsonの中身は以下のようになるはずです。タイトルなどのメタデータが反映され、章ごとにタイトルとパラグラフのリストが保持されていることを確認してください。

```json
{
  "title": "How to Make Parallel Books",
  "id": "sample01: How to Make Parallel Books",
  "author": "Mikio Hirabayashi",
  "chapters": [
    {
      "title": "Basics",
      "body": [
        {
          "paragraph": "Parallel corpora are powerful tools to learn languages.  With them, you can learn foreign languages easily by reading your favorite stories.  Each sentence in the original corpus is associated with its translation in your mother tongue."
        },
        {
          "paragraph": "This project provides scripts to make parallel books from arbitrary contents.  All you have to do is to prepare the original corpus and run some commands to make parallel books in various formats.  Translation is done by AI platforms like ChatGPT and Gemini."
        },
        {
          "macro": "image https://example.com/logo1.jpg"
        },
        {
          "macro": "comment We will rock you."
        }
      ]
    },
    {
      "title": "License",
      "body": [
        {
          "paragraph": "This software is distributed under the terms of Apache License version 2.0.  Sample data in this project are in public domain.  So, both can be redestributed freely without additional permissions."
        }
      ]
    }
  ]
}
```

以下のコマンドを実行して、ChatGPTで翻訳を行い、結果のJSONファイルを生成します。

```
./scripts/make_parallel_book_chatgpt.py basic.json
```

生成されたbasic-parallel.jsonの中身は以下のようになるはずです。

```json
{
  "id": "sample01: How to Make Parallel Books",
  "source_language": "en",
  "target_language": "ja",
  "title": {
    "id": "00000-000",
    "source": "How to Make Parallel Books",
    "target": "平行書籍の作り方"
  },
  "author": {
    "id": "00001-000",
    "source": "Mikio Hirabayashi",
    "target": "平林幹夫"
  },
  "chapters": [
    {
      "title": {
        "id": "00002-000",
        "source": "Basics",
        "target": "基本"
      },
      "body": [
        {
          "paragraph": [
            {
              "id": "00003-000",
              "source": "Parallel corpora are powerful tools to learn languages.",
              "target": "平行コーパスは言語を学ぶための強力なツールです。"
            },
            {
              "id": "00003-001",
              "source": "With them, you can learn foreign languages easily by reading your favorite stories.",
              "target": "それらを使えば、お気に入りの物語を読むことで外国語を簡単に学ぶことができます。"
            },
            {
              "id": "00003-002",
              "source": "Each sentence in the original corpus is associated with its translation in your mother tongue.",
              "target": "元のコーパスの各文は、母国語の翻訳と関連付けられています。"
            }
          ]
        },
        {
          "paragraph": [
            {
              "id": "00004-000",
              "source": "This project provides scripts to make parallel books from arbitrary contents.",
              "target": "このプロジェクトは任意のコンテンツから平行な書籍を作成するためのスクリプトを提供しています。"
            },
            {
              "id": "00004-001",
              "source": "All you have to do is to prepare the original corpus and run some commands to make parallel books in various formats.",
              "target": "やることは、元のコーパスを準備し、いくつかのコマンドを実行してさまざまな形式の平行な書籍を作成するだけです。"
            },
            {
              "id": "00004-002",
              "source": "Translation is done by AI platforms like ChatGPT and Gemini.",
              "target": "翻訳はChatGPTやGeminiなどのAIプラットフォームによって行われます。"
            }
          ]
        },
        {
          "macro": {
            "id": "00005-000",
            "name": "image",
            "value": "https://example.com/logo1.jpg"
          }
        },
        {
          "macro": {
            "id": "00006-000",
            "name": "comment",
            "value": "We will rock you."
          }
        }
      ]
    },
    {
      "title": {
        "id": "00007-000",
        "source": "License",
        "target": "ライセンス"
      },
      "body": [
        {
          "paragraph": [
            {
              "id": "00008-000",
              "source": "This software is distributed under the terms of Apache License version 2.0.",
              "target": "このソフトウェアはApache License バージョン2.0の条件の下で配布されています。"
            },
            {
              "id": "00008-001",
              "source": "Sample data in this project are in public domain.",
              "target": "このプロジェクトのサンプルデータはパブリックドメインです。"
            },
            {
              "id": "00008-002",
              "source": "So, both can be redistributed freely without additional permissions.",
              "target": "そのため、追加の許可なしに両方を自由に再配布することができます。"
            }
          ]
        }
      ]
    }
  ],
  "cost": 0.004,
  "timestamp": "2025-06-07T02:53:09.376157Z"
}
```

本のタイトルや章のタイトルも含めて、ちゃんと翻訳がなされています。今回の費用は0.004ドルなので、0.6円くらいが請求されることになります。

実行時のログを見てみましょう。全てが正常に進む場合、以下のようなログが出ます。

```
Loading data from basic.json
Total tasks: 9
Title: How to Make Parallel Books
GPT models: gpt-3.5-turbo
Task 0: book_title - How to Make Parallel Books
Task 1: book_author - Mikio Hirabayashi
Task 2: chapter_title - Basics
Task 3: paragraph - Parallel corpora are powerful tools to learn languages.  With th
Task 4: paragraph - This project provides scripts to make parallel books from arbitr
Task 5: macro - image https://example.com/logo1.jpg
Task 6: macro - comment We will rock you.
Task 7: chapter_title - License
Task 8: paragraph - This software is distributed under the terms of Apache License v
Done: tasks=9, total_cost=$0.0038 (Y0.57)
Validating output
Writing data into basic-parallel.json
Finished
```

デフォルトでは、gpt-3.5-turboというモデルが使われます。これは多くのタスクで十分な精度で、かつ安いのが利点です。費用は多くかかりますが、より高精度な結果が欲しいのであれば、gpt-4oを使うのも良いでしょう。以下のように実行します。

```
./scripts/make_parallel_book_chatgpt.py basic.json --model gpt-4o
```

```
Loading data from basic.json
Total tasks: 9
Title: How to Make Parallel Books
GPT models: gpt-4o
Task 0: book_title - How to Make Parallel Books
Task 1: book_author - Mikio Hirabayashi
Attempt 1 failed (model=gpt-4o, temperature=0.0, use_context=True): Validation error
Task 2: chapter_title - Basics
Task 3: paragraph - Parallel corpora are powerful tools to learn languages.  With th
Task 4: paragraph - This project provides scripts to make parallel books from arbitr
Task 5: macro - image https://example.com/logo1.jpg
Task 6: macro - comment We will rock you.
Task 7: chapter_title - License
Task 8: paragraph - This software is distributed under the terms of Apache License v
Done: tasks=9, total_cost=$0.0341 (Y5.11)
Validating output
Writing data into basic-parallel.json
Finished
```

gpt-3.5-turboでは$0.0038（0.6円）だったのに、gpt-4oだと$0.0341（5.11円）になっています。長い文章を扱うには、ちょっと高いですね。よって、まずはgpt-3.5-turboで全体のタスクを終わらせてから、気に入らない部分だけをgpt-4oで再試行するのが良いでしょう。どのタスクを再試行するかを把握するには、生成したJSONデータに含まれるタスクIDを見ます。以下の例の場合、原文と翻訳が全く合っていません。

```json
{
  "id": "00035-004",
  "source": "Fetch me my hat.",
  "target": "寝る子は育つ。"
}
```

その場合、タスク35をやり直すことになるでしょう。--redoオプションに、タスクIDを指定します。35,128,247のように、複数のタスクIDを指定することもできます。

```
./scripts/make_parallel_book_chatgpt.py basic.json --model gpt-4o --redo 35
```

タスクの中には、ChatGPTがうまく扱えないものもあるかもしれません。ChatGPTにはJSONの結果を返すように指示していますが、その生成がうまくいかない場合には、プロンプトやパラメータを調整して自動的に再試行がなされます。6回の再試行を経ても失敗する場合には、モデルを変えてさらに6回の再試行を行い、処理を完遂させます。

```
Loading data from basic.json
Total tasks: 9
Title: How to Make Parallel Books
GPT models: gpt-3.5-turbo
Task 0: book_title - How to Make Parallel Books
Task 1: book_author - Mikio Hirabayashi
Task 2: chapter_title - Basics
Task 3: paragraph - Parallel corpora are powerful tools to learn languages.  With th
Task 4: paragraph - This project provides scripts to make parallel books from arbitr
Attempt 1 failed (model=gpt-3.5-turbo, temperature=0.0, use_context=True): Extra data: line 8 column 2 (char 585)
Attempt 2 failed (model=gpt-3.5-turbo, temperature=0.4, use_context=True): Extra data: line 8 column 2 (char 587)
Attempt 3 failed (model=gpt-3.5-turbo, temperature=0.6, use_context=True): Extra data: line 8 column 2 (char 582)
Attempt 4 failed (model=gpt-3.5-turbo, temperature=0.8, use_context=True): Extra data: line 8 column 2 (char 587)
Attempt 5 failed (model=gpt-3.5-turbo, temperature=0.0, use_context=False): Extra data: line 8 column 2 (char 614)
Attempt 6 failed (model=gpt-3.5-turbo, temperature=0.5, use_context=False): Extra data: line 8 column 2 (char 605)
Task 5: macro - image https://example.com/logo1.jpg
Task 6: macro - comment We will rock you.
Task 7: chapter_title - License
Task 8: paragraph - This software is distributed under the terms of Apache License v
Done: tasks=9, total_cost=$0.0094 (Y1.41)
Validating output
Writing data into basic-parallel.json
Finished
```

プロンプトやパラメータやモデルを変えて合計12回の試行をしてもうまくいかない場合、その場で処理が停止します。

```
Loading data from basic.json
Total tasks: 9
Title: How to Make Parallel Books
GPT models: gpt-3.5-turbo
Task 0: book_title - How to Make Parallel Books
Task 1: book_author - Mikio Hirabayashi
Task 2: chapter_title - Basics
Task 3: paragraph - Parallel corpora are powerful tools to learn languages.  With th
Task 4: paragraph - This project provides scripts to make parallel books from arbitr
Attempt 1 failed (model=gpt-3.5-turbo, temperature=0.0, use_context=True): Extra data: line 8 column 2 (char 718)
Attempt 2 failed (model=gpt-3.5-turbo, temperature=0.4, use_context=True): Extra data: line 8 column 2 (char 766)
Attempt 3 failed (model=gpt-3.5-turbo, temperature=0.6, use_context=True): Extra data: line 8 column 2 (char 573)
Attempt 4 failed (model=gpt-3.5-turbo, temperature=0.8, use_context=True): Extra data: line 8 column 2 (char 645)
Attempt 5 failed (model=gpt-3.5-turbo, temperature=0.0, use_context=False): Extra data: line 8 column 2 (char 616)
Attempt 6 failed (model=gpt-3.5-turbo, temperature=0.5, use_context=False): Extra data: line 8 column 2 (char 614)
Attempt 1 failed (model=gpt-4o, temperature=0.0, use_context=True): Extra data: line 8 column 2 (char 607)
Attempt 2 failed (model=gpt-4o, temperature=0.4, use_context=True): Extra data: line 8 column 2 (char 601)
Attempt 3 failed (model=gpt-4o, temperature=0.6, use_context=True): Extra data: line 8 column 2 (char 551)
Attempt 4 failed (model=gpt-4o, temperature=0.8, use_context=True): Extra data: line 8 column 2 (char 572)
Attempt 5 failed (model=gpt-4o, temperature=0.0, use_context=False): Extra data: line 17 column 2 (char 614)
Attempt 6 failed (model=gpt-4o, temperature=0.5, use_context=False): Extra data: line 17 column 2 (char 605)
Traceback (most recent call last):
  File "/Users/mikio/dev/parallelbook/./scripts/make_parallel_book_chatgpt.py", line 637, in <module>
    main()
  File "/Users/mikio/dev/parallelbook/./scripts/make_parallel_book_chatgpt.py", line 611, in main
    response = execute_task_by_chatgpt_enja(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/mikio/dev/parallelbook/./scripts/make_parallel_book_chatgpt.py", line 514, in execute_task_by_chatgpt_enja
    raise RuntimeError("All retries failed: unable to parse valid JSON with required fields")
RuntimeError: All retries failed: unable to parse valid JSON with required fields
```

AIモデルにとって都合の悪いデータを入力すれば、この事態は起こり得ます。異常に長いパラグラフや、プロンプトが紛らわしくなるような記号などを含んでいる場合が典型的です。いずれにせよ、再試行しても状況が改善されないでしょう。その場合、入力データを書き換えるのが無難です。--redoオプションを指定すると、指定したタスクの入力データにおける該当パラグラフを再読み込みするので、都合の悪いデータを排除できます。ただし、パラグラフの数を増減させないように注意してください。そうするとタスクIDがずれるので、全体をやり直す必要が生じます。

エラーが出る度に処理が止まると面倒くさいという場合には、--failsoftオプションを使います。これを指定すると、失敗したタスクはダミーデータで埋めて処理を進めます。結果として、以下のようなレコードが出力に含まれることになります。入力を修正してから再試行するなり、出力を直接手で修正するなりの対処をすると良いでしょう。

```json
{
  "id": "00001-000",
  "source": "This is the end of the world.",
  "target": "[*FAILSOFT*]",
  "error": true
}
```

## 変換機能群のチュートリアル

TBD.

## 生成機能群の仕様

### make_parallel_book_chatgpt.py

make_parallel_book_chatgpt.pyは、原文データのJSONファイルを読んで、その内容を元に対訳データを生成するスクリプトです。対訳データの生成にはChatGPTを用います。

前提として、環境変数OPENAI_API_KEYの値にOpenAIのAPIキーが設定されている必要があります。そのうえで、原文データのJSONファイルを指定して実行すると、そのファイル名に "-parallel.json" をつけた名前で翻訳データのJSONファイルが生成されます。以下のコマンドを実行すると、sample-parallel.jsonが生成されます。

```shell
make_parallel_book_chatgpt.py sample.json
```

本スクリプトは、パラグラフ単位でChatGPTを呼び出して翻訳を行います。文単位ではなくパラグラフ単位で翻訳することで、文脈を加味した翻訳が可能になります。語彙の曖昧性や代名詞の曖昧性を解決するには、ある程度大きい単位で翻訳するのが有利です。さらに、プロンプトの中に文脈情報として以下のものを加えています。

- 前のパラグラフの500文字程度の文のリスト
- 次のパラグラフの200文字程度の文のリスト
- 現在の場面の要約

プロンプトの例を以下に示します。

```
あなたは『ANNE OF GREEN GABLES』の英日翻訳を担当しています。
以下の情報をもとに、与えられたパラグラフを自然な日本語に翻訳してください。

現在の場面の要約（前回出力された文脈ヒント）:
- マリラがアンに引き取ることを決めることを示唆しているが、ミセス・ブルーエットは不機嫌な態度でそれを受け入れる様子。

直前のパラグラフ:
 - “I didn’t say that Matthew and I had absolutely decided that we wouldn’t keep her.
 - In fact I may say that Matthew is disposed to keep her.
 - I just came over to find out how the mistake had occurred.
 - I think I’d better take her home again and talk it over with Matthew.
 - I feel that I oughtn’t to decide on anything without consulting him.
 - If we make up our mind not to keep her we’ll bring or send her over to you tomorrow night.
 - If we don’t you may know that she is going to stay with us.
 - Will that suit you, Mrs. Blewett?”
 - “I suppose it’ll have to,” said Mrs. Blewett ungraciously.

直後のパラグラフ:
 - “Oh, Miss Cuthbert, did you really say that perhaps you would let me stay at Green Gables?”
 - she said, in a breathless whisper, as if speaking aloud might shatter the glorious possibility.
 - “Did you really say it?

----
翻訳対象のパラグラフ:
During Marilla’s speech a sunrise had been dawning on Anne’s face. First the look of despair faded out; then came a faint flush of hope; her eyes grew deep and bright as morning stars. The child was quite transfigured; and, a moment later, when Mrs. Spencer and Mrs. Blewett went out in quest of a recipe the latter had come to borrow she sprang up and flew across the room to Marilla.
----
出力形式はJSONとし、次の2つの要素を含めてください:
{
  "translations": [
    { "en": "原文の文1", "ja": "対応する訳文1" },
    { "en": "原文の文2", "ja": "対応する訳文2" }
    // ...
  ],
  "context_hint": "この段落を含めた現在の場面の要約、登場人物、心情、場の変化などを1文（100トークン程度）で簡潔に記述してください。"
}
英文は意味的に自然な単位で文分割してください。
日本語訳は文体・語調に配慮し、自然な対訳文を生成してください。たとえ短い文でも、文とみなせれば独立させてください。
context_hint は次の段落の翻訳時に役立つような背景情報を含めてください（例：誰が話しているか、舞台の変化、話題の推移など）。
不要な解説や装飾、サマリー文などは含めず、必ず上記JSON構造のみを出力してください。
```

上述のプロンプトに対するレスポンスは以下のようになります。

```
{
  "translations": [
    { "en": "During Marilla’s speech a sunrise had been dawning on Anne’s face.", "ja": "マリラのスピーチ中、アンの顔には日の出のような光が差していた。" },
    { "en": "First the look of despair faded out; then came a faint flush of hope; her eyes grew deep and bright as morning stars.", "ja": "最初は絶望の表情が消え、次に微かな希望の光が差し込んだ。彼女の目は深く輝き、まるで朝の星のようだった。" },
    { "en": "The child was quite transfigured; and, a moment later, when Mrs. Spencer and Mrs. Blewett went out in quest of a recipe the latter had come to borrow she sprang up and flew across the room to Marilla.", "ja": "その子はまるで変わり果てていた。そして、そのしばらく後、スペンサー夫人とブルーエット夫人が借りに来たレシピを探しに出かけた時、アンは飛び起きて部屋を横切り、マリラに駆け寄った。" }
  ],
  "context_hint": "マリラのスピーチ中、アンの表情が次第に変化し、希望に満ちた光を浴びる。アンは喜びに満ち、マリラに駆け寄る。"
}
```

前後のパラグラフを文脈情報として与えるだけではなく、前のパラグラフの翻訳作業で得られた場面のヒント情報を次のパラグラフの翻訳にリレーしていくことにより、翻訳精度を高めることを企図しています。文単位での翻訳よりもパラグラフ単位の翻訳の方が有利であり、現在のパラグラフだけを見る翻訳よりも、前後の文とリレーされた文脈情報を加味した翻訳の方が有利であると仮定しています。

ChatGPTのAPIを叩くと、費用がかかります。2025年5月現在、デフォルトのgpt-3.5-turboモデルだと、入力の1000トークンあたり0.0005ドルかかり、出力の1000トークンあたり、0.0015ドルかかります。gpt-4oモデルだとその10倍で、入力の1000トークンあたり0.005ドルかかり、出力の1000トークンあたり、0.015ドルかかります。

例えば、「Anne of Green Gables」を訳すとしましょう。平均すると、各パラグラフの翻訳には、入力で1000トークン、出力で500トークン程度が使われます。つまり、gpt-3.5-turboモデルだと、入力で0.0005ドル、出力で0.00075ドルかかります。合計で0.00125ドルです。それを1826パラグラフの分だけやるので、2.28ドルかかります。gpt-4oモデルだと、その10倍の22.8ドルかかります。

本スクリプトの手法では文脈情報を入力するために多くのトークン数が費やされていますが、入力トークンの費用が出力トークンの費用よりも小さいので、文脈情報を付加することによる総合的な費用の向上は大きくありません。パラグラフ単位での翻訳と文分割を同時に行うことでの出力トークン数の増加の方が問題ですが、使いやすい対訳本を作る上ではそこは譲れません。

ChatGPTによる処理には時間がかかり、またサーバ側やネットワークの不調などで処理が止まることも多々あります。したがって、途中経過の保存のそこからの再開をする機能が必須となります。本スクリプトでは、途中経過をSQLiteのデータベースに保存することで中断と再開の機能を実現しています。処理中にCtrl-Cを入力するなどして任意のタイミングでプロセスを終了しても、同じコマンドを実行すれば処理を再開することができます。途中経過のデータベースは、入力ファイル名に "-state.db" をつけた名前のファイルで管理されます。

make_parallel_book_chatgpt.pyは以下のオプションを備えます。

- --output OUTPUT : 出力ファイルを明示的に指定します。
- --state STATE : 状態ファイルを明示的に指定します。
- --reset : 最初からタスクをやり直します。
- --num-tasks NUM_TASKS : 処理する最大タスク数を指定します。
- --force-finish : 全部のタスクが終わらなくても、出力ファイルを生成します。
- --failsoft : 失敗したタスクがあっても処理を続けます。
- --model GPT_MODEL : ChatGPTのモデル名を指定します。
- --no-fallback : 失敗時に別モデルを使う処理を抑制します。
- --debug : 各タスクのプロンプトと応答などのデバッグ情報をログ表示します。

ChatGPTに渡すプロンプトはスクリプト内にハードコードされているので、適宜修正して使ってください。表記揺れを防ぐために固有名詞とその翻訳のリストを与えたり、作品の背景知識を埋め込んだりすることも有用です。

## 変換機能群の仕様

TBD.

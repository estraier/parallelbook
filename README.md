## 概要

parallelbookは、AIを使って対訳本を作るプロジェクトです。現状では英日翻訳に対応しています。

英日対訳本は、英語の本に現れる文のひとつひとつに対して、日本語訳を付与したものです。以下のような構造です。

|英文|日本語訳|
|---|---|
|I am happy to join with you today in what will go down in history as the greatest demonstration for freedom in the history of our nation.|私は今日、歴史に残るほどの自由のための最大のデモに参加できて嬉しいです。|
|Five score years ago, a great American, in whose symbolic shadow we stand today, signed the Emancipation Proclamation.|五十年前、偉大なアメリカ人が、彼の象徴的な影の下で今日立っている私たちが、奴隷解放宣言に署名しました。|
|This momentous decree came as a great beacon light of hope to millions of Negro slaves who had been seared in the flames of withering injustice.|この重大な布告は、数百万の黒人奴隷たちに、しぼんだ不正義の炎で焼かれた希望の大きな灯台として現れました。|
|It came as a joyous daybreak to end the long night of their captivity.|それは、彼らの長い捕囚の夜を終わらせる喜ばしい夜明けとして現れました。|

このような構造のデータを対訳コーパスとも呼びます。対訳コーパスは英語学習者の強い味方です。原文を読むだけでは語彙や語法や文法が難しくて意味が解釈できない場合も、訳文を読めばすぐに理解できます。原文だけで理解できる時は訳文を見ないで読み進めて速読・多読することもできますし、逐一訳文を確認して精読することもできます。

まずは、[デモサイト](https://dbmx.net/parallelbook/)を御覧ください。いくつかのサンプルデータを読めば、対訳コーパスの使い勝手が分かるでしょう。

対訳コーパス形式の教材は巷に多くありますが、文章全体の対訳が並べられているものが多いです。それだと、原文で分からない文に出会った時に、訳文の中の該当文を探すのが面倒です。それに対策すべく、このプロジェクトでは、原文と訳文を文単位で対応付けます。躓きそうな時に即座に救いがあることで、多少難しい英文でも読み進められるようになります。

このプロジェクトは、生成機能群と変換機能群から構成されます。生成機能群はプレーンテキストやJSONの入力データを読み込んで、AIで処理してJSONの対訳データを作ります。変換機能群は、JSONの対訳データを読み込んで、HTMLやEPUBなどの出力データを作ります。

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

まず、原文のデータを作りましょう。以下のようなプレーンテキストのファイルを用意します。minimum-raw.txtという名前で保存しましょう。samplesディレクトリの中に同じものがあります。

```
Hello, world. We love translation.

Dr. Slump said, “We did it!” I was surprised.
```

パラグラフは空行で区切られます。1つのパラグラフの中に任意の数の文が書けます。

以下のコマンドを実行して、ソースJSON形式に変換します。

```shell
./scripts/jsonize_plaintext.py < minimum-raw.txt > minimum-source.json
```

生成されたminimum-source.jsonの中身は以下のようになるはずです。何らかの方法でこの書式のソースJSONファイルを直接作っても構いません。raw_line要素はデバッグのためだけにあるので、省略しても構いません。

```json
{
  "chapters": [
    {
      "body": [
        {
          "paragraph": "Hello, world. We love translation.",
          "raw_line": 1
        },
        {
          "paragraph": "Dr. Slump said, “We did it!” I was surprised.",
          "raw_line": 3
        }
      ],
      "raw_line": 1
    }
  ]
}
```

以下のコマンドを実行して、ChatGPTで翻訳を行い、結果の対訳JSONファイルを生成します。

```shell
./scripts/make_parallel_book_chatgpt.py minimum-source.json
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
          ],
          "raw_line": 1
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
          ],
          "raw_line": 3
        }
      ],
      "raw_line": 1
    }
  ],
  "cost": 0.001,
  "timestamp": "2025-06-08T07:12:50.282068Z"
}
```

ChatGPTによって、パラグラフは文単位に区切られ、その文単位で翻訳が付与されます。また、cost属性は、ChatGPTを動かすために使った費用を示します。ここでは0.001 USドルなので、1ドル150円換算で、このタスクの実行によって0.15円くらいが請求されることがわかります。

処理を途中で終わらせたい場合にはCtrl-Cを押してください。プロセスは安全に停止し、次回の実行時には途中から再開されます。実行時に毎回最初からやり直したい場合には、--resetオプションを付けます。

もう少し実践的な例も見てみましょう。以下の内容をbasic-raw.txtとして保存してください。samplesディレクトリの中に同じものがあります。

```
# How to Make Parallel Books

- @id sample01: How to Make Parallel Books
- @author Mikio Hirabayashi

## Basics

Parallel corpora are powerful tools to learn languages.  With them, you can learn foreign languages easily by reading your favorite stories.  Each sentence in the original corpus is associated with its translation in your mother tongue.

This project provides scripts to make parallel books from arbitrary contents.  All you have to do is to prepare the original corpus and run some commands to make parallel books in various formats.  Translation is done by AI platforms like ChatGPT and Gemini.

## License

This software is distributed under the terms of Apache License version 2.0.  Sample data in this project are in public domain.  So, both can be redestributed freely without additional permissions.
```

以下のコマンドを実行して、ソースJSON形式に変換します。

```shell
./scripts/jsonize_plaintext.py < basic-raw.txt > basic-source.json
```

生成されたbasic-source.jsonの中身は以下のようになるはずです。タイトルなどのメタデータが反映され、章ごとにタイトルとパラグラフのリストが保持されていることを確認してください。

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
          "paragraph": "Parallel corpora are powerful tools to learn languages.  With them, you can learn foreign languages easily by reading your favorite stories.  Each sentence in the original corpus is associated with its translation in your mother tongue.",
          "raw_line": 8
        },
        {
          "paragraph": "This project provides scripts to make parallel books from arbitrary contents.  All you have to do is to prepare the original corpus and run some commands to make parallel books in various formats.  Translation is done by AI platforms like ChatGPT and Gemini.",
          "raw_line": 10
        }
      ],
      "raw_line": 6
    },
    {
      "title": "License",
      "body": [
        {
          "paragraph": "This software is distributed under the terms of Apache License version 2.0.  Sample data in this project are in public domain.  So, both can be redestributed freely without additional permissions.",
          "raw_line": 14
        }
      ],
      "raw_line": 12
    }
  ]
}
```

以下のコマンドを実行して、ChatGPTで翻訳を行い、結果の対訳JSONファイルを生成します。

```shell
./scripts/make_parallel_book_chatgpt.py basic-source.json
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
          ],
          "raw_line": 8
        },
        {
          "paragraph": [
            {
              "id": "00004-000",
              "source": "This project provides scripts to make parallel books from arbitrary contents.",
              "target": "このプロジェクトでは、任意のコンテンツから平行な書籍を作成するためのスクリプトが提供されています。"
            },
            {
              "id": "00004-001",
              "source": "All you have to do is to prepare the original corpus and run some commands to make parallel books in various formats.",
              "target": "必要なのは元のコーパスを準備し、いくつかのコマンドを実行してさまざまな形式の平行な書籍を作成するだけです。"
            },
            {
              "id": "00004-002",
              "source": "Translation is done by AI platforms like ChatGPT and Gemini.",
              "target": "翻訳はChatGPTやGeminiなどのAIプラットフォームによって行われます。"
            }
          ],
          "raw_line": 10
        }
      ],
      "raw_line": 6
    },
    {
      "title": {
        "id": "00005-000",
        "source": "License",
        "target": "ライセンス"
      },
      "body": [
        {
          "paragraph": [
            {
              "id": "00006-000",
              "source": "This software is distributed under the terms of Apache License version 2.0.",
              "target": "このソフトウェアはApache License バージョン2.0の条件の下で配布されています。"
            },
            {
              "id": "00006-001",
              "source": "Sample data in this project are in public domain.",
              "target": "このプロジェクトのサンプルデータはパブリックドメインです。"
            },
            {
              "id": "00006-002",
              "source": "So, both can be redistributed freely without additional permissions.",
              "target": "そのため、追加の許可なしに自由に再配布することができます。"
            }
          ],
          "raw_line": 14
        }
      ],
      "raw_line": 12
    }
  ],
  "cost": 0.004,
  "timestamp": "2025-06-08T07:12:55.169844Z"
}
```

本のタイトルや章のタイトルも含めて、ちゃんと翻訳がなされています。今回の費用は0.004ドルなので、0.6円くらいが請求されることになります。

実行時のログを見てみましょう。全てが正常に進む場合、以下のようなログが出ます。

```
Loading data from basic-source.json
Total tasks: 7
Title: How to Make Parallel Books
GPT models: gpt-3.5-turbo
Task 0: book_title - How to Make Parallel Books
Task 1: book_author - Mikio Hirabayashi
Task 2: chapter_title - Basics
Task 3: paragraph - Parallel corpora are powerful tools to learn languages.  With th
Task 4: paragraph - This project provides scripts to make parallel books from arbitr
Task 5: chapter_title - License
Task 6: paragraph - This software is distributed under the terms of Apache License v
Done: tasks=7, total_cost=$0.0038 (Y0.57)
Validating output
Writing data into basic-parallel.json
Finished
```

デフォルトでは、gpt-3.5-turboというモデルが使われます。これは多くのタスクで十分な精度で、かつ安いのが利点です。費用は多くかかりますが、より高精度な結果が欲しいのであれば、gpt-4oを使うのも良いでしょう。以下のように実行します。

```shell
./scripts/make_parallel_book_chatgpt.py basic-source.json --model gpt-4o
```

```
Loading data from basic-source.json
Total tasks: 7
Title: How to Make Parallel Books
GPT models: gpt-4o
Task 0: book_title - How to Make Parallel Books
Task 1: book_author - Mikio Hirabayashi
Attempt 1 failed (model=gpt-4o, temperature=0.0, jsonize=True): Validation error
Task 2: chapter_title - Basics
Task 3: paragraph - Parallel corpora are powerful tools to learn languages.  With th
Task 4: paragraph - This project provides scripts to make parallel books from arbitr
Task 5: chapter_title - License
Task 6: paragraph - This software is distributed under the terms of Apache License v
Done: tasks=7, total_cost=$0.0341 (Y5.11)
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
./scripts/make_parallel_book_chatgpt.py basic-source.json --model gpt-4o --redo 35
```

タスクの中には、ChatGPTがうまく扱えないものもあるかもしれません。ChatGPTにはJSONの結果を返すように指示していますが、その生成がうまくいかない場合には、プロンプトやパラメータを調整して自動的に再試行がなされます。6回の再試行を経ても失敗する場合には、モデルを変えてさらに6回の再試行を行い、処理を完遂させます。

```
Loading data from basic-source.json
Total tasks: 7
Title: How to Make Parallel Books
GPT models: gpt-3.5-turbo
Task 0: book_title - How to Make Parallel Books
Task 1: book_author - Mikio Hirabayashi
Task 2: chapter_title - Basics
Task 3: paragraph - Parallel corpora are powerful tools to learn languages.  With th
Task 4: paragraph - This project provides scripts to make parallel books from arbitr
Attempt 1 failed (model=gpt-3.5-turbo, temperature=0.0, jsonize=True): Extra data: line 8 column 2 (char 585)
Attempt 2 failed (model=gpt-3.5-turbo, temperature=0.0, jsonize=False): Extra data: line 8 column 2 (char 587)
Attempt 3 failed (model=gpt-3.5-turbo, temperature=0.4, jsonize=True): Extra data: line 8 column 2 (char 582)
Attempt 4 failed (model=gpt-3.5-turbo, temperature=0.4, jsonize=False): Extra data: line 8 column 2 (char 587)
Attempt 5 failed (model=gpt-3.5-turbo, temperature=0.8, jsonize=True): Extra data: line 8 column 2 (char 614)
Attempt 6 failed (model=gpt-3.5-turbo, temperature=0.8, jsonize=False): Extra data: line 8 column 2 (char 605)
Task 5: chapter_title - License
Task 6: paragraph - This software is distributed under the terms of Apache License v
Done: tasks=7, total_cost=$0.0094 (Y1.41)
Validating output
Writing data into basic-parallel.json
Finished
```

プロンプトやパラメータやモデルを変えて合計12回の試行をしてもうまくいかない場合、その場で処理が停止します。

```
Loading data from basic-source.json
Total tasks: 7
Title: How to Make Parallel Books
GPT models: gpt-3.5-turbo
Task 0: book_title - How to Make Parallel Books
Task 1: book_author - Mikio Hirabayashi
Task 2: chapter_title - Basics
Task 3: paragraph - Parallel corpora are powerful tools to learn languages.  With th
Task 4: paragraph - This project provides scripts to make parallel books from arbitr
Attempt 1 failed (model=gpt-3.5-turbo, temperature=0.0, jsonize=True): Extra data: line 8 column 2 (char 718)
Attempt 2 failed (model=gpt-3.5-turbo, temperature=0.0, jsonize=False): Extra data: line 8 column 2 (char 766)
Attempt 3 failed (model=gpt-3.5-turbo, temperature=0.4, jsonize=True): Extra data: line 8 column 2 (char 573)
Attempt 4 failed (model=gpt-3.5-turbo, temperature=0.4, jsonize=False): Extra data: line 8 column 2 (char 645)
Attempt 5 failed (model=gpt-3.5-turbo, temperature=0.8, jsonize=True): Extra data: line 8 column 2 (char 616)
Attempt 6 failed (model=gpt-3.5-turbo, temperature=0.8, jsonize=False): Extra data: line 8 column 2 (char 614)
Attempt 1 failed (model=gpt-4o, temperature=0.0, jsonize=True): Extra data: line 8 column 2 (char 607)
Attempt 2 failed (model=gpt-4o, temperature=0.0, jsonize=False): Extra data: line 8 column 2 (char 601)
Attempt 3 failed (model=gpt-4o, temperature=0.4, jsonize=True): Extra data: line 8 column 2 (char 551)
Attempt 4 failed (model=gpt-4o, temperature=0.4, jsonize=False): Extra data: line 8 column 2 (char 572)
Attempt 5 failed (model=gpt-4o, temperature=0.8, jsonize=True): Extra data: line 17 column 2 (char 614)
Attempt 6 failed (model=gpt-4o, temperature=0.8, jsonize=False): Extra data: line 17 column 2 (char 605)
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

特定のタスクの文分割や翻訳が意図通りじゃないといった場合でには、--redoでそのタスクだけやり直すと同時に、--extra-hintで追加のヒント情報を与えると回復できる場合があります。

```shell
./scripts/make_parallel_book_chatgpt.py books/anne02-source.json --redo 0 --extra-hint="「Anne of the Island」は、「島のアン」と訳してください。" --debug
```

## 変換機能群のチュートリアル

TBD.

## 生成機能群の仕様

### jsonize_plaintext.py

jsonize_plaintext.pyは、Markdown風のテキストファイルを読んで、その内容を元に対訳処理の入力用のJSONデータを生成するスクリプトです。このデータ形式をソースJSON形式と呼びます。入力データは標準入力から読み込み、出力データは標準出力に書き込みます。よって、以下のように実行します。

```shell
jsonize_plaintext.py < sample-raw.txt > sample-source.json
```

入力の形式は、Markdownのサブセットです。以下のデータはその全ての機能を使っています。

```
# Book Title

- @id sample02: book title
- @author John Doe

## Chapter1's Title

### Header in the chapter

This is paragraph one. "Baby steps to giant strides!", he said.
Contiguous lines are concatened
into one paragraph. So, you can fold them by a single linefeed.

I replied, "This is the second paragraph. I'm not sure though."
Brank lines separate paragraphs.

- @macro image https://dbmx.net/parallelbook/logo.png
- @macro comment Macros are not translated but kept intact to the output.

## Chapter2's Title

> Lines in blockquotes are also concatenated
> and translated. A whitespace must follow ">".

- Hop. Step. Jump! Each item in the list are not segmented.
- Saitama, Saitama? A whitespace must follow "-".

|symbol|name|number|
|Au|gold|79|
|Ag|silver|47|

```text
one
two two

three three three
```

普通に英文を書くと、段落になります。段落は空行で区切ります。段落の途中の改行は空白と同等とみなされるので、文の間や文の途中で単一の改行を入れて折り返しても大丈夫です。

以下の特殊記法があります。多くの特殊記法は、記号の後ろに空白が必要です。「#1」「-1」で始まっても特殊記法にはなりませんが、「# 1」や「- 1」で始まれば特殊記法になります。

-「#」と空白で始まる行は本のタイトルを示します。通常は文章の冒頭に書きます。
-「##」と空白で始まる行は章のタイトルを示します。章を区切るにはこれを用います。
-「###」と空白で始まる行はヘッダを示します。
-「- @id」と空白で始まる行は文書のIDを示します。
-「- @author」と空白で始まる行は文書の著者を示します。
-「- @macro」と空白で始まる行はマクロを示します。マクロは翻訳されずにそのまま出力に渡ります。
-「-」と空白で始まる行はリストの項目になります。連続した項目は1つのリストになります。
-「>」と空白で始まる行は引用になります。連続した引用は1つの引用ブロックになります。
-「|」で始まり「|」で終わる行は表の行になります。連続した表の行は1つの表になります。
-「```」で始まる行から次の「```」の行までは、コードブロックになります。コードブロックは翻訳されません。

### make_parallel_book_chatgpt.py

make_parallel_book_chatgpt.pyは、jsonize_plaintext.pyが生成したソースJSONファイルを読んで、その内容を元に対訳データを生成するスクリプトです。対訳データの生成にはChatGPTを用います。

前提として、環境変数OPENAI_API_KEYの値にOpenAIのAPIキーが設定されている必要があります。そのうえで、ソースJSONファイルを指定して実行すると、そのファイル名から拡張子と "-source" を抜いた文字列に "-parallel.json" をつけた名前で翻訳データのJSONファイルが生成されます。以下のコマンドを実行すると、sample-parallel.jsonが生成されます。

```shell
make_parallel_book_chatgpt.py sample-source.json
```

本スクリプトは、パラグラフ単位でChatGPTを呼び出して翻訳を行います。文単位ではなくパラグラフ単位で翻訳することで、文脈を加味した翻訳が可能になります。語彙の曖昧性や代名詞の曖昧性を解決するには、ある程度大きい単位で翻訳するのが有利です。さらに、プロンプトの中に文脈情報として以下のものを加えています。

- 前のパラグラフの500文字程度の文のリスト
- 次のパラグラフの200文字程度の文のリスト
- 現在の場面の要約

プロンプトの例を以下に示します。

```
あなたは『I Have a Dream』の英日翻訳を担当しています。
以下の情報をもとに、与えられたパラグラフを自然な日本語に翻訳してください。
----
{
  "現在の場面の要約": "マーティン・ルーサー・キング・ジュニアは奴隷解放宣言に署名された場所で演説を行い、アメリカの建国者たちが全てのアメリカ人が相続人となる約束手形に署名したこと、そしてその約束が有色人種の市民に対して果たされていないことが述べられています。次の段落では、キング牧師がアラバマ州での人種差別について語りかけています。",
  "直前のパラグラフ": [
    "With this faith, we will be able to transform the jangling discords of our nation into a beautiful symphony of brotherhood.",
    "With this faith, we will be able to work together, to pray together, to struggle together, to go to jail together, to stand up for freedom together, knowing that we will be free one day.",
    "And this will be the day -- this will be the day when all of God's children will be able to sing with new meaning:",
    "My country 'tis of thee, sweet land of liberty, of thee I sing.",
    "Land where my fathers died, land of the Pilgrim's pride,    From every mountainside, let freedom ring!"
  ],
  "直後のパラグラフ": [
    "But not only that: Let freedom ring from Stone Mountain of Georgia.",
    "Let freedom ring from Lookout Mountain of Tennessee.",
    "Let freedom ring from every hill and molehill of Mississippi.",
    "From every mountainside, let freedom ring."
  ],
  "翻訳対象のパラグラフ": "And if America is to be a great nation, this must become true. And so let freedom ring from the prodigious hilltops of New Hampshire. Let freedom ring from the mighty mountains of New York. Let freedom ring from the heightening Alleghenies of Pennsylvania. Let freedom ring from the snow-capped Rockies of Colorado. Let freedom ring from the curvaceous slopes of California."
}


----
出力形式はJSONとし、次の要素を含めてください:
{
  "translations": [
    { "en": "原文の文1", "ja": "対応する訳文1" },
    { "en": "原文の文2", "ja": "対応する訳文2" }
    // ...
  ],
  "context_hint": "この段落を含めた現在の場面の要約、登場人物、心情、場の変化などを1文（100トークン程度）で簡潔に記述してください。",
}

----
英文は意味的に自然な単位で文分割してください。たとえ短い文でも、文とみなせれば独立させてください。
ただし、分割の際に元の英文を1文字も変更しないでください。句読点や引用符も含めて全て保持してください。
日本語訳は文体・語調に配慮しつつも、できるだけ直訳調にとどめ、構文や語順の対応関係が分かるようにしてください。
context_hintは次の段落の翻訳時に役立つような背景情報を含めてください（例：誰が話しているか、舞台の変化、話題の推移など）。
不要な解説や装飾、サマリー文などは含めず、必ず上記JSON構造のみを出力してください。

```

上述のプロンプトに対するレスポンスは以下のようになります。

```json
{
  "translations": [
    { "en": "And if America is to be a great nation, this must become true.", "ja": "もしアメリカが偉大な国であり続けるなら、この言葉は実現しなければならない。" },
    { "en": "Let freedom ring from the prodigious hilltops of New Hampshire.", "ja": "ニューハンプシャー州の雄大な丘から自由の鐘を鳴らそう。" },
    { "en": "Let freedom ring from the mighty mountains of New York.", "ja": "ニューヨークの偉大な山々から自由の鐘を鳴らそう。" },
    { "en": "Let freedom ring from the heightening Alleghenies of Pennsylvania.", "ja": "ペンシルベニア州の高いアレゲニー山脈から自由の鐘を鳴らそう。" },
    { "en": "Let freedom ring from the snow-capped Rockies of Colorado.", "ja": "コロラド州の雪を被ったロッキー山脈から自由の鐘を鳴らそう。" },
    { "en": "Let freedom ring from the curvaceous slopes of California.", "ja": "カリフォルニアの曲線美ある斜面から自由の鐘を鳴らそう。" }
  ],
  "context_hint": "キング牧師はアメリカが偉大な国であり続けるためには、全ての州から自由の鐘が鳴らされるべきだと訴えています。"
}
```

前後のパラグラフを文脈情報として与えるだけではなく、前のパラグラフの翻訳作業で得られた場面のヒント情報を次のパラグラフの翻訳にリレーしていくことにより、翻訳精度を高めることを企図しています。文単位での翻訳よりもパラグラフ単位の翻訳の方が有利であり、現在のパラグラフだけを見る翻訳よりも、前後の文とリレーされた文脈情報を加味した翻訳の方が有利であると仮定しています。

AIは間違います。特に、指示通りのJSONフォーマットを出力しなかったり、指示通りの内容を出さなかったりすることがよくあります。よって、後処理として整合性を確認し、不整合であれば、自動的に再試行が行われます。整合性の確認としては、まずJSONが適切に構築できるかを検査します。さらに、文分割した結果を結合した文字列と、元のパラグラフの間の差分（レーベンシュタイン編集距離）を調べ、その割合が10%を超えていたら不整合とみなします。また、引用符が維持されているかどうかも検査しています。

再試行の際にはtemperatureパラメータを増やして出力のランダム性を上げるほか、プロンプトに微調整をします。特にプロンプト内の入力データを疑似JSON形式とプレーンテキストで切り替えるのが効果があります。

パラメータやプロンプトを変えて6回の試行をしてもうまくいかない場合、モデルを切り替えてさらに6回の試行をします。gpt-4oモデルを使っている場合、gpt-3.5-turboモデルに切り替え、gpt-4oモデルを以外を使っている場合、gpt-4oモデルに切り替えます。それでもうまく行かない場合、処理が停止します。ただし、--failsoftオプションをつけている場合、ダミーデータを出力して処理が続行されます。

ChatGPTのAPIを叩くと、費用がかかります。2025年5月現在、デフォルトのgpt-3.5-turboモデルだと、入力には1000トークンあたり0.0005ドルかかり、出力には1000トークンあたり0.0015ドルかかります。gpt-4oモデルだとその10倍で、入力には1000トークンあたり0.005ドルかかり、出力には1000トークンあたり0.015ドルかかります。

例えば、「Anne of Green Gables」を訳すとしましょう。平均すると、各パラグラフの翻訳には、入力で800トークン、出力で400トークン程度が使われます。よって、gpt-3.5-turboモデルだと、入力には0.8*0.0005=0.0004ドルかかり、出力には0.4*0.0015=0.0006ドルかかります。合計で0.0012ドルです。それを1826パラグラフの分だけやるので、1.096ドルかかります。実際には再試行の分がかかるので、その1.5倍くらい見ておくと良いでしょう。つまり1.7ドルくらいです。gpt-4oモデルだと、その10倍の17ドルくらいかかります。

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
- --extra-hint : プロンプトに追加するヒント情報を指定します。
- --debug : 各タスクのプロンプトと応答などのデバッグ情報をログ表示します。

ChatGPTに渡すプロンプトはスクリプト内にハードコードされているので、適宜修正して使ってください。表記揺れを防ぐために固有名詞とその翻訳のリストを与えたり、作品の背景知識を埋め込んだりすることも有用です。

make_parallel_book_chatgpt.pyの出力は以下のような形式になります。

```json
{
  "id": "sample02: book title",
  "source_language": "en",
  "target_language": "ja",
  "title": {
    "id": "00000-000",
    "source": "Book Title",
    "target": "本の題名"
  },
  "author": {
    "id": "00001-000",
    "source": "John Doe",
    "target": "ジョン・ドウ"
  },
  "chapters": [
    {
      "title": {
        "id": "00002-000",
        "source": "Chapter1's Title",
        "target": "第1章のタイトル"
      },
      "body": [
        {
          "header": {
            "id": "00003-000",
            "source": "Header in the chapter",
            "target": "章のヘッダー"
          }
        },
        {
          "paragraph": [
            {
              "id": "00004-000",
              "source": "This is paragraph one.",
              "target": "これは1つ目の段落です。"
            },
            {
              "id": "00004-001",
              "source": "\"Baby steps to giant strides!\", he said.",
              "target": "「小さな一歩から大きな飛躍へ！」と彼は言いました。"
            },
            {
              "id": "00004-002",
              "source": "Contiguous lines are concatened into one paragraph.",
              "target": "隣接する行は1つの段落に結合されます。"
            },
            {
              "id": "00004-003",
              "source": "So, you can fold them by a single linefeed.",
              "target": "そのため、1つの改行で折りたたむことができます。"
            }
          ],
          "raw_line": 10
        },
        {
          "paragraph": [
            {
              "id": "00005-000",
              "source": "I replied, \"This is the second paragraph. I'm not sure though.\"",
              "target": "私は答えました。「これが2番目の段落です。でも、確信はありません。」"
            },
            {
              "id": "00005-001",
              "source": "Brank lines separate paragraphs.",
              "target": "空行が段落を区切ります。"
            }
          ],
          "raw_line": 14
        },
        {
          "macro": {
            "id": "00006-000",
            "name": "image",
            "value": "https://dbmx.net/parallelbook/logo.png"
          },
          "raw_line": 17
        },
        {
          "macro": {
            "id": "00007-000",
            "name": "comment",
            "value": "Macros are not translated but kept intact to the output."
          },
          "raw_line": 18
        }
      ],
      "raw_line": 6
    },
    {
      "title": {
        "id": "00008-000",
        "source": "Chapter2's Title",
        "target": "第2章のタイトル"
      },
      "body": [
        {
          "list": [
            {
              "id": "00009-000",
              "source": "Hop. Step. Jump! Each item in the list are not segmented.",
              "target": "ホップ。ステップ。ジャンプ！リスト内の各項目は分割されません。"
            },
            {
              "id": "00010-000",
              "source": "Saitama, Saitama? A whitespace must follow \"-\".",
              "target": "埼玉、埼玉？「-」の後には空白が必要です。"
            }
          ],
          "raw_line": 25
        },
        {
          "table": [
            [
              {
                "id": "00011-000",
                "source": "symbol",
                "target": "記号"
              },
              {
                "id": "00011-001",
                "source": "name",
                "target": "名前"
              },
              {
                "id": "00011-002",
                "source": "number",
                "target": "番号"
              }
            ],
            [
              {
                "id": "00012-000",
                "source": "Au",
                "target": "Au"
              },
              {
                "id": "00012-001",
                "source": "gold",
                "target": "金"
              },
              {
                "id": "00012-002",
                "source": "79",
                "target": "79"
              }
            ],
            [
              {
                "id": "00013-000",
                "source": "Ag",
                "target": "Ag"
              },
              {
                "id": "00013-001",
                "source": "silver",
                "target": "銀"
              },
              {
                "id": "00013-002",
                "source": "47",
                "target": "47"
              }
            ]
          ],
          "raw_line": 28
        },
        {
          "code": {
            "id": "00014-000",
            "code": "one\ntwo two\n\nthree three three"
          },
          "raw_line": 32
        }
      ],
      "raw_line": 20
    }
  ],
  "cost": 0.004,
  "timestamp": "2025-06-13T15:36:35.768991Z"
}
```

## 変換機能群のチュートリアル

生成機能群で対訳本のJSONデータを生成したら、それを任意の方法で利用します。ユーザ独自の利用方を編み出しても良いのですが、典型的には、HTMLやEPUBなどの標準化されたデータ形式に変換し、Webブラウザや電子書籍リーダなどの既存の表示端末に読み込んで利用することになります。

最も典型的な利用方法は、JSONをHTMLに変換して、Webブラウザで閲覧することです。それを簡単にするために、JavaScriptコードと、それを呼び出すHTMLと、結果を整形するCSSファイルを用意しました。

ここでは、あなたがWebサーバを運用していることを前提とします。手元で手軽に試したい場合、任意のディレクトリで以下のコマンドを実行してください。そのディレクトリの内容を公開する簡易Webサーバが起動します。

```shell
python3 -m http.server 8000
```

webディレクトリの中にある index.htmlとparallelbook.jsとparallelbook.cssを、Webサーバで公開されている任意のディレクトリにコピーします。仮に公開ディレクトリが /home/mikio/public/parallelbook とすると、以下のようにします。

```shell
cp web/index.html web/parallelbook.js web/parallelbook.css /home/mikio/public/parallelbook
```

また、対訳JSONのサンプルを、公開ディレクトリの中のbookディレクトリにコピーします。

```shell
mkdir /home/mikio/public/parallelbook/books
cp samples/*-parallel.json books/*-parallel.json /home/mikio/public/parallelbook/books
```

Webサーバの該当URLにアクセスすると、対訳本を閲覧できます。ローカルで簡易Webサーバを立ち上げた場合、http://localhost:8000/ にアクセスしてください。詳しい使い方はそのページに書いてあります。

index.htmlを見ると、対訳データのレンダリングの方法が分かります。head要素の中に以下のようなコードを書きます。

```html
<script type="module">
// 外部のJavaScriptファイルのインポート
import { renderParallelBook } from "./parallelbook.js";

// 書籍データのリストを定義
const bookList = {
  dream: ["I Have a Dream", "books/dream-parallel.json"],
  anne01: ["Anne of Green Gables", "books/anne01-parallel.json"],
  // 「パラメータ名: ["表示名", "JSONのURL"]」の形式で行を足す
};

// ナビの要素名、コンテンツの要素名、書籍データのリスト、書籍パラメータ名、モードパラメータ名
// を指定して、レンダリングを行う
renderParallelBook("parallel-book-selector", "parallel-book-content",
  bookList, "book", "mode");
</script>
<link rel="stylesheet" href="parallelbook.css">

<!-- 以下はポップアップ辞書の設定。辞書が必要なければ省略可 -->
<script src="https://dbmx.net/dict/union_dict_pane.js"></script>
<script>
union_dict_activate();
</script>
<link rel="stylesheet" href="https://dbmx.net/dict/union_dict_pane.css"/>
```

body要素の中には、レンダリングを行う要素を書きます。これらの要素さえ書けば、任意のページに対訳本を埋め込めます。

```html
<nav id="parallel-book-selector" aria-label="書籍選択ナビゲーション" lang="ja"></nav>

<article id="parallel-book-content" aria-label="書籍本文表示エリア" lang="zxx"></article>
```

対訳データを電子書籍リーダで読むためのEPUB形式に変換することもできます。対訳JSONファイルを指定してコマンドを実行するだけです。

```shell
./scripts/make_parallel_epub.py basic-parallel.json
```

そうすると、basic-parallel.epubというファイルが出来上がります。

```
Loading data from basic-parallel.json
Preparing the directory as basic-parallel-epub
Writing the navigation file as basic-parallel-epub/OEBPS/nav.xhtml
Writing the chapter file as basic-parallel-epub/OEBPS/text/chapter-001.xhtml
Writing the chapter file as basic-parallel-epub/OEBPS/text/chapter-002.xhtml
Writing the style file as basic-parallel-epub/OEBPS/css/style.css
Writing the OPF file as basic-parallel-epub/OEBPS/content.opf
Writing the container file as basic-parallel-epub/META-INF/container.xml
Writing the EPUB file as basic-parallel.epub
```

これを適当な電子書籍リーダに読み込めば、対訳本として読めます。Kindleの場合、[Send-to-Kindle](https://www.amazon.co.jp/sendtokindle)にアップロードするか端末のメールアドレスに送信すれば、AZW3形式に変換されたデータが端末に送信されます。



## 変換機能群の仕様

### parallelbook.js

parallelbook.jsは、任意のWebページに対訳コーパスを表示する機能を実現します。通常は、script要素の中にimport文を書き、renderParallelBook関数をインポートします。その後、renderParallelBook関数を呼び出します。パラーメータとして以下のものを与えます。

- 書籍選択のセレクタを表示する要素のID。通常はnav要素を用います。nullや空文字列なら書籍選択のセレクタは省略されます。
- 書籍の本文を表示する要素のID。通常はarticle要素を用います。
- 書籍データのリスト。「パラメータ名: ["表示名", "JSONのURL"]」を持つ連想配列です。
- URLのクエリ部分における書籍パラメータの名前。
- URLのクエリ部分におけるモードパラメータの名前。

parallelbook.cssは、renderParallelBookが表示した対訳本のスタイルを設定する。このファイルを編集すると、文字の色や大きさや文書の幅などの様々な設定をカスタマイズできる。

書籍パラメータ名が "book" でモードパラメータ名が "mode" の場合、URLのクエリ部分に "?book=anne01&mode=en" などとすることで、初期状態で該当の書籍を表示できます。その場合、書籍選択セレクタを省略しても機能します。

### make_parallel_epub.py

make_parallel_epub.pyは、対訳JSONデータを読んでEPUBファイルを生成する機能です。EPUBファイルは、XHTMLやCSSで電子書籍の内容を表現し、XMLのメタデータと合わせて特定のディレクトリ構造に配置したデータを、ZIP形式でアーカイブしたものです。対訳JSONファイルを指定して実行すると、その拡張子を抜いて "-epub" を付けたディレクトリの中にEPUBのデータが作成され、"-epub" を ".epub" に変えたアーカイブファイルが作成されます。

```shell
./scripts/make_parallel_epub.py basic-parallel.json
```

make_parallel_epub.pyは以下のオプションを備えます。

- --output OUTPUT : 出力ファイルを明示的に指定します。
- --working OUTPUT : 作業用ディレクトリを明示的に指定します。

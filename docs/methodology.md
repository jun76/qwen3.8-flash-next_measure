# 測定方法と公開データの読み方

本書の件数と測定順は、最初のパラメータ探索67リクエストを対象とする。
G7/S31の直接入力・Harness入力を再起動条件から揃えて測った追加30リクエストは、[キャッシュ条件を揃えた再測定](cache_recheck.md)に分けて記録する。

## 実験目的と数え方

RTX 5090 32GB・Core i7-14700・RAM 128GBの環境で、llama.cppまたはStrataの起動パラメータ調整によるQwen3.8-Flash-Nextの生成速度の改善を調査した。
ユーザープロンプトは初回探索67回と追加再測定30回とも「ブロック崩しゲーム作って」。モデル能力全般の評価ではない。

| 単位 | llama.cpp | Strata | 合計 |
| --- | ---: | ---: | ---: |
| サーバー設定：IDごとの起動引数の組み合わせ | 12 | 31 | 43 |
| 条件：設定ID × 入力形式 × sampling × 思考有無 × 出力上限 | 21 | 36 | 57 |
| リクエスト：同条件の再測定も数える | 22 | 45 | 67 |

U1–U5、G1–G7、S01–S31は本実験内で付与した設定IDで、起動引数の組み合わせを識別する。UはUnsloth版llama.cpp、GはGenerelSchwerz版llama.cpp、SはStrataに対応する。
番号は測定群ごとに1から始まる。AtomicBotを動かした記録はない。
候補を順に絞り込む探索であり、全要因を独立に振った実験ではない。追加最適化をまとめて有効にしたケースもある。

## 環境と共通入力

- 測定日：2026-09-28、日本時間。
- Windows native、GeForce RTX 5090 32GB、Core i7-14700、RAM 128GB（64GB × 2、DDR5-5600）、M.2 SSD。
- 両エンジンともISTA-DASLab配布のGSQ-RCO IQ3_Sの同じ2分割GGUFを使用。ファイルのハッシュは[assets.json](assets.json)。
- **直接入力**：共通のユーザープロンプトだけをmessagesに入れる。
- **Harness入力**：DeepSeek Harness 0.1.5-rc.1で保存したシステム指示、実行環境・skillの案内、共通プロンプト、27個のツール定義を使用。[匿名化したfixture](../fixtures/harness-request.json)を同梱。
- APIへ保存済みリクエストを送信した測定。ブラウザ描画とツール実行の時間は含めない。応答がtool_callsで終了しても、エージェント作業全体の完了を意味しない。

## tok/sの定義

| 測定群 | 値の出所 |
| --- | --- |
| llama.cpp | API応答の`timings.predicted_per_second` |
| Strata | engineログの生成token数 ÷ 生成時間。ログで丸められたtok/sも別フィールドへ保存 |

いずれも生成区間全体の平均で、prefill（入力処理）は除く。思考ありでは思考の生成も含む。
`wall_seconds`はHTTPリクエスト全体の時間であり、上記のtok/sの分母ではない。
Strataの時間はengineログのミリ秒精度、llama.cppはAPIが返した精度。小数点以下を多く保存していても測定精度が高まるわけではない。
使用したGenerel版のAPIは、最初の1 tokenをprompt処理から得るため、速度の分子を`predicted_n - 1`としている（[実装](https://github.com/GenerelSchwerz/llama.cpp/blob/50df2c7cf761a4647bd2555cb4e0f0fabdaeef11/tools/server/server-common.h#L410)）。
表の生成token数はその1 tokenを含む総数で、速度はAPIの定義をそのまま使う。

4,096または2,048 tokenなどの固定長測定と、EOS/ツール呼び出し終了までの測定を区別する。
llama G7の70.53 / 70.38 tok/sは思考中の4,096 tokenで打ち切った測定。
Strata S31の117.30 tok/sは、再起動後のHarness入力・思考あり・2,048 tokenの3回の中央値。

## エンジン間で異なる条件

| 項目 | llama.cpp G7 | Strata S31 |
| --- | --- | --- |
| 最大context | 131,072 | 262,144 |
| KV | K/Vともq4_0 | int8 |
| MTP | 無効 | Q2_0 head、spec=4、spec-min-p=0.5 |
| 生成時sampling | temperature=1、top_k=20、top_p=0.95、min_p=0.05、seed=1234 | engineのgreedy生成 |
| 原Harness入力token数 | 8,930 | 8,685 |
| expertキャッシュ | 21,000 MiBの予算 | 拡張配置表、auto、reserve=3,072 MiB、約9,500枠 |

ユーザープロンプトと本体GGUFは同じでも、テンプレート、入力token数、生成内容、出力長などは一致しない。
したがってREADMEの数値は各設定で得た速度であり、条件を完全に揃えたエンジン間の倍率ではない。
UnslothやGenerelのMTPケースはQ8_0/Q4_K_M headを使用しており、StrataのQ2_0 headとも異なる。
llama.cppでtemperature=0を測ったのはNo.7、10、12。その他の条件は各測定群の全行表を参照。

## キャッシュと実行順

llama.cppは`cache_prompt=false`、Strataは加えて`--prompt-cache 0`。Strataの原記録は全45回ともreused_tokens=0。
同じサーバープロセス内の2回目以降には、前の生成によるexpertキャッシュの配置が残る。
入力KVの再利用を無効にしても、その効果まで無効にはならない。

[plans/](../plans/)はプロセス単位のグループを記録する。各グループで起動し、グループ内のリクエストを順に実行して終了する。
llama G7はNo.20の前に再起動。Strataは41プロセスグループで45リクエストを実行した。
Strataの全Harness応答（No.33、35、37）は、同じサーバーで2,048 tokenの測定を1回行った直後の2回目。
quickプランは一部を新規プロセスで実行するため、全プランの途中にある履歴を再現するものではない。
ここでの再起動はengineプロセスの再起動を意味し、OSのファイルキャッシュを消去した状態ではない。

## expert配置表と既存の局所修正

Strataの拡張配置表は、元の8,000件の順位を保持し、未収録のexpertを層ごとに順に追加して24,576件にした。
追加した順位は実測のrouting頻度から求めたものではない。推論中の適応キャッシュが実際のexpert使用に応じて入れ替える。
作成スクリプトと元・生成後のハッシュを同梱した。VRAM残量でautoの実確保数が変わるため、各回の`startup.json`とCSVに実数を保存している。

[Strataパッチ](../patches/strata-local.patch)は測定開始前から存在した2点の修正：

1. parity確認コードがCPUのAVX-512対応を確認してから該当経路を呼ぶ。
2. legacy S2のキャッシュ経路に対する警告を、別経路であるnative IQへ表示しない。

31設定の比較中に重み・engineコードは変えていない。この警告範囲の変更は、モデル全体の出力の正しさを証明するものではない。
Unsloth U1は保存済み設定要約に全argvがなかったため、U3の保存済みargvと元のMTP起動スクリプトから`threads=20`、`fit-target=4096`を復元した。該当設定に`reconstruction_note`を付けている。

## 匿名化とハッシュ

ユーザー名、ユーザーディレクトリ、元の作業・インストール先を、`models/`、`vendor/`、`fixtures/workspace/`などのリポジトリ相対パスへ置換した。
記録中の`artifacts/strata/packs/`と`artifacts/strata/mtp/`は旧配置の匿名化先。追試用の実配置は[paths.example.json](../configs/paths.example.json)が定義する`vendor/strata/`以下。
ログのパスは記録の参照用であり、そこに実行ファイルや全ての元ファイルが同梱されていることを意味しない。

入力・応答中のパスも置換したため、公開fixtureのtoken数、生成内容、速度は原記録と変わり得る。
**CSV・JSONL・API応答中のtoken数やtimingは原測定の数値を保持しており、匿名化後に再測定・再tokenizeした値ではない。**
上記は初回探索の`results/llama_cpp/`と`results/strata/`に適用する。
追加の`results/cache-recheck/`は公開fixtureを使って測り直した記録で、公開コピーでも解析後のリクエスト本文が一致することを確認した。
初回探索と追加測定の差には、Harness入力のパス置換による違いも含まれる。
直接入力のプロンプト本文は共通の日本語文のまま。

- `original_request_sha256`：原llama.cppリクエストファイルのハッシュ。
- `published_request_sha256`：公開llama.cppリクエストファイルのハッシュ。
- `original_output_sha256` / `published_output_sha256`：Strataのmessageから`content`、`reasoning_content`、`tool_calls`を取り、`json.dumps(..., ensure_ascii=False, sort_keys=True)`したUTF-8列のハッシュ。
- [publication-manifest.json](../results/publication-manifest.json)：ファイルごとに原記録と公開コピーのSHA-256を対応付けたもの。対象はコピーした入力・応答・ログ等であり、新規作成したREADMEや集計CSVは含めない。
- [assets.json](assets.json)：重み、配置表、実行ファイルのハッシュ。ビルドし直したバイナリのハッシュ一致は保証しない。

## 品質・ばらつきの限界

全応答を得たHTMLについて実施済みのJavaScript構文確認を記録した。llama G7のHarness出力1件は`state`の二重宣言で失敗し、そのまま保存している。
他の構文確認通過もゲームの全操作を検証した意味ではない。本実験は速度調整が主目的であり、一般的な品質差やKV量子化の影響はこれらの少数例から判断できない。

各条件は主に1回。Strataの有力候補のみ2～3回、llamaの同条件再測定は1組。
温度・クロック・同時GPU使用・空きVRAM・生成内容で速度は変わる。終了後の空きVRAMは生成中の最小値ではない。
100,000 tokenを実際に連続生成した記録は含まない。

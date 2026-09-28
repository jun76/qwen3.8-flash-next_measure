# qwen3.8-flash-next_measure

**日本語** | [English](README.en.md)

Qwen3.8-Flash-Nextの生成速度（tok/s）の改善を目的として、llama.cppの2つのforkとStrataで起動パラメータを調整した実験記録。
共通のユーザープロンプトは「ブロック崩しゲーム作って」。設定、全測定結果、入力・応答、ログ、追試スクリプトをまとめた。

## 検証環境

測定日：2026-09-28。

| 項目 | 構成 |
| --- | --- |
| OS・実行環境 | Windows native |
| GPU | NVIDIA GeForce RTX 5090（VRAM 32GB） |
| CPU | Intel Core i7-14700 |
| メモリ | 128GB（64GB × 2、DDR5-5600） |
| モデル保存先 | M.2 SSD |

本体モデルは両エンジンとも同じ[ISTA-DASLab GSQ-RCO IQ3_S](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF)の2分割GGUFを使用した。

## エンジン名と設定ID

**G7やS31は、本実験で起動引数の組み合わせごとに付与した設定ID。ソフトウェアのバージョン名や公式プリセット名ではない。**

| 本文での呼称 | 使用したエンジン | 本実験の設定ID |
| --- | --- | --- |
| Unsloth版 | [unslothai/llama.cpp](https://github.com/unslothai/llama.cpp) | U1–U5 |
| GenerelSchwerz版（略称：Generel版） | [GenerelSchwerz/llama.cpp](https://github.com/GenerelSchwerz/llama.cpp) | G1–G7 |
| Strata | [Niko1221/Strata](https://github.com/Niko1221/Strata) | S01–S31 |

各IDの全起動引数は[llama.cpp設定](configs/llama_cpp.json)と[Strata設定](configs/strata.json)、使用コミットは[ソース版一覧](docs/sources.json)に記録した。
「Unsloth版」はエンジンのforkを指し、本体GGUFは上記のISTA-DASLab配布物を使用した。

## 設定別の生成速度

以下は測定条件ごとに上位の設定を速度順に並べ、設定値を示したもの。
固定長の設定比較は初回探索67件から集計し、応答終了までの表はキャッシュ条件を揃えた追加再測定へ更新した。

速度はprefillを除いた**生成区間の平均tok/s**で、思考トークンも含む。複数回ある条件は中央値、1回だけの条件はその実測値を掲載する。
「直接」はユーザープロンプトのみ、「Harness」は同じプロンプトにDeepSeek Harnessのシステム指示・ツール定義を加えた入力。

### llama.cpp：直接入力の固定長測定

直接入力・思考あり・temperature=1の固定長測定から、設定別の上位3件。
3件とも**context=131,072、MTP無効、生成8スレッド／入力20スレッド**。

| 設定 | tok/s ↓ | 測定長 × 回数 | KV（K/V） | expert cache（MiB） | 追加最適化 |
| --- | ---: | --- | --- | ---: | --- |
| G7 | 70.46 | 4,096 token × 2 | q4_0 / q4_0 | 21,000 | 下記6項目を有効 |
| G3 | 69.13 | 1,024 token × 1 | q8_0 / q8_0 | 20,000 | 下記6項目を有効 |
| G1 | 48.81 | 1,024 token × 1 | q8_0 / q8_0 | 18,000 | 無効 |

**G7の主な起動引数**（[使用forkとビルド手順](docs/reproduce.md)、モデル等を含む全引数は[configs/llama_cpp.json](configs/llama_cpp.json)の`G7`）：

```text
--ctx-size 131072 --cache-type-k q4_0 --cache-type-v q4_0
--moe-expert-cache-mib 21000 --threads 8 --threads-batch 20
-ngl all --fit off --load-mode none --lazy-mode on --flash-attn on -b 512 -ub 512
--backend-sampling --decode-overlap --decode-boundary-overlap
--ple-prefetch --phase-aware-workspace --live-context-workspace
```

掲載した上位3設定は、GenerelSchwerz版でMTPを無効にし、expertキャッシュへVRAMを割り当てた構成。G3はq8_0のKVを使用する。
G7の2回は70.53 / 70.38 tok/s（再起動前後）。G3とは測定長が異なり、キャッシュ量とKVも同時に変えているため、両者の小差をKVだけの効果とは扱わない。
記録はllama No.18・20 / No.11 / No.8。出力上限で打ち切らずに測定した結果は「応答終了までの生成速度」に掲載した。

### Strata：Harness入力の固定長測定

Harness入力・思考あり・greedy・2,048 token生成・毎回サーバー再起動の測定から、設定別の上位5件。
全行で**Q2_0 MTP、spec=4、spec-min-p=0.5、KV=int8、expert-cache=auto**。

| 設定 | tok/s ↓（回数） | context | expert配置表 | adapt-every | vram-reserve-mib | 終了後の空きVRAM（GiB） | 備考 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| S24 | 118.04（3） | 32K | 拡張 | 4 | 3,072 | 1.45–1.72 | 最大contextは32K |
| S31 | 117.30（3） | 256K | 拡張 | 1 | 3,072 | 1.39–1.68 | 256K構成で最高の中央値 |
| S21 | 110.46（1） | 128K | 拡張 | 4 | 2,048 | 0.57 | 空きVRAMが少ないため参考値 |
| S29 | 109.15（2） | 128K | 拡張 | 4 | 3,072 | 1.51–1.69 | S21からVRAM予約量を増加 |
| S30 | 106.43（3） | 256K | 配布時の8,000件 | 1 | 700 | 4.46–4.49 | 配置表の拡張なし |

**S31の主な起動引数**（[配置表の作成手順](docs/reproduce.md)、[基準引数](configs/strata-base.json)と[設定差分](configs/strata.json)）：

```text
--max-context 262144 --kv int8 --spec 4 --spec-min-p 0.5
--expert-profile artifacts/strata/expert-profile-expanded.bin --expert-cache auto
--vram-reserve-mib 3072 --adapt-every 1
```

S31は配置表を拡張してGPU常駐expertを約9,500枠へ増やし、毎ラウンド入れ替える構成。共通設定はprefill=2048、pcie-frac=0.55。実測のCPUワーカー数は19。
S30は配布時の配置表を使用し、S31より測定後の空きVRAMが多かった。
空きVRAMは上表に使った各測定の終了後の値で、生成中の最小値ではない。
記録は順にStrata No.24・41・42 / No.31・36・40 / No.21 / No.29・43 / No.30・34・39。

### 応答終了までの生成速度

思考あり・毎回サーバーを再起動して各3回測定した結果。
値は生成区間のtok/sの**中央値（最小–最大）**。出力長は各回で異なる。

| 設定 | 直接入力：tok/s | Harness入力：tok/s |
| --- | ---: | ---: |
| llama.cpp G7 | **62.32**（61.84–62.34） | **63.50**（62.01–63.56） |
| Strata S31 | **99.25**（97.03–105.78） | **110.40**（91.08–128.05） |

S31のHarness入力には大きなばらつきがあり、直接入力より低い回もあった。
2,048 tokenに揃えた再測定でもS31はHarness入力の中央値が高かったが、同一入力の再送は速度と生成内容の両方が変わり、キャッシュ単独の効果は分離できなかった。
生成数、MTP採用率、同じ2,048 tokenでの比較、同一入力を再送した場合の差は[再測定の全記録](docs/cache_recheck.md)に掲載した。

**考察（仮説）**

考えられる説明の一つは、Harnessの指示でコード生成へ早く進み、MTPの先読みが当たりやすくなったことである。
Strataは先読みが連続して当たった分をまとめて確定するため、一度の検証で確定できるtokenが増えると、生成速度が上がり得る（[使用版の実装](https://github.com/Niko1221/Strata/blob/6c4c8c1dfafc16fa0ea7fc80c12c79f93b9f7eee/src/program/generate.cpp)）。

2,048 tokenに揃えた再測定では、Harnessの2回は短い思考からコード生成へ進み、直接入力の3回はいずれも思考中に上限へ達した。
MTP採用率の中央値はHarnessが82.18%、直接入力が63.50%だった。
Harnessでも思考中に上限へ達した残りの1回は、コード生成へ進んだ2回より速度と採用率が低かった。
生成数を揃えても差が残るため、総生成数の違いだけでは速度差を説明できない。

ただし、入力長やexpert配置、実行時の状態も異なり、MTPの因果効果は分離していない。
各条件3回の観測であり、統計的な有意差も確認していない。

Harnessはツール呼び出しを出し終えるまでで、ツールの実行時間は含めない。
この表は全て新規プロセスで、入力KVの再利用も無効。OSのファイルキャッシュは消去していない。
思考なしの結果や生成コードの確認結果は、初回探索の[llama.cpp全記録](docs/llama_cpp.md)・[Strata全記録](docs/strata.md)へ掲載。
掲載値は記載の測定環境と共通プロンプトで得た結果。エンジン間ではcontext、KV、MTP、sampling、テンプレートが異なるため、比較できる範囲は[測定方法](docs/methodology.md)に記載した。

## 測定件数

初回のパラメータ探索：

| 測定群 | サーバー設定 | 入力・生成条件を含む条件数 | 生成リクエスト数 |
| --- | ---: | ---: | ---: |
| llama.cpp：Unsloth / GenerelSchwerz | 12（U1–U5、G1–G7） | 21 | 22 |
| Strata | 31（S01–S31） | 36 | 45 |
| **合計** | **43** | **57** | **67** |

MTP、CPUスレッド、expertのGPUキャッシュ、KV形式、コンテキスト、転送・適応設定などを探索した。
全組み合わせの総当たりではない。AtomicBotは調査のみで、実測には含めない。

今回のキャッシュ再測定は既存のG7/S31を使う追加30リクエスト（計97リクエスト）。
内訳は応答終了まで12回、2,048 token上限で新規プロセス12回、同一プロセス内の再送6回。
設定を追加した探索ではなく、直接/Harnessとキャッシュ履歴の比較である。
[再測定の条件・全30件](docs/cache_recheck.md)を別に記録した。

## 追試

1. [再現手順](docs/reproduce.md)に沿って、固定した版のエンジンとモデルを用意する。重み・実行ファイルはこのリポジトリに含めていない。
2. 配置先を[configs/paths.example.json](configs/paths.example.json)に合わせる。変更する場合は、Git対象外の`configs/paths.local.json`へ上書き値を書く。
3. リポジトリのルートから実行する。スクリプトはPython 3.10以降の標準ライブラリを使用する。

```powershell
# 起動引数の確認のみ。サーバーや生成処理は実行しない
python scripts/run_benchmarks.py --plan plans/llama_cpp-quick.json --dry-run
python scripts/run_benchmarks.py --plan plans/strata-quick.json --dry-run

# 他の推論サーバーを終了してから、片方ずつ測定
python scripts/run_benchmarks.py --plan plans/llama_cpp-quick.json
python scripts/run_benchmarks.py --plan plans/strata-quick.json
```

新しい結果はGit対象外の`runs/`へ保存する。
初回探索67件はパス置換前の実測記録で、公開したHarness入力とトークン単位では一致しない。
追加再測定30件は公開入力を用いた実測値で、[専用プランとコマンド](docs/reproduce.md#キャッシュ条件を揃えた再測定)で追試できる。

## 関連ファイル

| 場所 | 内容 |
| --- | --- |
| [docs/reproduce.md](docs/reproduce.md) | モデル取得、固定版のビルド、追試コマンド |
| [docs/methodology.md](docs/methodology.md) | 集計単位、速度の定義、比較条件、匿名化の影響 |
| [configs/](configs/) / [plans/](plans/) | 43設定の引数、初回67件と追加30件の実行順・再起動境界 |
| [results/llama_cpp/](results/llama_cpp/) / [results/strata/](results/strata/) | CSV・JSONL、保存済み入力・応答、起動・測定ログ |
| [docs/cache_recheck.md](docs/cache_recheck.md) / [results/cache-recheck/](results/cache-recheck/) | キャッシュ条件を揃えた追加30件の比較・集計・全記録 |
| [fixtures/harness-request.json](fixtures/harness-request.json) | 匿名化したHarness入力。ツールは定義だけで実行しない |
| [artifacts/generated/](artifacts/generated/) | 保存済み応答から抽出したHTML。失敗例も未修正で保存 |
| [scripts/](scripts/) | リクエスト再生、expert配置表拡張、資産ハッシュ照合 |
| [patches/strata-local.patch](patches/strata-local.patch) | 測定前から適用していたStrataの局所修正 |
| [docs/sources.json](docs/sources.json) / [docs/assets.json](docs/assets.json) | 使用コミット、ビルド情報、モデル等のSHA-256 |
| [results/publication-manifest.json](results/publication-manifest.json) | 原記録と公開コピーのハッシュ対応 |

本リポジトリで作成したスクリプト・設定・説明文は[MIT License](LICENSE)。取り込んだ第三者の内容と各モデル・エンジンの扱いは[NOTICE](NOTICE.md)を参照。

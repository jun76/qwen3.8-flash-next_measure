# キャッシュ条件を揃えた再測定

[README](../README.md)の「応答終了までの生成速度」を、G7/S31・直接/Harnessの4条件で再測定した。
G7とS31は本実験内の設定IDであり、使用するエンジンと起動引数は[設定一覧](../README.md#エンジン名と設定id)に記載している。
測定環境は初回探索と同じWindows native、RTX 5090 32GB、Core i7-14700、RAM 128GB、M.2 SSD。
追加測定時のOSはWindows 11（build 26200）、NVIDIA driverは591.86、測定ランナーのPythonは3.12.11。
記録は[environment.json](../results/cache-recheck/environment.json)を参照。

## 結果

### 応答終了まで

思考あり・毎回新規プロセスで各3回。値は中央値（最小–最大）、単位はtok/s。

| 設定 | 直接入力：tok/s | Harness入力：tok/s |
| --- | ---: | ---: |
| llama.cpp G7 | 62.32（61.84–62.34） | 63.50（62.01–63.56） |
| Strata S31 | 99.25（97.03–105.78） | 110.40（91.08–128.05） |

| 設定 | 入力 | 入力token数 | 生成token数：中央値（最小–最大） | 終了理由（件数） |
| --- | --- | ---: | ---: | --- |
| G7 | 直接 | 58 | 25,930（25,930–25,930） | stop: 3 |
| G7 | Harness | 8,858 | 5,506（5,506–5,506） | tool_calls: 3 |
| S31 | 直接 | 58 | 28,025（23,735–28,650） | stop: 3 |
| S31 | Harness | 8,613 | 13,634（4,955–17,375） | tool_calls: 3 |

12回とも出力上限には達せず、直接入力は`stop`、Harness入力は`tool_calls`で終了した。
S31のHarness入力は中央値で直接入力を約11%上回ったが、観測範囲は大きく重なり、3回目は直接入力の3回全てより低かった。
旧表の121.62 tok/sは今回の観測範囲内であり、プロセス内キャッシュを引き継がない起動直後にも128.05 tok/sを観測した。
一方、G7は入力ごとに3回とも生成内容・生成数が一致し、全応答の速度のばらつきも小さかった。

S31は直接・Harnessそれぞれの3回で、短い応答ほど平均tok/sが高い並びになった。
ただし、生成内容とMTP採用率も同時に変わっており、出力長だけの効果とは分離できない。

### 同じ出力上限での比較

毎回新規プロセスで、生成上限2,048 tokenを各3回。値は中央値（最小–最大）。

| 設定 | 直接入力：tok/s | Harness入力：tok/s |
| --- | ---: | ---: |
| llama.cpp G7 | 73.21（59.68–73.21） | 62.79（62.42–63.24） |
| Strata S31 | 95.85（92.11–102.09） | 115.34（98.44–119.79） |

12回とも実際に2,048 tokenを生成し、`length`で終了した。
S31では生成数を揃えてもHarness入力の中央値が高く、生成数の違いだけでは速度差を説明できない。
G7では直接入力の中央値が高くなり、全応答の表とは順序が入れ替わった。
Harness入力が常に速くなるという一般則は、この比較からは得られない。

G7の直接入力は3回とも同じ生成内容だったが、1回目の59.68 tok/sも観測範囲に含めた。
この差の原因は特定しておらず、OS・ドライバのキャッシュや通常の背景処理を完全には固定していない点が残る。

### S31：同じプロセスで同じ入力を再送

2,048 token測定の1回目と、その直後の2回目を対にした。promptキャッシュは両方とも無効。
速度変化率は各対で計算してから中央値を取るため、列の中央値同士を割った値とは一致しない場合がある。

| 入力 | 1回目 tok/s | 2回目 tok/s | 対ごとの変化率：中央値（最小–最大） | 同じ生成内容だった対 |
| --- | ---: | ---: | ---: | ---: |
| 直接 | 95.85（92.11–102.09） | 94.10（83.78–95.49） | -1.83（-17.94–3.67）% | 0/3 |
| Harness | 115.34（98.44–119.79） | 98.36（96.62–103.29） | -14.72（-19.34–4.93）% | 0/3 |

直接・Harnessとも2組で低下、1組で上昇した。
6組全てで生成内容が変わり、S31はgreedyでも今回の再送で同じ出力にはならなかった。
Harnessの最初の2組では、1回目は短い思考の後に`write`の引数生成へ進んだが、再送では思考を生成中のまま上限に達した。
プロセス内の履歴だけでなく生成内容とMTP採用率も変わったため、この変化率をキャッシュ単独の効果とは扱わない。
旧表の高い値を、前のリクエストによるキャッシュの温まりだけで説明する根拠は得られなかった。

### S31のMTP採用率

engineログの`drafts accepted / offered`をリクエストごとに計算し、中央値（最小–最大）を表示。

| 測定 | 直接入力 | Harness入力 |
| --- | ---: | ---: |
| 応答終了まで・新規 | 73.74（72.80–74.69）% | 82.08（80.83–85.61）% |
| 2,048 token・新規 | 63.50（62.63–63.60）% | 82.18（71.91–84.15）% |
| 2,048 token・再送 | 57.95（54.69–60.60）% | 71.29（69.16–71.79）% |

採用率と速度の関係を調べる補助情報であり、この測定だけでMTPやキャッシュの因果効果を分離した値ではない。
固定長のS31 Harness入力では採用率の中央値も高く、生成内容によってMTPが効きやすくなったことは速度差を説明する候補になる。
ただし、採用率だけでtok/sは決まらず、入力長やexpert配置、実行時の状態も同時に異なる。

### キャッシュと動作状態の確認

S31の18リクエストは全て`reused_tokens=0`、G7の12リクエストは全て`cache_n=0`だった。
S31の実cache枠数は9,548–9,631、CPUワーカー数は19。
各プロセスの開始前・起動後・終了後のVRAMは保存記録を参照。

| 設定 | 生成リクエスト中のGPUサンプル数 | 温度の範囲（°C） | SMクロックの範囲（MHz） | 空きVRAMの最小観測値（MiB） |
| --- | ---: | ---: | ---: | ---: |
| G7 | 185 | 46–65 | 2812–2880 | 1,702 |
| S31 | 153 | 44–62 | 2422–2880 | 624 |

リクエスト中のサンプルにはprefillも含む。10秒より短い変化や、他のプロセスによる影響を全て排除できたことを示す値ではない。
別途記録した終了直後の空きVRAMの最小値は、G7が2,167 MiB、S31が519 MiBだった。
空きVRAMと実cache枠数を固定した試験ではないため、生成内容だけにばらつきの原因を限定しない。

## 測定条件

初回の表では、Strataの直接入力は新規プロセスでの1回目、Harness入力は2,048 token生成後の2回目だった。
入力KVの再利用は無効でも、expertキャッシュなどの履歴が揃っていなかった。
今回の主表は全リクエストを新規プロセスの1回目とし、同じ条件を3回ずつ測定した。

| 測定群 | 条件 | 各条件の回数 | リクエスト数 | プロセス数 |
| --- | --- | ---: | ---: | ---: |
| 応答終了まで | G7/S31 × 直接/Harness、毎回新規プロセス | 3 | 12 | 12 |
| 2,048 token上限 | G7/S31 × 直接/Harness、毎回新規プロセス | 3 | 12 | 12 |
| 同一入力の再送 | 上記S31の直後、同じプロセスで直接/Harnessを再送 | 3 | 6 | 追加なし |
| **合計** | **10条件、既存の2設定を使用** | | **30** | **24** |

2,048 token測定は出力上限を揃える比較で、EOSを無視する設定ではない。
応答終了までの上限は65,536 tokenとし、`length`で終了した場合は上限到達として記録する。
ツール呼び出しを出し終えた時点までを測り、そのツールや生成コードは実行しない。

### 揃えた条件と残る違い

| 項目 | 条件 |
| --- | --- |
| 本体重み・エンジン | 初回探索と同じファイル。測定前に本体GGUF・MTP・配置表・実行ファイルをSHA-256で照合 |
| 実行順 | [プラン](../plans/cache-recheck.json)を開始前に固定。full/fixedの各群で繰り返しごとに4組を並べ替え（shuffle seed=20260928） |
| 入力 | 公開済みの[直接入力](../fixtures/direct-request.json)と[Harness入力](../fixtures/harness-request.json)。両エンジンへ同じmessages/toolsを送信 |
| 思考 | 全リクエストで有効 |
| sampling | G7: temperature=1、top_k=20、top_p=0.95、min_p=0.05、seed=1234。S31: engineのgreedy生成 |
| promptキャッシュ | `cache_prompt=false`。S31は`--prompt-cache 0`、G7は`--cache-ram 0`。S31の`reused_tokens`とG7の`cache_n`を記録 |
| expertなどのプロセス内キャッシュ | 主表と固定長の1回目は毎回プロセス終了・再起動。S31の2回目だけ状態を引き継ぐ |
| OSファイルキャッシュ | 消去しない。モデル読込を含む起動時間は生成tok/sに含めない |
| キャッシュ容量 | G7は21,000 MiB。S31は元の`auto`を保持し、起動ごとの実slot数とVRAM使用量を記録 |
| 他の負荷 | 他の推論サーバーを停止。通常のデスクトップアプリは残す。GPU使用量・温度・クロック等を10秒間隔で記録 |
| 集計 | Strataは生成token数 ÷ 生成秒数。G7はAPIの`predicted_per_second`を使用。条件ごとに3回の中央値と最小–最大を表示。観測範囲は信頼区間ではない |

G7の速度の分子は、最初の1 tokenを除いた`predicted_n - 1`である（[使用版の実装](https://github.com/GenerelSchwerz/llama.cpp/blob/50df2c7cf761a4647bd2555cb4e0f0fabdaeef11/tools/server/server-common.h#L410)）。
最初のtokenはprompt処理から得られるため、APIの定義に従って生成時間との比を照合した。
公開CSV/JSONLの`timed_tokens`がこの分子、`output_tokens`が最初のtokenも含めた総生成数を示す。

再起動で揃うのは、前のリクエストから引き継ぐプロセス内状態である。
各表の「新規」はこの状態を指し、OSまで含めた全キャッシュの消去を意味しない。
今回の入力をprefillする間にもexpertキャッシュは変わるので、直接入力と長いHarness入力で、生成開始時の中身まで同一になるわけではない。
OS・ドライバ等のキャッシュやバックグラウンド負荷も完全には固定していない。
seedを固定しても、応答長・生成内容が3回とも同じになるとは限らない。

G7とS31はcontext、KV、MTP、sampling、テンプレートが異なる。
これらを保持した設定別の速度を示しており、エンジンだけを変更した比較ではない。
詳細は[初回探索の測定方法](methodology.md)を参照。

### 初回の表との関係

| 設定 | 旧：直接入力 tok/s（token数） | 旧：Harness入力 tok/s（token数） |
| --- | ---: | ---: |
| G7 | 61.68（25,930） | 60.26（6,274） |
| S31 | 109.85（18,993） | 121.62（5,207） |

旧表は各セル1回で、初回探索の記録をそのまま保持している。
初回探索では公開前の個人パスを含む入力を使用し、今回はパスを置換した公開fixtureをそのまま使用した。
また、応答の出力上限を32,768から65,536へ変更した。
そのため、旧値と新値の差をキャッシュだけの効果として扱わない。
キャッシュ履歴の影響は、今回のS31の2,048 token測定で1回目と2回目を対にして調べる。
この対でも生成内容が変わった場合は、キャッシュ単独の因果効果とは断定できない。
この短い再送での変化率を、旧表の長い応答へそのまま当てはめることもできない。

## 全30リクエスト

「新規」は再起動直後の1回目、「再送」は同一プロセスの2回目。`case_id`は保存ディレクトリ名と対応する。

| No. | プロセス | 設定 | 測定 | 入力 | 状態 | tok/s | 入力token数 | 生成token数 | MTP採用率 | 終了理由 |
| ---: | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | [01](../results/cache-recheck/01-S31-harness-full-r1/) | S31 | 応答終了 | Harness | 新規 | 110.40 | 8,613 | 13,634 | 82.08% | tool_calls |
| 2 | [02](../results/cache-recheck/02-S31-direct-full-r1/) | S31 | 応答終了 | 直接 | 新規 | 105.78 | 58 | 23,735 | 73.74% | stop |
| 3 | [03](../results/cache-recheck/03-G7-harness-full-r1/) | G7 | 応答終了 | Harness | 新規 | 62.01 | 8,858 | 5,506 | — | tool_calls |
| 4 | [04](../results/cache-recheck/04-G7-direct-full-r1/) | G7 | 応答終了 | 直接 | 新規 | 61.84 | 58 | 25,930 | — | stop |
| 5 | [05](../results/cache-recheck/05-G7-direct-full-r2/) | G7 | 応答終了 | 直接 | 新規 | 62.32 | 58 | 25,930 | — | stop |
| 6 | [06](../results/cache-recheck/06-G7-harness-full-r2/) | G7 | 応答終了 | Harness | 新規 | 63.56 | 8,858 | 5,506 | — | tool_calls |
| 7 | [07](../results/cache-recheck/07-S31-direct-full-r2/) | S31 | 応答終了 | 直接 | 新規 | 97.03 | 58 | 28,650 | 74.69% | stop |
| 8 | [08](../results/cache-recheck/08-S31-harness-full-r2/) | S31 | 応答終了 | Harness | 新規 | 128.05 | 8,613 | 4,955 | 85.61% | tool_calls |
| 9 | [09](../results/cache-recheck/09-S31-harness-full-r3/) | S31 | 応答終了 | Harness | 新規 | 91.08 | 8,613 | 17,375 | 80.83% | tool_calls |
| 10 | [10](../results/cache-recheck/10-S31-direct-full-r3/) | S31 | 応答終了 | 直接 | 新規 | 99.25 | 58 | 28,025 | 72.80% | stop |
| 11 | [11](../results/cache-recheck/11-G7-harness-full-r3/) | G7 | 応答終了 | Harness | 新規 | 63.50 | 8,858 | 5,506 | — | tool_calls |
| 12 | [12](../results/cache-recheck/12-G7-direct-full-r3/) | G7 | 応答終了 | 直接 | 新規 | 62.34 | 58 | 25,930 | — | stop |
| 13 | [13](../results/cache-recheck/13-S31-harness-fixed-r1/) | S31 | 2,048上限 | Harness | 新規 | 115.34 | 8,613 | 2,048 | 82.18% | length |
| 14 | [13](../results/cache-recheck/13-S31-harness-fixed-r1/) | S31 | 2,048上限 | Harness | 再送 | 98.36 | 8,613 | 2,048 | 71.29% | length |
| 15 | [14](../results/cache-recheck/14-S31-direct-fixed-r1/) | S31 | 2,048上限 | 直接 | 新規 | 95.85 | 58 | 2,048 | 63.60% | length |
| 16 | [14](../results/cache-recheck/14-S31-direct-fixed-r1/) | S31 | 2,048上限 | 直接 | 再送 | 94.10 | 58 | 2,048 | 54.69% | length |
| 17 | [15](../results/cache-recheck/15-G7-harness-fixed-r1/) | G7 | 2,048上限 | Harness | 新規 | 63.24 | 8,858 | 2,048 | — | length |
| 18 | [16](../results/cache-recheck/16-G7-direct-fixed-r1/) | G7 | 2,048上限 | 直接 | 新規 | 59.68 | 58 | 2,048 | — | length |
| 19 | [17](../results/cache-recheck/17-G7-direct-fixed-r2/) | G7 | 2,048上限 | 直接 | 新規 | 73.21 | 58 | 2,048 | — | length |
| 20 | [18](../results/cache-recheck/18-S31-harness-fixed-r2/) | S31 | 2,048上限 | Harness | 新規 | 119.79 | 8,613 | 2,048 | 84.15% | length |
| 21 | [18](../results/cache-recheck/18-S31-harness-fixed-r2/) | S31 | 2,048上限 | Harness | 再送 | 96.62 | 8,613 | 2,048 | 71.79% | length |
| 22 | [19](../results/cache-recheck/19-S31-direct-fixed-r2/) | S31 | 2,048上限 | 直接 | 新規 | 102.09 | 58 | 2,048 | 63.50% | length |
| 23 | [19](../results/cache-recheck/19-S31-direct-fixed-r2/) | S31 | 2,048上限 | 直接 | 再送 | 83.78 | 58 | 2,048 | 60.60% | length |
| 24 | [20](../results/cache-recheck/20-G7-harness-fixed-r2/) | G7 | 2,048上限 | Harness | 新規 | 62.42 | 8,858 | 2,048 | — | length |
| 25 | [21](../results/cache-recheck/21-S31-harness-fixed-r3/) | S31 | 2,048上限 | Harness | 新規 | 98.44 | 8,613 | 2,048 | 71.91% | length |
| 26 | [21](../results/cache-recheck/21-S31-harness-fixed-r3/) | S31 | 2,048上限 | Harness | 再送 | 103.29 | 8,613 | 2,048 | 69.16% | length |
| 27 | [22](../results/cache-recheck/22-S31-direct-fixed-r3/) | S31 | 2,048上限 | 直接 | 新規 | 92.11 | 58 | 2,048 | 62.63% | length |
| 28 | [22](../results/cache-recheck/22-S31-direct-fixed-r3/) | S31 | 2,048上限 | 直接 | 再送 | 95.49 | 58 | 2,048 | 57.95% | length |
| 29 | [23](../results/cache-recheck/23-G7-direct-fixed-r3/) | G7 | 2,048上限 | 直接 | 新規 | 73.21 | 58 | 2,048 | — | length |
| 30 | [24](../results/cache-recheck/24-G7-harness-fixed-r3/) | G7 | 2,048上限 | Harness | 新規 | 62.79 | 8,858 | 2,048 | — | length |

## データと追試

- [集計JSON](../results/cache-recheck/summary.json)：条件別中央値・最小・最大と、S31の各対の速度変化。
- [全測定CSV](../results/cache-recheck/results.csv) / [JSONL](../results/cache-recheck/results.jsonl)：生成数、生成時間、入力処理時間、終了理由、MTP採用率、実cache枠数。
- [保存記録](../results/cache-recheck/)：各プロセスの入力・応答・設定・engineログ。
- [GPU時系列](../results/cache-recheck/hardware.jsonl)：10秒間隔の値。生成中の真の極値や全負荷を捉えるものではない。
- [資産照合](../results/cache-recheck/asset-check.json) / [測定の出所](../results/cache-recheck/provenance.json)：照合済みハッシュと入力・スクリプトの版。
- [公開時のハッシュ対応](../results/cache-recheck/publication-manifest.json)：原記録とパス除去後のコピーの対応。

`semantic_output_sha256`は応答のcontent、reasoning_content、各tool callのfunctionを整列したJSONにして算出する。
ランダムに付くtool call IDは比較から除く。
ここでの「同じ生成内容」は、これらのフィールドの文字列が一致することを指す。
入力の公開コピーは、JSONとして読み込んだ本文が測定時と一致することを確認した。
ログや起動設定の個人パスは相対パスに置換し、改行はLFへ統一した。

環境構築は[追試手順](reproduce.md)を参照。
既存の推論サーバーを終了してから、リポジトリルートで実行する。

```powershell
python scripts/run_cache_recheck.py --plan plans/cache-recheck.json --output runs/cache-recheck-local
python scripts/summarize_cache_recheck.py --input runs/cache-recheck-local/results.jsonl --output runs/cache-recheck-local/summary.json
```

公開JSONLから集計の再計算だけを行う場合は推論を必要としない。

```powershell
python scripts/summarize_cache_recheck.py --input results/cache-recheck/results.jsonl --output runs/cache-recheck-summary.json
```

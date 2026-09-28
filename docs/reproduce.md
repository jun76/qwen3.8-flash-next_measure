# 追試手順

以下はWindows / NVIDIA CUDA向け。全パスはリポジトリルートを基準とする。
記録した重み・ソース版・引数を用意し、公開済みリクエストを再送する手順。
初回探索67リクエストでは入力を公開時に匿名化した。
追加再測定30リクエストは、その公開入力を用いて実測した。
両者の違いは[測定方法](methodology.md)と[再測定の記録](cache_recheck.md)に記載した。

## 1. 前提と配置

元の測定環境はRTX 5090 32GB、Core i7-14700、RAM 128GB、M.2 SSD。
S31やG7のキャッシュ予算をVRAM容量の異なる環境へ適用する場合は調整が必要。
Python 3.10以降、Git、NVIDIAドライバを使用。ソースビルドにはVisual Studio 2022 C++ Build Tools、CMake、Ninja、CUDA Toolkitが必要。
GenerelとStrataの実測ビルドはMSVC 19.44、CUDA 13.1、SM120。コマンドはx64の開発用PowerShellで実行する。

```powershell
git clone https://github.com/jun76/qwen3.8-flash-next_measure.git
Set-Location qwen3.8-flash-next_measure
New-Item -ItemType Directory -Force vendor, models | Out-Null
```

主な配置先：

```text
models/IQ3_S/                 # 本体GGUFの2分割ファイル
models/MTP/                   # llama.cpp用Q4_K_M / Q8_0 head
vendor/llama-generel/          # 固定コミットからビルド
vendor/llama-unsloth/          # 固定リリースの展開内容
vendor/cuda-runtime/           # 必要な場合、CUDA runtime DLL
vendor/strata/                 # 固定コミット、venv、engine、pack、MTP
artifacts/strata/              # 拡張expert配置表
runs/                         # 新しく実行した測定結果
```

これらの大きな資産と`runs/`はGit対象外。別の場所に既にある場合は[paths.example.json](../configs/paths.example.json)を`configs/paths.local.json`へコピーして必要なキーだけ上書きする。
初期値は全て相対パス。個人用の上書きでは絶対パスも指定できるが、そのファイルを公開しない。

## 2. 本体モデルとllama.cpp用MTP

本体は[ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/main/IQ3_S)のIQ3_Sを使用する。
2ファイル合計は約83.62 GB（10進数）。次のファイル名で配置する。

```text
models/IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf
models/IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf
```

Hugging Face CLIがある場合の取得例：

```powershell
hf download ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF --include "IQ3_S/*.gguf" --revision 2a55d75962e22f7a4a1d9963ab6eae3678537831 --local-dir models
```

本体の取得時Hubリビジョンは記録していないが、公開準備時に上記リビジョンのLFSハッシュと実測ファイル2本のSHA-256が一致することを確認した。[assets.json](assets.json)で取得後にも照合できる。

U1–U3/U5/G2/G4/G5には[Unsloth配布MTP head](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/tree/38bb39ee97821de2c9009abb7e93950eec396e66/MTP)も必要。
G7だけを試す場合は不要。

```powershell
hf download unsloth/Qwen3.8-Flash-Next-GGUF "MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf" "MTP/mtp-Qwen3.8-Flash-Next-shared-Q4_K_M.gguf" --revision 38bb39ee97821de2c9009abb7e93950eec396e66 --local-dir models
```

Q4/Q8とも、実測ファイルのSHA-256と上記リビジョンのLFSハッシュの一致を確認した。

## 3. GenerelSchwerz版llama.cpp（G1–G7）

```powershell
git clone https://github.com/GenerelSchwerz/llama.cpp.git vendor/llama-generel
git -C vendor/llama-generel checkout 50df2c7cf761a4647bd2555cb4e0f0fabdaeef11
cmake -S vendor/llama-generel -B vendor/llama-generel/build-sm120 -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DGGML_NATIVE=ON -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF
cmake --build vendor/llama-generel/build-sm120 --target llama-server -j 12
```

`CUDA_PATH`は使用するCUDA Toolkitを指すようにする。ランナーはその`bin`と`bin/x64`をDLL検索パスへ追加する。
`llama-server.exe`と生成されたDLL群を同じビルド配置に残す。SM120以外のGPUではarchとビルド先・`paths.local.json`を調整し、元の測定と異なる点を記録する。
このforkの6個の追加最適化、MoE cacheなどの全引数は[configs/llama_cpp.json](../configs/llama_cpp.json)にある。上流llama.cppへそのまま渡せる引数とは限らない。

## 4. Unsloth版llama.cpp（U1–U5、必要な場合）

[b11160-mix-a6922ccのWindows x64 CUDA13-newer ZIP](https://github.com/unslothai/llama.cpp/releases/download/b11160-mix-a6922cc/app-b11160-mix-a6922cc-windows-x64-cuda13-newer.zip)を展開し、`vendor/llama-unsloth/llama-server.exe`とDLL群が置かれるようにする。
配布ZIPのSHA-256は`4a3151489c1f2d3326118e64ffc71f6099f52e148b7a520b8bc980db56a39246`。
ソースコミットは`a3c12db9dfc9a5bdf93df199ec370e9faf117c69`、配布物のビルド情報は[unsloth-build-info.json](unsloth-build-info.json)。

元の実験では[b11146向けCUDA 13.4 runtime ZIP](https://github.com/ggml-org/llama.cpp/releases/download/b11146/cudart-llama-bin-win-cuda-13.4-x64.zip)のDLLを併用した。展開したruntime DLLを`vendor/cuda-runtime/`へ置く。ZIPとDLLのハッシュは[sources.json](sources.json)と[assets.json](assets.json)に記録した。
CUDA runtimeも速度や互換性に影響し得るため、追試時に使用版を記録する。
U1の全argvには保存記録から復元した部分がある。[測定方法の注記](methodology.md)を参照。

## 5. Strata（S01–S31）

固定版へ測定前からの局所修正を適用する。既に用意したGGUFを指定し、native IQのpack、tokenizer、Q2_0 MTP runtimeを作る。

```powershell
git clone https://github.com/Niko1221/Strata.git vendor/strata
git -C vendor/strata checkout 6c4c8c1dfafc16fa0ea7fc80c12c79f93b9f7eee
git -C vendor/strata apply ../../patches/strata-local.patch
python -m venv vendor/strata/.venv
& ./vendor/strata/.venv/Scripts/python.exe -m pip install -r docs/requirements-strata-recorded.txt
& ./vendor/strata/.venv/Scripts/python.exe vendor/strata/setup.py --family qwen --model IQ3_S --context 262144 --vision no --yes --setup --no-start --build --gguf-dir (Resolve-Path models/IQ3_S).Path
python scripts/expand_expert_profile.py
```

先にvenvを作り、そのPythonで`setup.py`を実行する。setupは追加の依存関係、ソースビルド、モデルの準備を行う。`--no-start`で測定用サーバーはまだ起動しない。
元のStrata venvはPython 3.12.10。[主要Python依存関係](strata-python-environment.json)も記録している。上記pip行で主要依存版を合わせる。
ggml用llama.cppは`3cf03257f219afbe7334045ff7c6a06ac68c627d`を取得する。
native IQでは本体GGUFのexpertを直接読む。StrataのQ2_0 MTPはQwenのBF16 checkpointからMTP部分を取得して変換するもので、llama.cpp用Q4/Q8 headとは別資産。
MTP取得元mainのHubリビジョンは元記録にないため、[変換後ファイルのハッシュ](assets.json)と[取得tensorの記録](strata-mtp-tensors.json)を同梱した。

上記setupによる主なビルド設定は`STRATA_ENABLE_CUDA=ON`、`STRATA_BUILD_TESTS=OFF`、Release、Ninja、実機GPUのCUDA arch。
元のRTX 5090ビルドはarch=120、CUDA 13.1。`STRATA_GGML_DIR`はsetupが取得した`vendor/strata/third_party/llama.cpp`。

配置表拡張スクリプトは元の8,000件を保持して24,576件へ拡張する。期待するハッシュ：

- 元：`2504ff83d9dcacc80e503dfe02b06d139a3170b914241b69eac728009f9a1300`
- 拡張後：`49535f57316381f92a2bca33ae9003b21f13c2a1f1d8071eb96fdf655144991a`

S31の差分は`--expert-profile`を拡張配置表へ変更、`--vram-reserve-mib 3072`、`--adapt-every 1`。
基準S01のspec=4、spec-min-p=0.5、context=262144、KV=int8を保持する。
native IQで使うこの経路はspecを2以上にする前提で、MTP無効のケースを31設定へ含めていない。

## 6. 資産の照合

```powershell
# 本体2ファイルだけを照合（約84 GBを読むため時間がかかる）
python scripts/verify_assets.py --group model

# Strataの準備済み資産も照合
python scripts/verify_assets.py --group strata
```

ビルドしたexeはコンパイラや配置でハッシュが変わり得る。`--group binaries`は元バイナリとの同一性を確認する用途で、同じソースからのビルド成功判定には使わない。
重み・runtimeはGitへ追加せず、版とハッシュを記録する。

## 7. 測定

他の推論サーバーを終了し、片方ずつ実行する。既定ポートはllama.cppが8081、Strataが8082。
このランナーは既存サーバーを自動終了しない。ポート競合、他の既知ポートの推論サーバー、開始前GPU0空きVRAM 8 GiB未満を検出すると停止する。
開始後の空きVRAMが512 MiB未満でも生成を止める。これは速度やメモリ不足を完全に防ぐ保証ではない。

```powershell
# quick：G7 1回、またはS01/S31を各1回
python scripts/run_benchmarks.py --plan plans/llama_cpp-quick.json --dry-run
python scripts/run_benchmarks.py --plan plans/strata-quick.json --dry-run
python scripts/run_benchmarks.py --plan plans/llama_cpp-quick.json
python scripts/run_benchmarks.py --plan plans/strata-quick.json

# 初回パラメータ探索の再生：llama.cpp 22回 / Strata 45回
python scripts/run_benchmarks.py --plan plans/llama_cpp.json
python scripts/run_benchmarks.py --plan plans/strata.json

# 指定設定だけ（プラン内の再測定も保持）
python scripts/run_benchmarks.py --plan plans/strata.json --configs S01,S30,S31
```

`--dry-run`は引数と入力ファイルを表示するだけ。全プランは長い応答と多数のモデル再読込を含むため時間がかかる。
`--configs`で前の設定を省いても、選んだプロセスグループ内のリクエスト順は保持する。
別GPU容量に合わせてガードを変更する場合は`--min-free-vram-mib`、ポート変更は`--port`を指定する。

### キャッシュ条件を揃えた再測定

G7/S31 × 直接/Harnessの4組を、応答終了まで各3回、2,048 token上限で各3回測る。
さらにStrataの2,048 token測定では、同じプロセスで同じリクエストをもう1回送る。
合計24プロセス・30リクエストで、実行順は[cache-recheck.json](../plans/cache-recheck.json)に固定した。

```powershell
# 設定と入力の存在確認のみ。生成は開始しない
python scripts/run_cache_recheck.py --plan plans/cache-recheck.json --output runs/cache-recheck-local --dry-run

# 全30リクエストを実行。既存の出力ディレクトリは上書きしない
python scripts/run_cache_recheck.py --plan plans/cache-recheck.json --output runs/cache-recheck-local

# 中央値・観測範囲と、Strataの同一プロセス内での速度変化を集計
python scripts/summarize_cache_recheck.py --input runs/cache-recheck-local/results.jsonl --output runs/cache-recheck-local/summary.json
```

この追加ランナーは、開始前の空きVRAMを24,000 MiB以上、起動後を512 MiB以上とするガードを設けている。
測定中は他の推論サーバーを終了しておく。
promptキャッシュは無効とし、OSのファイルキャッシュは消去しない。
Strataの2回目だけexpertキャッシュなどのプロセス内状態を引き継ぐ。
GPUの使用量・温度・クロックを10秒間隔で`hardware.jsonl`へ記録する。
詳しい統制条件と限界は[再測定の記録](cache_recheck.md)を参照。

中断した場合は`--start-at`と`--stop-after`でプラン内のプロセス番号を指定できる。
再開先には別の未作成ディレクトリを使い、同じ`case_id`の重複を除いてから集計する。
Strataの新規プロセスと継続プロセスの組は、両リクエストが揃っている必要がある。

## 8. 新しい結果の保存・共有

`runs/<日時>-<engine>/`にプラン、プロセス別設定・ログ・起動状態、リクエスト・応答、`results.jsonl`を保存する。
`config_id`、`historical_run`、`request_in_process`により元の実験と対応付けられる。
追加再測定では`case_id`、`phase`、`repetition`、`cache_start`で条件と繰り返しを識別する。
request/responseは保存するが、生成されたツール呼び出しは実行しない。DeepSeek HarnessのインストールやWeb認証は追試に不要。

新しく生成されたconfigやログには、追試したPCの解決後の絶対パスが入る。`runs/`と`paths.local.json`はGit対象外のまま保ち、共有する際は公開用コピーを作ってパスを除去する。
速度と合わせて、ハードウェア、ソース版、モデルハッシュ、sampling、context、KV、MTP、実cache量、起動後何回目か、入力・生成token数を記録すると比較しやすい。

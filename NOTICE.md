# Third-party material and attribution

This repository contains experiment records and scripts, not bundled model weights or inference engines.

- The original scripts, configuration templates and explanatory documents written for this repository are available under the [MIT License](LICENSE).
- Captured DeepSeek Harness prompt and tool definitions come from [`@deepseek-ai/dsh`](https://github.com/deepseek-ai/deepseek-harness), version 0.1.5-rc.1. Its MIT license and copyright notice are included in [licenses/deepseek-harness-MIT.txt](licenses/deepseek-harness-MIT.txt). Local paths in the captured material have been normalized.
- Strata source, model assets and expert-profile binaries are not redistributed here. The [small local patch](patches/strata-local.patch) documents changes to the pinned upstream source; pre-existing upstream portions remain subject to their upstream terms. No repository-wide license was found in the pinned Strata checkout; this repository does not assign a license to Strata itself.
- llama.cpp engines, CUDA libraries and model weights must be obtained from their respective upstream projects and used under their respective terms. See [source versions](docs/sources.json).
- `results/` contains path-normalized factual measurement records, inference logs and model responses. `artifacts/generated/` contains HTML extracted from those responses, including an uncorrected syntax-failure example. Responses and embedded third-party content are retained as experimental evidence; the repository license does not replace applicable third-party terms.

The names Qwen, Strata, llama.cpp, Unsloth, GenerelSchwerz and DeepSeek identify the projects used in the experiment. This is an independent experiment, not an official benchmark from those projects.

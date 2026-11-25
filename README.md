# Chunqing-Dai-research

持续推进气象与大气遥感相关的 autoresearch 工作，按周更新研究结果。

## 当前阶段

当前处于 P0 的 M0 审计和启动阶段，目标是建立一个可复现的 MODIS/AERONET AOD 基准。仓库已经固定数据契约、时间切分、基线模型、指标和实验记录格式，并补充了从零启动说明、代理工作协议和结果门控。

详细研究方向和验收规则记录在 GitHub Issue [#1](https://github.com/LZF1111/Chunqing-Dai-research/issues/1) 和 [`program.md`](program.md) 中。

## 快速开始

项目使用 Python 3.10 或更高版本。新用户先阅读 [`GETTING_STARTED.md`](GETTING_STARTED.md)，再用仓库内的合成样例验证完整流程。

```powershell
python -m pip install -e .
python scripts/generate_example_data.py
python prepare.py --input data/example_collocations.csv --dataset-kind synthetic
python train.py --model satellite --data-dir data/processed --artifact-dir artifacts/satellite
python evaluate.py --data-dir data/processed --artifact-dir artifacts/satellite --split validation
python run_experiment.py --model ridge --data-dir data/processed --experiment-id smoke-ridge --hypothesis "Verify the complete smoke-test execution path"
python gate.py --candidate artifacts/smoke-ridge/validation_metrics.json --experiment-id smoke-ridge --initialize --smoke-only
```

样例数据只用于检查程序入口和结果格式，不能作为科学结论。真实实验需要按照 [`data/README.md`](data/README.md) 生成 MODIS/AERONET 配准数据，并保存数据版本和文件哈希。

## 当前入口

- [`prepare.py`](prepare.py) 验证配准数据、执行确定性的时间或站点切分，并生成 manifest。
- [`train.py`](train.py) 训练均值、卫星原值、岭回归、随机森林和小型 MLP 基线。
- [`evaluate.py`](evaluate.py) 使用固定评估逻辑输出总体指标和 AOD 分层指标。
- [`run_experiment.py`](run_experiment.py) 在固定超时下运行一次实验，保存完整日志并追加 JSONL 记录。
- [`gate.py`](gate.py) 根据固定的指标门槛接受、拒绝或初始化一个实验基线。
- [`scripts/run_seed_sweep.py`](scripts/run_seed_sweep.py) 在多个 seed 上重复同一假设并生成汇总结果。
- [`program.md`](program.md) 定义研究目标、可修改范围、资源预算和接受规则。
- [`AGENT_PROMPT.md`](AGENT_PROMPT.md) 定义交给实验代理的启动提示词和每轮工作协议。
- [`AUDIT_REPORT.md`](AUDIT_REPORT.md) 保存最近一次仓库审计结论和待办项。

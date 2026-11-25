# 从零启动 P0 autoresearch

本文面向第一次接触本项目的用户。目标是先跑通可审计的软件流程，再接入真实 MODIS/AERONET 配准数据，最后开启固定预算的自动实验。

## 1. 环境准备

项目需要 Python 3.10 或更高版本。建议使用独立环境。

```powershell
git clone https://github.com/LZF1111/Chunqing-Dai-research.git
cd Chunqing-Dai-research

python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

如果本机的 `python` 缺少标准库或无法创建虚拟环境，请改用完整的 Python 或 Conda 环境，并在实验记录中保存 `python --version` 和 `python -m pip freeze` 的结果。

## 2. 运行软件冒烟测试

```powershell
python scripts/generate_example_data.py
python prepare.py --input data/example_collocations.csv --dataset-kind synthetic
python run_experiment.py `
  --model ridge `
  --data-dir data/processed `
  --experiment-id smoke-ridge `
  --hypothesis "Verify the complete smoke-test execution path" `
  --timeout-seconds 120
```

检查以下文件已经生成：

- `data/manifest.json`
- `data/processed/train.csv`
- `data/processed/validation.csv`
- `data/processed/test.csv`
- `artifacts/smoke-ridge/record.json`
- `artifacts/smoke-ridge/validation_metrics.json`
- `results/experiments.jsonl`

样例数据全部为合成数据，只用于验证程序入口、日志和文件格式。它不参与真实研究结论。

## 3. 接入真实数据前的检查

真实数据接入前，先阅读并完成：

1. [`program.md`](program.md)
2. [`data/README.md`](data/README.md)
3. [`decisions/0001-freeze-p0-aod-protocol.md`](decisions/0001-freeze-p0-aod-protocol.md)
4. [`AUDIT_REPORT.md`](AUDIT_REPORT.md)

真实输入必须是已经完成卫星过境与 AERONET 站点匹配的 CSV。当前数据入口会验证字段、时间、数值范围和切分。原始 HDF、AERONET 下载文件和大型中间文件放在本地缓存或外部存储中，源文件哈希写入 manifest。

## 4. 运行真实基线

```powershell
python prepare.py `
  --input data/collocations.csv `
  --dataset-kind real `
  --collocation-metadata data/collocation_metadata.json

python run_experiment.py --model mean --data-dir data/processed --experiment-id baseline-mean --hypothesis "Establish the training-mean reference"
python run_experiment.py --model satellite --data-dir data/processed --experiment-id baseline-satellite --hypothesis "Establish the official satellite AOD reference"
python run_experiment.py --model ridge --data-dir data/processed --experiment-id baseline-ridge --hypothesis "Establish the linear calibration reference"
python run_experiment.py --model random_forest --data-dir data/processed --experiment-id baseline-random-forest --hypothesis "Establish the tree-model reference"
python run_experiment.py --model mlp --data-dir data/processed --experiment-id baseline-mlp --hypothesis "Establish the neural-network reference"
```

先检查各基线的验证指标、AOD 分层指标、样本数和日志，再初始化第一个基线：

```powershell
python gate.py `
  --candidate artifacts/baseline-satellite/validation_metrics.json `
  --experiment-id baseline-satellite `
  --initialize
```

初始化的模型和选择理由必须写入 `decisions/` 或阶段性报告。官方卫星 AOD 是业务基线，通常应作为比较对象保存。

## 5. 启动实验代理

把 [`AGENT_PROMPT.md`](AGENT_PROMPT.md) 作为新会话的初始提示词。代理的工作目录必须是仓库根目录。第一轮只允许人工监督模式，完成若干基线和候选实验后再开启自动循环。

每次实验都应能回答四个问题：改了什么，为什么改，使用了哪一版数据，结果是否通过固定门控。

进入 M1 后，使用多 seed 汇总入口：

```powershell
python scripts/run_seed_sweep.py `
  --model ridge `
  --experiment-id ridge-feature-v1 `
  --hypothesis "观测几何特征可以降低跨站点验证误差"

python gate.py `
  --candidate artifacts/ridge-feature-v1-seed-summary/seed_summary.json `
  --experiment-id ridge-feature-v1
```

## 6. 结束一次研究轮次

阶段性轮次结束时，保存以下内容：

- 当前最佳实验编号
- 训练、验证和测试协议
- 数据 manifest 哈希
- 所有实验的成功和失败记录
- 通过门控的 Git commit
- 运行资源和时间
- 分层指标退化检查
- 需要人类决定的开放问题

完整审计清单见 [`AUDIT_REPORT.md`](AUDIT_REPORT.md)。

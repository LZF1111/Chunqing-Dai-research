# Issue #1 本地研究上下文

## 来源

- 仓库：https://github.com/LZF1111/Chunqing-Dai-research
- Issue：https://github.com/LZF1111/Chunqing-Dai-research/issues/1
- 本地快照日期：2026-11-25

## 当前目标

建立可以长期运行和审计的 atmospheric remote sensing autoresearch。当前优先推进 P0 MODIS/AERONET AOD 交叉校准，后续再扩展到 TROPOMI NO₂、AIRS 廓线和其他方向。

## 当前阶段

当前阶段是 M0 审计和真实数据准备。仓库已经具备：

- 配准 CSV 的字段和数值检查
- 按年份的时间切分
- 按站点的留出切分
- 均值、官方卫星 AOD、岭回归、随机森林和 MLP 基线
- 固定评估指标
- 单次实验日志
- 结果门控入口

真实 MODIS 文件下载、AERONET 文件下载和自动空间配准仍属于接入工作。接入完成前，合成样例只能用于软件检查。

## 研究范围

第一阶段使用官方卫星 AOD、质量标志、观测几何、位置、地表类型和可选气象特征。标签使用 AERONET Version 3 Level 2.0 的 500 nm AOD。反射率到 AOD 的完整反演任务单独登记为 Track B。

## 进入 M1 的条件

真实数据 manifest 已冻结，时间和站点留出结果已生成，所有基线均已记录，数据泄漏审计通过，且 `gate.py` 已经在多个 seed 上验证过接受和拒绝逻辑。

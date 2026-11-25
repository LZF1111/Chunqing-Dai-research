# P0 配准数据契约

`prepare.py` 接受一个 CSV 文件。每行代表一个已经完成卫星过境与 AERONET 站点匹配的样本。原始卫星文件、AERONET 下载文件和大型中间文件保存在本地缓存或外部存储，仓库只保存处理代码、字段说明和小型软件样例。

## 字段分级

每行代表一个已经完成卫星过境与 AERONET 站点匹配的样本。字段分为必需字段和可选辅助字段。缺失的可选字段会保留为空值，由训练管线在训练集上拟合中位数后填充。

### 必需字段

| 字段 | 类型 | 含义 | 约束 |
| --- | --- | --- | --- |
| `station_id` | string | AERONET 站点标识 | 不能为空 |
| `timestamp` | ISO 8601 | 卫星过境或配准时间 | 必须可解析 |
| `latitude` | float | 站点纬度 | -90 到 90 |
| `longitude` | float | 站点经度 | -180 到 180 |
| `aeronet_aod_500` | float | AERONET 500 nm AOD 标签 | 大于等于 0 |
| `satellite_aod` | float | 官方卫星 AOD 基线 | 大于等于 0 |
| `qa_value` | float | 卫星质量标志 | 0 到 1 |
| `solar_zenith_deg` | float | 太阳天顶角 | 0 到 180 |
| `view_zenith_deg` | float | 卫星观测天顶角 | 0 到 180 |
| `relative_azimuth_deg` | float | 相对方位角 | 0 到 360 |
| `surface_type` | string | 地表类型 | 不能为空 |
### 可选辅助字段

| 字段 | 类型 | 含义 | 约束 |
| --- | --- | --- | --- |
| `air_temperature_k` | float | 2 m 气温 | 缺失或 150 到 350 K |
| `relative_humidity_pct` | float | 相对湿度 | 缺失或 0 到 100% |
| `boundary_layer_height_m` | float | 边界层高度 | 缺失或大于 0 m |

`air_temperature_k`、`relative_humidity_pct` 和 `boundary_layer_height_m` 目前作为可用辅助特征。字段缺失或单行缺失都必须在 manifest 中记录。缺失值填充只能使用训练集统计量。

## 配准记录

真实配准数据还应包含以下审计字段。它们在当前训练特征中不直接使用，但必须保留在中间数据或配准日志中：

- 卫星产品名称和版本
- 卫星原始文件标识
- AERONET 原始文件标识
- 卫星过境时间和 AERONET 匹配时间范围
- 空间窗口定义
- 有效像元数量
- 像元聚合方式
- 质量筛选规则编号
- 每个源文件的 SHA-256

真实数据还需要一个配准元数据 JSON。可以复制 [`collocation_metadata.example.json`](collocation_metadata.example.json) 后填写，并通过 `--collocation-metadata` 传给 `prepare.py`。`dataset_kind=real` 时，产品版本、质量规则和每个源文件的 SHA-256 都必须已经填写。

## 输出文件

运行 `prepare.py` 后，输出目录包含 `train.csv`、`validation.csv` 和 `test.csv`。数据目录的上一级生成内容确定的 `manifest.json`，其中记录数据来源类别、源文件哈希、保留与拒绝样本数、切分年份、特征字段、可选字段缺失率、处理脚本哈希和处理后 split 文件哈希。生成时间和本机绝对路径不写入 manifest。

`example_collocations.csv` 由脚本生成，只用于软件冒烟检查，所有数值均为合成数据。

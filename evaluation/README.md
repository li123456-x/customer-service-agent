# Top K 小样本评测

此目录只增加离线评测能力，不修改应用默认参数，不删除、重建或写入 Milvus，也不写入 PostgreSQL 业务表。

本轮结果见 [top_k_report.md](top_k_report.md)。只有10篇短文档，因此结论只适用于当前验证语料。

## 文件

- `top_k_dataset.json`：60道问题、开发/留出划分及原始条款金标准。无需给每种切分重新标注Chunk ID。
- `top_k.py`：只读检索、缓存查询向量、模型调用预算和复用现有回复节点的生成测试。
- `test_top_k.py`：覆盖评分、等价依据、分片跨度、未完成实验拒绝汇总及预算保护的单元测试。
- `answer_reviews.json`：本轮助手逐条审阅记录，不是独立人工盲评。没有另付费调用评审模型。
- `report.py`：不调用API，校验快照和完整评审后生成报告。
- `results/`：本地原始输出及缓存，默认不提交Git。不得公开API Key或真实客户数据。

## 运行

在项目根目录和原来的Python环境中运行：

```powershell
python -X utf8 -m unittest evaluation.test_top_k -v
python -X utf8 -m evaluation.top_k validate
```

以下两步会产生服务费用，运行前需确认授权额度和配置。已有目录会复用缓存，不重复成功请求：

```powershell
python -X utf8 -m evaluation.top_k retrieve
python -X utf8 -m evaluation.top_k generate
```

原始结果完成且评审记录匹配后，可以离线重建报告：

```powershell
python -X utf8 -m evaluation.report
```

程序先比较本地切分和Milvus中的`source`、`text`。如果内容不一致，会停止而不是替你重建索引。

## 方法与限制

仅改变K=1、3、5、8；查询向量每题生成一次。先按开发集检索表现挑选非3的候选，再在预先指定的20道生成题上比较候选与基线，共40次。

生成复用`knowledge_only_context_node`和`generate_reply_node`，不进入意图分流或会写库的`finish`，因此不是完整客服端到端评测。

生成测试固定temperature=0、输出上限900 Token、超时45秒并禁用重试。生产模型初始化不改变。每题只生成一次，本轮未评估采样波动和并发。

每个输出目录最多计数80次Embedding和40次DeepSeek尝试。失败调用也计数；DeepSeek失败后停止，不将规则兜底当成模型成功回答。额度按目录计数，不是账户级费用锁，新目录必须重新确认费用授权。

只读数据快照确认文本一致，不证明历史向量一定由指定模型生成；本轮使用项目配置的Embedding检索已有向量，没有重嵌入整个知识库。

知识库来源和题集由同一助手构造，仍可能共享政策条款；仅场景分组不等于真实流量隔离。结果不能写成线上准确率，不能因为语义相似度高就算回答正确。

新版本题集或新费用授权后，独立实验使用新输出目录。报告生成前需对新答案重新评审，不能复用本轮评分记录。

## 切分与K联合评测

第二轮报告见 [chunk_grid_report.md](chunk_grid_report.md)。比较9组切分与4个K，共36组；原来的60题已观察，因此全部转为开发数据。新20道题在实验前冻结，见`chunk_validation.json`。

这轮复用旧查询向量，嵌入不同切分中的56段唯一文本及20个新问题；实际使用26次Embedding请求、没有调用DeepSeek。新运行上限60次Embedding，独立重测必须重新确认费用。

使用NumPy精确余弦排序，不创建或修改生产Milvus集合。只读比较基线向量时，本地与原Milvus的60个查询Top3排序全部一致；这一校验不能替代新配置的ANN和线上负载测试。

```powershell
python -X utf8 -m unittest evaluation.test_chunk_grid -v
python -X utf8 -m evaluation.chunk_grid prepare
python -X utf8 -m evaluation.chunk_grid run
python -X utf8 -m evaluation.chunk_grid report
```

`prepare`和`report`不调用付费API，`run`调用Embedding并只读核对Milvus。再次运行相同目录会复用向量缓存，不代表独立重测。生产参数没有变更。

实测500/0和500/80生成相同的14段文本，没有实际重叠。这是当前语料的结构属性，不意味着所有文档下80都无效。800超过当前全部文档长度，等于整篇检索，也不能推广到长文档。

## 相关性阈值与K联合比较

第三轮报告见 [threshold_k_report.md](threshold_k_report.md)。固定500/80，复用第二轮缓存的
Top8分数，对比K=1、3、5、8，以及不设阈值和0.30至0.80、步长0.05的阈值，共48组。
严格先取Top K再过滤，和当前生产逻辑一致。不调用任何API，不连接数据库，不修改生产参数。

```powershell
python -X utf8 -m evaluation.threshold_k
python -X utf8 -m unittest evaluation.test_threshold_k -v
```

原60题与上一轮20题都已被查看，因此本轮80题全部属于探索数据，没有新的独立留出集。
报告区分政策证据覆盖、库内空结果与库外仍有片段，后两项仅是拒答风险和误放行的代理，
不是最终回答正确率或幻觉率。缺少可接受风险上限时，不自动挑所谓最优阈值。
缓存或当前政策与快照不一致时直接停止，绝不会自动补发收费请求。

## 当前应用配置

2026-10-10在用户确认后，将应用暂定默认值改为Top 5、相关性阈值0.55，切分仍为500/80。
客服、管理Tool与前端管理检索未显式指定K时都读取后端配置，显式K仍可用于对照。
旧报告描述的是各次实验执行时的参数与行为，不为新默认值改写历史记录。
新默认值来自已观察数据的探索结果，尚未通过新的独立留出题和最终回答评测确认。

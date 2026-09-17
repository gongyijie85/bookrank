# Hunyuan-MT 图书翻译质量研究

> 研究范围：`tencent/Hunyuan-MT-7B`，通过 SiliconFlow 的 OpenAI 兼容 `chat/completions` 接口调用；目标是专业、自然且有文学感的简体中文书名、简介和图书详情。本文只依据模型/平台官方资料和翻译行业标准，并结合 BookRank3 当前实现提出建议。

## 结论

提升质量的关键不是继续堆叠“资深翻译家”角色描述，而是把任务改造成**有上下文、有术语约束、可验证的翻译流程**：

1. **遵循模型原生格式**：Hunyuan-MT 官方模板是一条 `user` 消息——“把下面的文本翻译成中文，不要额外解释”，且模型卡明确说明模型没有默认 `system_prompt`。当前实现把大段字段规则放在 `system`、把原文单独放在 `user`，应先以官方单消息模板为基线做 A/B 测试，而不是假定复杂 system prompt 一定生效。[Hunyuan-MT 官方模型卡](https://huggingface.co/tencent/Hunyuan-MT-7B#prompts)
2. **书名不能脱离整本书翻译**：标题请求至少要携带作者、类别、系列、简介摘要和专名表，解决人名、地名、双关与意象歧义；`Verity` 被字面译成“唯实”正是缺少人名上下文的典型错误。W3C ITS 2.0 将领域、术语、文本分析（实体/概念消歧）和本地化说明都定义为机器翻译可消费的上下文元数据。[W3C ITS 2.0](https://www.w3.org/TR/its20/)
3. **“专业”和“优美”分层处理**：先保证事实、人物关系、专名和情节完整，再在不增删信息的前提下调整中文语序、节奏和措辞。不要用一句“文学性书名采用意译”触发不受约束的再创作。
4. **术语表优先于模型记忆**：已出版中文书名、系列名、作者/角色名、机构名和出版社名应建立逐书/逐系列词表，并随请求注入。ISO 12616-1 要求建立可靠的双语/多语术语集合；W3C 也把违反指定术语表与普通误译分开处理。[ISO 12616-1:2021](https://www.iso.org/standard/72308.html) · [W3C ITS 2.0 质量问题类型](https://www.w3.org/TR/its20/#lqissue-typevalues)
5. **自动指标不能代替人工审校**：Hunyuan 团队同时使用 XCOMET/CometKiwi 和多语专家人工评价，并明确自动指标对某些翻译现象不可靠；人工评价关注准确、流畅和地道。书名尤其应进入人工抽样或低置信度审核队列。[Hunyuan-MT 技术报告](https://arxiv.org/abs/2509.05209)

## 模型事实与边界

- Hunyuan-MT-7B 是面向机器翻译专门训练的模型，支持英中双向翻译；其后训练包含约 300 万对第一阶段数据、约 26.8 万对高保真第二阶段数据，以及 20% 的通用/翻译指令数据。[Hunyuan-MT 技术报告](https://arxiv.org/abs/2509.05209)
- 官方推荐推理参数为 `temperature=0.7`、`top_p=0.6`、`top_k=20`、`repetition_penalty=1.05`。这应作为复现实验基线；不能仅凭通用经验断言翻译一定应使用更低温度。[Hunyuan-MT 官方模型卡](https://huggingface.co/tencent/Hunyuan-MT-7B#use-with-transformers)
- SiliconFlow 的接口支持 `temperature`、`top_p`、`top_k`、`frequency_penalty`、`n`、`stop` 和 `response_format`，并返回 `finish_reason`、token 用量和可用于排障的 trace id。其通用文档列出的默认值包括 `top_k=50`、`frequency_penalty=0.5`，并不等于 Hunyuan 模型卡的推荐参数。[SiliconFlow Chat Completions](https://docs.siliconflow.cn/docs/api/chat-completions-post)
- 技术报告承认非字面语言、新词、俚语、专业术语和地名仍是机器翻译难点。报告的基准主要是通用句段与 WMT 数据，并未证明模型在出版书名“再创作”或正式中文书名检索上达到专业编辑水平。[Hunyuan-MT 技术报告](https://arxiv.org/abs/2509.05209)
- 报告发现普通 Chain-of-Thought 对翻译质量提升有限；更高质量版本 Chimera 使用专门训练的融合模型综合多个候选，而不是让基础模型输出长篇推理。因此生产翻译不应要求模型展示思考过程。[Hunyuan-MT 技术报告](https://arxiv.org/abs/2509.05209) · [Chimera 官方提示模板](https://huggingface.co/tencent/Hunyuan-MT-7B#prompt-template-for-hunyuan-mt-chmeria-7b)

## 推荐的翻译流程

### 1. 翻译前：建立“图书上下文包”

每本书先构造一次上下文，并供标题、简介和详情共享：

```text
作者：Colleen Hoover
原文书名：Verity
类别：psychological thriller / romantic suspense
系列：非系列
目标读者：大众小说读者
简介：Lowen is hired to complete Verity Crawford's books ...
强制术语：
- Verity Crawford => 维丽蒂·克劳福德（人物）
- Lowen Ashleigh => 洛温·阿什利（人物）
已确认书名：无
```

上下文中的“已确认书名”必须来自可追溯的出版社、ISBN/馆藏或人工记录；模型生成的名称不能标记为官方译名。W3C ITS 2.0 明确支持向翻译工具传递领域、术语、实体消歧、本地化说明和外部资源等元数据。[W3C ITS 2.0 数据类别](https://www.w3.org/TR/its20/#datacategories-defaults-etc)

优先级应固定为：**已确认正式译名 > 项目术语表 > 同系列既有译法 > 基于上下文的新译名**。这可避免同一角色或系列在不同页面出现多个译法。

### 2. 书名：保守消歧，再做有限度润色

书名的决策顺序：

1. 有可核验的简体中文正式译名时直接复用，不调用模型改写。
2. 标题是人物、地点、作品内专名或系列名时，用术语表辅助消歧，但不能把正文中的人物译名机械等同于书名译法。标题同时承担主题表达时，可以采用有文本依据的意译；例如 `Verity` 在正文中可作为人物名译为“维丽蒂”，作为书名则可结合“真相”这一词义与小说主题译为《真相》。
3. 无专名歧义时，先忠实保留核心意象、语气和类型承诺，再调整为简洁自然的中文；允许克制的出版化润色，但不能补写原文没有的情节或噱头。
4. 双关无法兼得时，优先保留与简介/类别更相关的一层含义，并进入人工复核；不要虚构“官方感”很强的四字标题。

建议以官方模板为骨架，把规则和上下文都放进同一条 `user` 消息：

```text
把下面的英文图书标题翻译成简体中文，只输出一个中文书名，不要额外解释。

要求：
- 忠实保留标题的核心含义、意象、语气和类型特征；中文简洁自然。
- 先依据上下文判断标题是否为人名、地名、系列名、习语或双关。
- 正文专名必须采用术语表中的译名；书名若同时承载主题含义，可结合简介作有依据的意译，不机械照搬人物音译。
- 不加书名号，不输出英文原文、标签、备选项或说明。

上下文（只用于消歧）：
作者：{author}
类别：{category}
系列：{series}
简介：{description_excerpt}
术语表：{glossary}

待翻译标题：
{title}
```

对高曝光或歧义标题，可用相同上下文独立生成 2–3 个候选，再由人工编辑选择。若平台未来提供 Hunyuan-MT-Chimera，可按官方多候选融合流程试验；不要把基础 Hunyuan-MT-7B 当作等价的 Chimera 自评器。官方报告显示 Chimera 综合多候选后，在 Flores-200 各方向的 XCOMET-XXL 平均提升约 2.3%，但这仍不是书名专项结果。[Hunyuan-MT 技术报告](https://arxiv.org/abs/2509.05209)

### 3. 简介：锁定专名和书名，再翻译完整段落

简介应在书名定稿后翻译，并把定稿书名、人物名和系列名作为强制术语传入。不要逐句调用，否则跨句指代、人物身份和文风会漂移。

```text
把下面的英文图书简介翻译成简体中文，只输出译文，不要额外解释。

要求：
- 完整、准确传达情节、人物关系、时间、否定和语气，不增删事实，不剧透原文未透露的信息。
- 在忠实基础上使用自然、凝练、有节奏的现代中文，消除英文语序痕迹；保持原段落结构。
- 必须一致使用术语表。书名用《》；人名不附英文；数字、日期和专有标识准确保留。
- 不添加宣传口号、评价、标签、注释或 Markdown。

图书上下文：
标题：{title} => {title_zh}
作者：{author}
类别与受众：{category}; {audience}
术语表：{glossary}

待翻译简介：
{description}
```

“首次出现专名一律附英文”的现有规则不适合大众图书简介：它会让成文像术语说明书。仅对没有稳定中文译名、且读者确有识别需要的机构/奖项保留英文；人物名和常见地点服从词表即可。

### 4. 图书详情：能结构化转换的字段不要交给模型

ISBN、价格、页数、日期、语言代码和版式等应由确定性规则处理；只把出版社名称、装帧说明等真正需要语言转换的字段交给模型。这样可避免模型改动数字、货币或标识符。需要翻译的详情仍应注入出版社术语表，并要求保持键、顺序和原始数值。

## 参数与候选策略

先建立三组实验，不直接在全量数据上凭感觉改参数：

| 组别 | 消息与参数 | 用途 |
|---|---|---|
| A 官方基线 | 单条 `user`；`temperature=0.7, top_p=0.6, top_k=20, repetition_penalty=1.05` | 验证官方可复现表现 |
| B 上下文提示 | 单条 `user`；与 A 相同参数；加入字段规则、上下文和术语表 | 单独衡量提示与上下文收益 |
| C 稳定性对照 | 与 B 相同；仅将 `temperature` 改为 `0.3` 或 `0.5` | 衡量专名一致性与文采之间的取舍 |

一次只改变一个变量。当前代码只设置 `temperature=0.3`，没有显式传入官方建议的 `top_p/top_k/repetition_penalty`，因此目前不能把结果简单归因于“模型不行”或“温度低”。SiliconFlow 文档对 temperature 的定义只是控制随机程度，并未给出 Hunyuan 的专属最优值；最终选择必须依据 BookRank3 自己的盲评结果。[SiliconFlow Chat Completions](https://docs.siliconflow.cn/docs/api/chat-completions-post)

还要注意参数名称并不等价：Hunyuan 推荐的是 `repetition_penalty=1.05`，而 SiliconFlow 公开接口只列出 `frequency_penalty`。不能用后者的 `0.5` 默认值冒充前者。第一轮复现实验可显式设 `top_k=20`、`top_p=0.6`、`temperature=0.7`，并把 `frequency_penalty=0` 作为中性工程基线；同时用一个小请求确认 SiliconFlow 是否实际接受额外的 `repetition_penalty`。若未公开支持，就记录该平台差异，不要静默假定已应用。

标题候选可用多次独立请求生成；简介默认只生成一版，避免无谓成本和事实漂移。设置足够但不过大的 `max_tokens`，并检查 `finish_reason`，防止简介被截断。

## 质量评价与发布门槛

ISO 5060:2024建议用错误类型和罚分进行分析式评价，并覆盖人工翻译、机器翻译后编辑和未经编辑的机器翻译；它也强调评价者能力与抽样。[ISO 5060:2024](https://www.iso.org/standard/80701.html)

建议建立 100–200 本的版本化黄金集，按小说/非虚构/技术、普通标题/人名标题/双关标题/系列标题分层，至少包含当前已知错误。盲评旧版与候选版：

- **准确**：是否误译、漏译、增译；人物关系、否定、数字和事实是否改变。
- **术语**：书名、系列、作者、人物、地点、机构是否遵循词表且全文一致。
- **流畅**：语法、搭配、语序和标点是否自然。
- **地道与文体**：是否符合图书类型与中文出版简介语域，是否有生硬翻译腔或过度营销。
- **格式**：是否只有目标字段、无标签/解释/Markdown，段落和不可翻译内容是否保持。

错误分类可对齐 W3C ITS 2.0 的 `terminology`、`mistranslation`、`omission`、`addition`、`grammar`、`style` 等类型，严重度和罚分由 BookRank3 在黄金集上校准。[W3C ITS 2.0 质量问题类型](https://www.w3.org/TR/its20/#lqissue-typevalues)

自动门禁只负责发现明显风险：术语未命中、原文数字/ISBN丢失、输出含标签或 Markdown、异常重复、空输出、截断、中文比例异常、标题与人物同名却译法不一致。自动通过不代表译文优美；上线前仍需按 ISO 5060 的思路做分层人工抽样。

## 对 BookRank3 的具体建议

当前实现见 [`app/services/zhipu_translation_service.py`](../../app/services/zhipu_translation_service.py)：

1. **P0 — 改消息结构**：SiliconFlow/Hunyuan 路径使用一条完整 `user` 消息，保留官方“翻译成中文、不要额外解释”骨架；智谱路径可继续独立维护，不要共享同一提示策略。
2. **P0 — 改调用粒度**：一本书先组装上下文和术语表；标题先译/确认，简介随后使用定稿标题与专名。不要继续让标题只看到一个孤立字符串。
3. **P0 — 版本化缓存**：缓存键除模型外还应包含提示模板版本、上下文/术语表版本和字段类型；否则新提示上线后仍可能命中旧译文。
4. **P1 — 建立译名资产**：按 ISBN/作品、系列和实体维护来源、译名、适用地区、审核状态；生产页优先使用“人工确认/正式来源”，模型输出不得覆盖。
5. **P1 — 加质量门禁与审核队列**：人名/单词标题、双关、标题与人物同名、术语冲突、多个候选差异过大时进入人工审核。
6. **P1 — 做受控 A/B 评估**：先用黄金集验证消息格式、上下文和参数，再重新生成全量语言包；记录模型、提示版本、参数、trace id、候选和审核结论。
7. **P2 — 评估候选融合**：若 SiliconFlow 上线 Chimera 或可部署官方 Chimera，按官方模板做多候选融合实验；在此之前，不以“让基础模型反思/解释”冒充该能力。

最值得先做的最小实验是：选 30 本高风险书，把当前提示与“单 user + 图书上下文 + 术语表”提示进行盲评。若 `Verity`、人物同名标题、系列名和双关标题的误译显著下降，再扩大到黄金集和全量重译。

## 主要来源

- Tencent Hunyuan：[Hunyuan-MT-7B 官方模型卡](https://huggingface.co/tencent/Hunyuan-MT-7B)
- Tencent Hunyuan：[Hunyuan-MT Technical Report](https://arxiv.org/abs/2509.05209)
- SiliconFlow：[Chat Completions API](https://docs.siliconflow.cn/docs/api/chat-completions-post)
- ISO：[ISO 5060:2024 — Translation output evaluation](https://www.iso.org/standard/80701.html)
- ISO：[ISO 12616-1:2021 — Translation-oriented terminography](https://www.iso.org/standard/72308.html)
- ISO：[ISO 17100:2015 — Requirements for translation services](https://www.iso.org/standard/59149.html)
- W3C：[Internationalization Tag Set (ITS) 2.0](https://www.w3.org/TR/its20/)

# 河口巡测湖

河口巡测资料中心把外业测带和巡测区修订加工为可核查的巡查调度净单。库管可分次接收瓦片件，调度员按正式版号领取任务变化及来源。

## 运行

需要 Python 3.11 标准库。从项目根目录运行。

```sh
python3 -B check_project.py
python3 -B -m lake.application demo
python3 -B -m lake.application route-demo
```

控制台提供 `check_project.py`。原套件也可直接用 unittest 运行。

```sh
python3 -B -m unittest discover -s tests -t . -p 'test_*.py'
```

演示在临时目录建立瓦片工作库和湖库，读取 `examples/sources.json` 和 `examples/workday.json`。输出包括每次到件后的发布状态、已签版的命中、净单和来源。样例先以西侧 `(S,A)` 建立版，再让同一组合移至东侧，最后让东侧改为 `(S,B)`。东件迟到时可见待件，同名换位净差为空，换项同时给出解除和新增。

持久工作库可独立初始化。

```sh
python3 -B -m lake.application init ./lake.sqlite ./field.sqlite
```

## 工作入口

以下入口以文件路径标识工作库。`lake_path` 为湖库，`field_path` 为瓦片工作库，两库使用不同文件。应用函数自行打开和关闭连接，写入操作各自提交。程序可在初始化后直接导入这些 Python 入口。

| 模块与入口 | 输入和结果 |
| --- | --- |
| `lake.application.initialize(lake_path, field_path)` | 创建缺失的表和正式空起始版 `origin`，可重复执行。 |
| `surveys.registry.register(field_path, kind, object_id, revision, source, bounds, crew=None)` | `kind` 用 `footprint` 或 `zone`。`bounds` 用 `Rectangle` 或四项 `(left, bottom, right, top)`。`crew` 仅用于 `footprint`，登记该测带负责班组。返回 `SourceRevision`，其 `ref` 可冻结用于建轮。 |
| `rounds.plans.open_round(lake_path, field_path, round_id, parent_id, assignments)` | `assignments` 从瓦片号映射到一组 `RevisionRef`。每个瓦片每类业务编号限一份修订。返回冻结的 `RoundPlan`。`get_round(lake_path, round_id)` 可重读。 |
| `tiles.packets.seal_tile(lake_path, field_path, round_id, tile_id)` | 从冻结绑定计算并暂存 `TilePacket`。包内含裁剪到本瓦片、带班组与确切修订的有效测带覆盖及巡测区范围。未清理的重封存返回原件。 |
| `lake.intake.accept_tile(lake_path, round_id, packet)` | 在湖库原子保存可恢复的瓦片材料和正式 `TileReceipt`。同件重投复领原收据。 |
| `tiles.release.release_tile(lake_path, field_path, source_id, receipt)` | 核对该湖库已提交的正式收据，清除对应暂存并持久记录 `ReleaseResult`。重复清理返回同一结局。 |
| `lake.publish.publish(lake_path, round_id)` | 待件返回 `PublishResult` 的 `missing`。齐件发布为 `lake-<round_id>`，已签轮次重投复领原版号。发布时把该版随瓦片实收的测带覆盖与班组、巡测区范围存入湖库。 |
| `dispatch.readback.read(lake_path, version_id)` | 读取正式 `DispatchSheet`，含命中、`delta.added`、`delta.removed`、所有命中来源及净单来源。指定版尚不存在时返回 `None`。 |
| `dispatch.routes.Route(points, zone)` | 路线输入：`points` 为折点 `(x, y)` 序列（整数、`Fraction` 或数值文本），`zone` 为路线所在巡测区编号。沿折点自带累计里程。 |
| `dispatch.routes.HandoverPolicy(crews, max_handovers, common_length)` | 巡查约束：可用班组、最多交班次数及每次交班所需的共同覆盖长度（连续里程）。 |
| `dispatch.routes.plan_route(lake_path, version_id, route, policy)` | 只读指定正式湖版核查路线，返回 `RoutePlan`：从起点可安全领跑的最长前缀 `reachable`、交班安排 `handovers` 及各段的班组、里程与来源测带 `segments`。 |
| `dispatch.routes.route_plan_record(plan)` | 把 `RoutePlan` 转为可序列化记录，里程用精确文本表示。 |

轮次、业务编号、修订和来源说明使用非空文本。非法输入和身份冲突抛出 `ValueError`，查不到必需的轮次、父版、来源或暂存时抛出 `LookupError`。正式收据缺失或不匹配时清理抛出 `ValueError`，原暂存继续保留。收据和清理结果均可复领。已清件可用此前留存的原 `TilePacket` 重投，重封存已清槽位会报告暂存已清理。湖侧的 `lake.evidence.load_round_evidence` 可通过湖库连接复查原收件。数据库错误由 SQLite 异常原样报告，本次写事务回滚。

## 计算和状态

瓦片号为 `列,行`，例如 `0,0`、`1,0`、`-1,0`。窗口宽高均为十格，列行从原点计。矩形为半开整数窗口。交集取各下界最大值及上界最小值，两个差值都大于零才计算面积。命中身份由测带号与巡测区号确定，各瓦片支持附确切修订、来源件号及正整数面积。湖库信任瓦片作业端提供的局部计算事实，点收核对其冻结绑定、规范内容、具名身份、面积范围和内容摘要。

显式改写某瓦片时，传空引用列表可使该瓦片封存为空。零相交的输入也可封存为空件。改写名单内的缺件阻止签发，名单外瓦片按指定父版沿用。空名单可签出净单为空的新版。正式点收后，可以删除源暂存而保留湖端实收。发布使用一个湖侧事务保存版本、签发、支持引用与调度结果。发布失败后可使用原实收续投。后续修订、清理和发布均保留按版号可读的历史。

全湖命中及净单按测带号、巡测区号排序。每个键的来源按瓦片号及确切修订排序，解除使用父版来源，新增使用新版来源。同一命中在两瓦片存续时只派一个任务。原套件覆盖修订冲突、边点接触和瓦片裁剪、错件与重投、实际清理和重开、沿用最后一份支持、迟到与逆序交付，以及提交失败后的恢复。

## 路线交班

`dispatch.routes.plan_route` 沿一条自带里程的折线，从起点核查指定正式湖版。核查只读取湖库中随瓦片实收的测带覆盖与巡测区范围，源库关闭后仍可复查。规则如下：

- 只有持有该路段实测、且路段在路线巡测区内的班组可以领跑；区外或没有当班有效实测的里程不得领跑。
- 交班须在换组前完成 `common_length` 长度的连续共同覆盖：这段共同覆盖须由当前班组领跑（交班点不早于当前段的起点），且不得与上一次交班的共同覆盖重复计入。
- 返回从起点可安全领跑的最长前缀 `reachable`；等长时取交班次数最少的安排。
- 各段记录领跑班组、起止里程与原瓦片测带（含测带号与确切修订）；`handovers` 记录实际交班位置与共同覆盖区间。

演示 `route-demo` 建立全路几何连续覆盖的两组：`alpha` 覆盖 `0..10`、`beta` 覆盖 `10..30`，仅在 `x=10` 相接，无法直接交班，最长前缀止于 `10`。加入覆盖 `5..25` 的中间班组 `gamma` 后，可先由 `alpha` 与 `gamma` 共同覆盖 `5..7` 交班、再由 `gamma` 与 `beta` 共同覆盖 `10..12` 交班，走完整条路线。

班组或测带改版只影响新湖版：旧版仍按原实收覆盖与班组核查。`surveys.registry.register` 的 `crew` 参与修订身份，同名同修订换班组会被判为内容冲突，须使用新修订号。
